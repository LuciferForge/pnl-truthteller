"""SQLite adapter — load Trades from positions.json and Fills from a SQLite DB.

The default schema matches the LuciferForge crash-recovery bot's `live_trades.db`
but the query parameters are configurable for other bots.

Expected SQLite schema (default):
    CREATE TABLE live_trades (
        id INTEGER PRIMARY KEY,
        token_id TEXT,
        side TEXT,           -- "BUY" or "SELL"
        timestamp TEXT,      -- ISO-8601
        raw_response TEXT    -- JSON string from client.post_order()
    );

The `raw_response` JSON is expected to contain CLOB fields:
    - orderID
    - makingAmount  (USDC for BUYs, shares for SELLs)
    - takingAmount  (shares for BUYs, USDC for SELLs)

Trades come from a positions.json with shape:
    {
        "open": [...],
        "closed": [
            {
                "token_id": "...",
                "entry_time": "2026-04-25T12:00:00+00:00",
                "entry_price": 0.05,
                "exit_time": "2026-04-26T18:30:00+00:00",
                "exit_price": 0.10,
                "shares": 100.0,
                "size_usd": 5.0,
                "exit_reason": "TARGET",
                "question": "Will X happen by Y?"
            },
            ...
        ]
    }
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from pnl_truthteller.reconcile import Trade, Fill


def _g(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d:
            return d[k]
    return default


def _fill_from_row(token_id: str, side: str, timestamp: str, raw_response: str) -> Fill | None:
    try:
        rj = json.loads(raw_response) if raw_response else {}
    except json.JSONDecodeError:
        return None
    return Fill(
        token_id=token_id,
        side=side.upper(),
        timestamp=timestamp,
        making_amount=float(rj.get("makingAmount", 0.0) or 0.0),
        taking_amount=float(rj.get("takingAmount", 0.0) or 0.0),
        order_id=rj.get("orderID") or rj.get("orderId"),
        raw=rj,
    )


def load_sqlite(
    *,
    sqlite_path: str | Path,
    positions_path: str | Path,
    table: str = "live_trades",
    token_id_col: str = "token_id",
    side_col: str = "side",
    timestamp_col: str = "timestamp",
    raw_response_col: str = "raw_response",
) -> tuple[list[Trade], list[Fill]]:
    """Load trades from a positions.json and fills from a SQLite DB.

    Parameters allow overriding column names for bots with different schemas.
    """
    pos_path = Path(positions_path)
    sql_path = Path(sqlite_path)

    if not pos_path.exists():
        raise FileNotFoundError(f"positions file not found: {pos_path}")
    if not sql_path.exists():
        raise FileNotFoundError(f"sqlite file not found: {sql_path}")

    pos = json.loads(pos_path.read_text())
    closed = pos.get("closed", []) if isinstance(pos, dict) else []

    trades: list[Trade] = []
    for d in closed:
        trades.append(
            Trade(
                token_id=str(_g(d, "token_id", "tokenId", default="")),
                entry_time=str(_g(d, "entry_time", "entryTime", default="")),
                entry_price=float(_g(d, "entry_price", "entryPrice", default=0.0) or 0.0),
                shares=float(_g(d, "shares", default=0.0) or 0.0),
                size_usd=float(_g(d, "size_usd", "sizeUsd", default=0.0) or 0.0),
                exit_time=_g(d, "exit_time", "exitTime"),
                exit_price=_g(d, "exit_price", "exitPrice"),
                exit_reason=_g(d, "exit_reason", "exitReason"),
                question=_g(d, "question", "market"),
            )
        )

    con = sqlite3.connect(str(sql_path))
    try:
        cur = con.execute(
            f"SELECT {token_id_col}, {side_col}, {timestamp_col}, {raw_response_col} "
            f"FROM {table}"
        )
        fills: list[Fill] = []
        for row in cur:
            f = _fill_from_row(*row)
            if f is not None:
                fills.append(f)
    finally:
        con.close()

    return trades, fills
