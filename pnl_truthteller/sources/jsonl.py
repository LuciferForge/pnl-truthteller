"""JSONL adapter — loads Trades and Fills from JSON Lines files.

Schema is permissive: keys can be camelCase or snake_case, the loader
normalizes both. See docs/data-format.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from pnl_truthteller.reconcile import Trade, Fill


def _g(d: dict, *keys: str, default: Any = None) -> Any:
    """Get the first present key from d among `keys`."""
    for k in keys:
        if k in d:
            return d[k]
    return default


def _trade_from_dict(d: dict) -> Trade:
    return Trade(
        token_id=str(_g(d, "token_id", "tokenId", "asset_id", default="")),
        entry_time=str(_g(d, "entry_time", "entryTime", "open_time", default="")),
        entry_price=float(_g(d, "entry_price", "entryPrice", default=0.0) or 0.0),
        shares=float(_g(d, "shares", "size_shares", default=0.0) or 0.0),
        size_usd=float(_g(d, "size_usd", "sizeUsd", "size", default=0.0) or 0.0),
        exit_time=_g(d, "exit_time", "exitTime", "close_time"),
        exit_price=_g(d, "exit_price", "exitPrice"),
        exit_reason=_g(d, "exit_reason", "exitReason", "close_reason"),
        question=_g(d, "question", "market", "title"),
        extra={k: v for k, v in d.items() if k.startswith("_")},
    )


def _fill_from_dict(d: dict) -> Fill:
    return Fill(
        token_id=str(_g(d, "token_id", "tokenId", "asset_id", default="")),
        side=str(_g(d, "side", default="")).upper(),
        timestamp=str(_g(d, "timestamp", "time", "created_at", default="")),
        making_amount=float(_g(d, "making_amount", "makingAmount", default=0.0) or 0.0),
        taking_amount=float(_g(d, "taking_amount", "takingAmount", default=0.0) or 0.0),
        order_id=_g(d, "order_id", "orderID", "orderId"),
        raw=d,
    )


def _read_jsonl(path: str | Path) -> Iterable[dict]:
    p = Path(path)
    with p.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_jsonl(
    *,
    trades_path: str | Path,
    fills_path: str | Path,
) -> tuple[list[Trade], list[Fill]]:
    """Load trades and fills from two JSONL files."""
    trades = [_trade_from_dict(d) for d in _read_jsonl(trades_path)]
    fills = [_fill_from_dict(d) for d in _read_jsonl(fills_path)]
    return trades, fills
