# Data format

`pnl-truthteller` accepts three input modes. This document specifies the schema each mode expects.

## Mode 1: CLOB API (`--wallet 0x...`)

Pulls fills directly from `data-api.polymarket.com/trades?user=<wallet>`. No local files required.

Trades are heuristically reconstructed by pairing FIFO BUYs against SELLs of the same token. This is approximate: if your bot does partial closes or holds multiple lots in the same market, the inferred trades may not match your bot's logical trades exactly. For high-fidelity reconciliation, prefer mode 2 or 3.

## Mode 2: SQLite + positions.json (`--sqlite ... --positions ...`)

This is the recommended mode if your bot already logs to disk.

### `positions.json` schema

A JSON file with shape:

```json
{
  "open": [],
  "closed": [
    {
      "token_id": "0x...",
      "entry_time": "2026-04-25T12:00:00+00:00",
      "entry_price": 0.05,
      "shares": 100.0,
      "size_usd": 5.0,
      "exit_time": "2026-04-25T14:00:00+00:00",
      "exit_price": 0.10,
      "exit_reason": "TARGET",
      "question": "Will X happen by Y?"
    }
  ]
}
```

Required: `token_id`, `entry_time`. Everything else is optional but improves the report quality.

The loader also accepts camelCase variants (`tokenId`, `entryTime`, etc.) for compatibility with Node-stack bots.

### SQLite schema

A table (default name `live_trades`) with at minimum:

```sql
CREATE TABLE live_trades (
    id INTEGER PRIMARY KEY,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,           -- "BUY" or "SELL"
    timestamp TEXT NOT NULL,      -- ISO-8601 string
    raw_response TEXT NOT NULL    -- JSON string from client.post_order()
);
```

The `raw_response` JSON must contain the CLOB response fields (`orderID`, `makingAmount`, `takingAmount`). This is what `py-clob-client` and `py-clob-client-v2` return from `post_order()`. If you wrap the SDK call, save the response object as JSON in this column.

### Custom column names

If your bot uses different column names, override via Python (the CLI does not expose this — file an issue if you need it):

```python
from pnl_truthteller.sources import load_sqlite

trades, fills = load_sqlite(
    sqlite_path="my_bot.db",
    positions_path="positions.json",
    table="my_trades_table",
    token_id_col="asset_id",
    side_col="direction",
    timestamp_col="created_at",
    raw_response_col="exchange_response",
)
```

## Mode 3: JSONL (`--trades ... --fills ...`)

For non-Python stacks or custom integrations.

### `trades.jsonl`

One JSON object per line:

```json
{"token_id":"0xa1","entry_time":"2026-04-20T10:00:00+00:00","entry_price":0.05,"shares":100.0,"size_usd":5.0,"exit_time":"2026-04-20T18:00:00+00:00","exit_price":0.10,"exit_reason":"TARGET","question":"Will A happen?"}
```

Fields (camelCase variants accepted):
- **token_id** (string, required) — Polymarket CLOB token ID
- **entry_time** (ISO-8601 string, required) — when the trade was opened
- **entry_price** (float) — price-per-share at entry
- **shares** (float) — share count
- **size_usd** (float) — USD allocation
- **exit_time** (ISO-8601 string) — when closed
- **exit_price** (float) — price-per-share at exit
- **exit_reason** (string) — TARGET / STOP / TIMEOUT / etc.
- **question** (string) — market question (for report readability)

### `fills.jsonl`

One JSON object per line:

```json
{"token_id":"0xa1","side":"BUY","timestamp":"2026-04-20T10:00:30+00:00","making_amount":5.0,"taking_amount":100.0,"order_id":"buy-a1-1"}
```

Fields:
- **token_id** (string, required) — same as trades
- **side** (string, required) — `"BUY"` or `"SELL"`
- **timestamp** (ISO-8601 string, required) — when the fill settled
- **making_amount** (float) — for BUY: USDC paid; for SELL: shares delivered
- **taking_amount** (float) — for BUY: shares received; for SELL: USDC received
- **order_id** (string, recommended) — used for dedup. If missing, dedup falls back to a synthetic key based on (timestamp, amounts) which is less reliable.

### Why `making_amount` / `taking_amount` instead of `price` × `shares`?

Because CLOB fills are reported as raw transfer amounts, not prices. Reconstructing prices from amounts requires you to know which side is the maker and which is the taker — and that's exactly what `side` tells us. Storing the raw amounts means we don't lose precision to floating-point price calculations.

## Common pitfalls

**`order_id` missing or wrong.** Dedup is the single most important step in this tool. If your data has no `order_id` or has duplicate IDs across distinct fills, your slippage numbers will be wrong. Verify by spot-checking a few rows: each unique fill should have a unique `order_id`.

**Timestamp formats.** ISO-8601 strings only. Naive timestamps (no `+00:00` suffix) are treated as UTC. If your data is in local time, convert to UTC before exporting.

**Mixing camelCase and snake_case in one file.** The loader accepts either, but if you mix them line-by-line, debugging is painful. Pick one.

**Large data volumes.** The current implementation loads everything into memory. For wallets with 100,000+ fills, you'll want to chunk by date range — see roadmap.
