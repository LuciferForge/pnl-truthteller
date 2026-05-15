# pnl-truthteller

[![PyPI](https://img.shields.io/pypi/v/pnl-truthteller.svg)](https://pypi.org/project/pnl-truthteller/)
[![Python](https://img.shields.io/pypi/pyversions/pnl-truthteller.svg)](https://pypi.org/project/pnl-truthteller/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Audit your Polymarket bot's actual on-chain P&L vs what your bot thinks it earned.**

```bash
pip install pnl-truthteller
pnl-truthteller --wallet 0xYourPolymarketProxy --output report.md
```

That's the entire workflow. Wallet address only. No API keys. Read-only. You get a markdown report showing how much your fill slippage is actually costing you.

## What we found

We built this because our own crash-recovery bot looked profitable in its SQLite (+$34) but felt like it was bleeding capital. We were right:

| Source | Trades | DB-reported P&L | On-chain P&L | **Hidden slippage** |
|---|---:|---:|---:|---:|
| Our bot | 320 | $+34.31 | $-90.72 | **$-125.03** |
| Random stranger's wallet (`0x1417...`) | 65 | $+32.36 | $-30.29 | **$-62.66** |

**The gap generalises.** We tested the tool on a random Polymarket trader's wallet pulled from the public CLOB feed — same pattern. Their DB-equivalent showed +$32 over 65 trades; the chain says -$30; that's $62 of hidden slippage they don't know about.

Both samples are in [`examples/`](examples/).

## Why this exists

Most Polymarket bots record P&L the moment an order is **placed**, not when it **fills**. The CLOB matching engine fills in stages (FOK rejects, partial fills, sweep retries, dust). If your bot writes `profit=$3.20` to its DB the moment `post_order` returns OK, but the actual on-chain fills only retrieve $2.85, you're losing ~11% to slippage and your DB is lying to you about it.

This package finds that gap on your bot.

## Install

```bash
pip install pnl-truthteller
```

Or from source:
```bash
git clone https://github.com/LuciferForge/pnl-truthteller
cd pnl-truthteller
pip install -e .
```

## Usage — three input modes

### 1. Direct from CLOB API (recommended — zero setup)

If you trade through `py-clob-client` or `py-clob-client-v2`, your fills are queryable from Polymarket's CLOB API. Just give us your wallet address:

```bash
pnl-truthteller --wallet 0xYourProxyAddress --output report.md
```

This pulls every fill for the wallet, groups them by token+direction, and produces a slippage report.

### 2. From your bot's SQLite (if you've been logging fills locally)

If your bot stores raw CLOB responses in a SQLite file (column `raw_response`), point the tool at it:

```bash
pnl-truthteller --sqlite ~/bot/trades.db \
                --positions ~/bot/positions.json \
                --output report.md
```

Schema expected: a `live_trades` table with columns `token_id, side, timestamp, raw_response` where `raw_response` is the JSON string returned by `client.post_order()`. See [`docs/data-format.md`](docs/data-format.md).

### 3. From a JSONL file (custom integrations)

If you're on a non-Python stack or have custom logging, dump your trades + fills to JSONL and pass them in:

```bash
pnl-truthteller --trades trades.jsonl --fills fills.jsonl --output report.md
```

Format spec: [`docs/data-format.md`](docs/data-format.md).

## What the report looks like

```
# Slippage Report — 2026-04-28T14:30:00+00:00

## TL;DR
- Closed trades total: 308 (live: 308, paper: 0)
- Lifetime theoretical P&L: +$33.49
- Lifetime actual P&L (on-chain fills): -$89.01
- Total slippage cost: -$122.50 (-365.8% of theoretical)
- Trades with stranded dust on-chain: 31 (total 47.3 shares dust)

## By exit reason
| Reason | n | Theoretical | Actual | Slippage |
|---|---|---|---|---|
| TIMEOUT | 142 | -$18.00 | -$84.50 | -$66.50 |
| TARGET | 71 | +$28.40 | +$22.10 | -$6.30 |
| RECOVERY_TRAILED | 50 | +$15.20 | +$12.40 | -$2.80 |
| STOP | 39 | +$7.89 | +$0.99 | -$6.90 |

## Worst 10 slippage events (per-trade)
[table of the 10 worst trades by slippage]
```

## What this measures, precisely

For each closed trade in your data, the tool:

1. **Finds the actual BUY fills** by matching token+timestamp window, deduplicated by `orderID`.
2. **Finds the actual SELL fills** that closed the position (same matching, same dedup).
3. **Computes theoretical P&L** = `(exit_price - entry_price) × shares` (what the bot's DB says).
4. **Computes actual P&L** = `sum(sell_takingAmount) - sum(buy_makingAmount)` (what the chain says).
5. **Slippage = actual - theoretical**. Negative = your fill ladder walked the book down.

The dedup-by-`orderID` step is critical. Sweep retries (where your bot tries 5%, 15%, 25% off ref price) often log the same orderID multiple times if your bot calls `post_order` from a retry loop without checking idempotency. Without dedup you double-count the proceeds and your slippage looks fine when it isn't.

## What it does NOT do

- It does NOT execute trades. Read-only auditing.
- It does NOT need your private key. Wallet address only.
- It does NOT report tax-purpose P&L. Slippage-focused, not gain/loss accounting.
- It does NOT work for non-Polymarket markets (yet — see roadmap).

## FAQ (audited operators' first questions)

**Q: Does this need my private key?**
No. Wallet address only. The script reads public on-chain fills + the public CLOB feed. Same data Polymarket's own UI shows anyone who types your address in.

**Q: Where does the audited data go?**
Nowhere. Local file in → local file out. No telemetry, no API call to me, no upload. Verify with `pip show pnl-truthteller` then read the source — it's ~600 lines.

**Q: I don't use a SQLite-logging bot, just trade by hand. Useful?**
Yes — use mode 1 (`--wallet 0x...`). It pulls fills directly from CLOB and shows you slippage vs. mid-book at fill time. You don't need any local logging at all.

**Q: How is this different from just reading my P&L on the Polymarket UI?**
Polymarket's UI shows realized + unrealized P&L. It does *not* show the gap between your intended fill price and your actual fill price. That gap — slippage — is what `pnl-truthteller` isolates and attributes by exit reason. Without that attribution you can't fix what's bleeding.

**Q: Why is this free / what's the catch?**
The companion Polymarket dataset is paid (link at bottom). The auditor is free MIT because the more people who run it, the more wallets contribute to the public [Polymarket Slippage Index](examples/POLYMARKET_SLIPPAGE_INDEX.md) — which makes the dataset more valuable. Cooperative game.

## When to run it

| Frequency | Why |
|-----------|-----|
| Once, now | If you've never done a fill-level audit, run it once to find out what your real P&L is. |
| Daily (cron) | If your bot is live, run the report nightly to catch slippage regressions early. |
| After every parameter change | Param changes (entry threshold, exit ladder) shift slippage. Run before/after to measure. |

## Roadmap

- v0.2 — Per-market category breakdown (sports vs politics vs crypto have different liquidity profiles)
- v0.3 — Orderbook-depth-at-time-of-fill reconstruction (what was the actual book when you swept?)
- v0.4 — Adapter for [Kalshi](https://kalshi.com) and other prediction-market venues
- v0.5 — Streamlit dashboard (real-time slippage monitoring)

## Public progress (no marketing, just receipts)

Weekly recaps with verifiable numbers (downloads, stars, real operator questions, what worked vs didn't) are posted as Announcements in this repo's [Discussions](https://github.com/LuciferForge/pnl-truthteller/discussions/categories/announcements). Most recent: [Week 1 recap (2026-05-15)](https://github.com/LuciferForge/pnl-truthteller/discussions/6).

## About the author

Built by [LuciferForge](https://github.com/LuciferForge), a solo operator running a [public-audited Polymarket crash-recovery bot](https://github.com/LuciferForge/polymarket-crash-bot) (308 closed trades, 80.2% WR). I built this because my own bot's DB was lying to me — found -$122.50 of hidden slippage cost on 308 trades. Now that the math is honest, the parameters can be too. Yours can be too.

Other tools in the LuciferForge stack:
- [`pip install polymarket-mcp-pro`](https://github.com/LuciferForge/polymarket-mcp) — Polymarket data as MCP tools for Claude / Cursor / Cline.
- [`pip install cross-signal-data`](https://github.com/LuciferForge/cross-signal-data) — 308-trade labeled crash-recovery dataset (free, MIT, also on HuggingFace).
- [`pip install quant-rollout`](https://github.com/LuciferForge/quant-rollout) — staged-deployment toolkit (gates, kill switch, veto window).
- [`pip install sigil-ta`](https://github.com/LuciferForge/sigil) — MCP-native TA runtime with the unique Polymarket Sentiment Divergence signal.
- [LuciferForge/polymarket-v2-migration](https://github.com/LuciferForge/polymarket-v2-migration) — V1→V2 cookbook for the April 28, 2026 cutover.

## Want the underlying Polymarket dataset?

The bot/dataset combo this tool was built and tested against is on Gumroad:

**13,964 markets · 10.8M price records · $11.7B+ volume · clean CSVs + SQLite + manifest**

→ [manja8.gumroad.com/l/polymarket-data](https://manja8.gumroad.com/l/polymarket-data?utm_source=github&utm_medium=readme&utm_campaign=pnl-truthteller-readme) — one-time price, lifetime updates.

If you want to test your own slippage analysis against the same raw market data we use, this is the file.

## License

MIT. Audit your bot, audit your friends' bots, audit anyone's bot. The chain is public.
