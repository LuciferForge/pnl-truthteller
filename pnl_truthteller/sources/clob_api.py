"""CLOB API adapter — pull trades and fills directly from Polymarket's CLOB.

Uses the public data-api endpoint for trade history. Wallet address only;
no API keys, no private key. Read-only.

Note: the Polymarket CLOB returns "trades" (filled orders), which we treat
as Fills. To produce Trades (logical round-trips), we group fills by token+side
into BUY clusters and SELL clusters, then pair them by sequence.

This is a heuristic — for high-fidelity Trade reconstruction, prefer the
SQLite or JSONL source which has your bot's intended-trade ground truth.
The CLOB-API source is for "I never logged anything locally, just give me the
chain truth" use cases.
"""
from __future__ import annotations

from typing import Any

import requests

from pnl_truthteller.reconcile import Trade, Fill

CLOB_DATA_API = "https://data-api.polymarket.com"


def _normalize_fill(d: dict) -> Fill | None:
    """Normalize a CLOB API trade row into a Fill."""
    side = str(d.get("side", "")).upper()
    if side not in ("BUY", "SELL"):
        return None

    # CLOB data-api returns these fields:
    # token_id, side, size, price, timestamp, transactionHash, ...
    # We need making_amount / taking_amount in the Fill convention.
    size_shares = float(d.get("size", 0) or 0)
    price = float(d.get("price", 0) or 0)
    usdc = size_shares * price

    if side == "BUY":
        making_amount = usdc          # USDC out
        taking_amount = size_shares   # shares in
    else:  # SELL
        making_amount = size_shares   # shares out
        taking_amount = usdc          # USDC in

    ts_raw = d.get("timestamp")
    if isinstance(ts_raw, (int, float)):
        from datetime import datetime, timezone
        timestamp = datetime.fromtimestamp(ts_raw, tz=timezone.utc).isoformat()
    else:
        timestamp = str(ts_raw or "")

    return Fill(
        token_id=str(d.get("asset", d.get("token_id", "")) or ""),
        side=side,
        timestamp=timestamp,
        making_amount=making_amount,
        taking_amount=taking_amount,
        order_id=d.get("orderID") or d.get("orderId") or d.get("transactionHash"),
        raw=d,
    )


def _pair_fills_into_trades(fills: list[Fill]) -> list[Trade]:
    """Heuristic: pair BUYs with subsequent SELLs of same token to form Trades.

    For each token: scan fills in time order, accumulate BUY shares, then when
    a SELL arrives, match it against the most recent open BUY cluster.
    """
    by_token: dict[str, list[Fill]] = {}
    for f in fills:
        by_token.setdefault(f.token_id, []).append(f)

    trades: list[Trade] = []
    for token_id, tfills in by_token.items():
        tfills_sorted = sorted(tfills, key=lambda x: x.timestamp)
        open_buys: list[Fill] = []  # FIFO queue
        for f in tfills_sorted:
            if f.side == "BUY":
                open_buys.append(f)
            elif f.side == "SELL" and open_buys:
                # Pop the oldest BUY cluster that has remaining shares
                buy = open_buys[0]
                shares = float(buy.taking_amount)
                usdc = float(buy.making_amount)
                if shares <= 0:
                    open_buys.pop(0)
                    continue
                entry_price = (usdc / shares) if shares > 0 else 0
                exit_price = (
                    float(f.taking_amount) / float(f.making_amount)
                    if float(f.making_amount) > 0
                    else 0
                )
                trades.append(
                    Trade(
                        token_id=token_id,
                        entry_time=buy.timestamp,
                        exit_time=f.timestamp,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        shares=shares,
                        size_usd=usdc,
                        exit_reason="(inferred from chain)",
                        question=None,
                    )
                )
                # Mark buy consumed
                open_buys.pop(0)
    return trades


def load_clob_api(
    *,
    wallet: str,
    api_base: str = CLOB_DATA_API,
    limit_per_page: int = 500,
    max_pages: int = 50,
    timeout_sec: float = 30.0,
) -> tuple[list[Trade], list[Fill]]:
    """Fetch all fills for a wallet and pair them into trades.

    Args:
        wallet: the proxy wallet address (NOT the EOA).
        api_base: defaults to Polymarket's data-api.
        limit_per_page: rows per request (CLOB caps at ~500).
        max_pages: hard-stop on pagination to bound runtime.
        timeout_sec: per-request HTTP timeout.

    Returns: (trades, fills) — trades are heuristically paired from fills.
    """
    fills: list[Fill] = []
    offset = 0
    pages = 0

    while pages < max_pages:
        url = f"{api_base}/trades"
        params = {
            "user": wallet,
            "limit": limit_per_page,
            "offset": offset,
        }
        resp = requests.get(url, params=params, timeout=timeout_sec)
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            break

        for row in rows:
            f = _normalize_fill(row)
            if f is not None:
                fills.append(f)

        if len(rows) < limit_per_page:
            break
        offset += limit_per_page
        pages += 1

    trades = _pair_fills_into_trades(fills)
    return trades, fills
