"""Core reconciliation: match trades to on-chain fills, compute slippage.

This module is data-source-agnostic. It takes plain dicts/dataclasses describing
trades (intended buys/sells) and fills (actual on-chain settlement records) and
produces SlippageRecord objects.

Source adapters (CLOB API, SQLite, JSONL) live in `pnl_truthteller.sources` and
return data in the shapes defined here.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence


# Default match windows. The BUY window is tight (the live BUY happens
# right around the trade's recorded entry_time). The SELL window is wider
# because exits often involve multiple sweep rounds spanning up to an hour.
DEFAULT_BUY_WINDOW_BEFORE_SEC = 10
DEFAULT_BUY_WINDOW_AFTER_SEC = 120
DEFAULT_SELL_WINDOW_BEFORE_SEC = 10
DEFAULT_SELL_WINDOW_AFTER_SEC = 3600


@dataclass
class Trade:
    """A logical trade — one round-trip the bot opened and (usually) closed.

    Fields map to what most Polymarket bots already log. If a bot has different
    column names, the source adapters normalize them into this shape.
    """

    token_id: str
    entry_time: str  # ISO-8601 string (timezone-aware preferred, naive treated as UTC)
    entry_price: float = 0.0
    shares: float = 0.0
    size_usd: float = 0.0
    exit_time: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    question: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fill:
    """A single on-chain settlement record from CLOB.

    For BUYs: maker side gives USDC, taker receives shares.
        making_amount = USDC out, taking_amount = shares in
    For SELLs: maker side gives shares, taker receives USDC.
        making_amount = shares out, taking_amount = USDC in
    """

    token_id: str
    side: str  # "BUY" or "SELL"
    timestamp: str  # ISO-8601
    making_amount: float
    taking_amount: float
    order_id: str | None = None  # used for dedup
    raw: dict[str, Any] | None = None  # original record, for debugging


@dataclass
class SlippageRecord:
    token_id: str
    entry_time: str
    exit_time: str | None
    exit_reason: str | None
    question: str | None
    is_paper_era: bool
    size_usd: float
    entry_price: float
    exit_price: float | None
    actual_buy_usdc: float
    actual_buy_shares: float
    actual_sell_usdc: float
    actual_sell_shares: float
    dust_shares_remaining: float
    theoretical_pnl: float
    actual_pnl: float
    slippage_usd: float
    n_buy_orders: int
    n_sell_orders: int

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_ts(s: str | None) -> float | None:
    """Parse ISO-8601 string to UNIX seconds. Naive timestamps treated as UTC."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _fnum(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def reconcile_one(
    trade: Trade,
    fills: Sequence[Fill],
    *,
    buy_window_before_sec: int = DEFAULT_BUY_WINDOW_BEFORE_SEC,
    buy_window_after_sec: int = DEFAULT_BUY_WINDOW_AFTER_SEC,
    sell_window_before_sec: int = DEFAULT_SELL_WINDOW_BEFORE_SEC,
    sell_window_after_sec: int = DEFAULT_SELL_WINDOW_AFTER_SEC,
) -> SlippageRecord | None:
    """Reconcile one trade against the candidate fills.

    Returns a SlippageRecord, or None if the trade has no resolvable timestamp.

    For trades with no live BUYs found (paper-era / pre-deployment), the record
    is returned with `is_paper_era=True` and zero on-chain numbers — the caller
    typically filters these out before aggregating.
    """
    entry_ts = _parse_ts(trade.entry_time)
    if entry_ts is None:
        return None

    exit_ts = _parse_ts(trade.exit_time) if trade.exit_time else None
    sell_hi_ts = (
        (exit_ts + sell_window_after_sec)
        if exit_ts
        else (entry_ts + 86400 * 3)  # cap at 3 days for un-closed trades
    )

    buy_lo_ts = entry_ts - buy_window_before_sec
    buy_hi_ts = entry_ts + buy_window_after_sec
    sell_lo_ts = entry_ts - sell_window_before_sec

    # Pre-filter fills by token (cheap)
    candidate_fills = [f for f in fills if f.token_id == trade.token_id]

    seen_buy_orders: set[str] = set()
    actual_buy_usdc = 0.0
    actual_buy_shares = 0.0

    seen_sell_orders: set[str] = set()
    actual_sell_usdc = 0.0
    actual_sell_shares = 0.0

    for f in candidate_fills:
        f_ts = _parse_ts(f.timestamp)
        if f_ts is None:
            continue

        if f.side.upper() == "BUY":
            if not (buy_lo_ts <= f_ts < buy_hi_ts):
                continue
            oid = f.order_id or f"_no_oid_buy_{f_ts}_{f.making_amount}_{f.taking_amount}"
            if oid in seen_buy_orders:
                continue
            seen_buy_orders.add(oid)
            actual_buy_usdc += _fnum(f.making_amount)
            actual_buy_shares += _fnum(f.taking_amount)

        elif f.side.upper() == "SELL":
            if not (sell_lo_ts <= f_ts < sell_hi_ts):
                continue
            oid = f.order_id or f"_no_oid_sell_{f_ts}_{f.making_amount}_{f.taking_amount}"
            if oid in seen_sell_orders:
                continue
            seen_sell_orders.add(oid)
            actual_sell_usdc += _fnum(f.taking_amount)
            actual_sell_shares += _fnum(f.making_amount)

    is_paper_era = actual_buy_usdc <= 0 and len(seen_buy_orders) == 0

    entry_price = _fnum(trade.entry_price)
    exit_price = _fnum(trade.exit_price) if trade.exit_price is not None else None
    size_usd = _fnum(trade.size_usd, 1.0)

    if entry_price > 0 and exit_price is not None:
        theoretical_pnl = (exit_price - entry_price) * _fnum(trade.shares)
    else:
        theoretical_pnl = 0.0

    actual_pnl = actual_sell_usdc - actual_buy_usdc

    if is_paper_era:
        slippage = 0.0
    else:
        slippage = actual_pnl - theoretical_pnl

    dust_shares = max(0.0, actual_buy_shares - actual_sell_shares)

    return SlippageRecord(
        token_id=trade.token_id,
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        exit_reason=trade.exit_reason,
        question=(trade.question or "")[:80] if trade.question else None,
        is_paper_era=is_paper_era,
        size_usd=round(size_usd, 4),
        entry_price=entry_price,
        exit_price=exit_price,
        actual_buy_usdc=round(actual_buy_usdc, 4),
        actual_buy_shares=round(actual_buy_shares, 4),
        actual_sell_usdc=round(actual_sell_usdc, 4),
        actual_sell_shares=round(actual_sell_shares, 4),
        dust_shares_remaining=round(dust_shares, 4),
        theoretical_pnl=round(theoretical_pnl, 4),
        actual_pnl=round(actual_pnl, 4),
        slippage_usd=round(slippage, 4),
        n_buy_orders=len(seen_buy_orders),
        n_sell_orders=len(seen_sell_orders),
    )


def reconcile_trades(
    trades: Iterable[Trade],
    fills: Sequence[Fill],
    **kwargs,
) -> list[SlippageRecord]:
    """Reconcile a batch of trades. Returns a list of SlippageRecord (paper-era included)."""
    out: list[SlippageRecord] = []
    fills_list = list(fills)
    for t in trades:
        rec = reconcile_one(t, fills_list, **kwargs)
        if rec is not None:
            out.append(rec)
    return out
