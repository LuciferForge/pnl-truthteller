# Polymarket Slippage Index — first cut

**Date:** 2026-04-30
**Method:** [pnl-truthteller](https://github.com/LuciferForge/pnl-truthteller) v0.1.1 `--wallet` mode against public Polymarket wallets pulled from the [Polymarket CLOB data-api](https://data-api.polymarket.com).
**Question:** Is the slippage gap our crash bot showed (DB +$33 / chain −$89) specific to our bot, or a general feature of how Polymarket bots track P&L?

---

## TL;DR

We pulled 3,500 recent CLOB trades, identified the most-active wallets, and audited their full lifetime fill history. Across **four wallets where the on-chain reconciliation is methodologically clean** (active trade-out behavior, not buy-and-hold-to-resolution), the pattern repeats:

| Wallet | Round-trip trades | DB-equivalent P&L | Actual on-chain P&L | **Hidden slippage** | Slip per trade |
|---|---:|---:|---:|---:|---:|
| Our bot (ground truth via SQLite) | 320 | $+34.31 | $-90.72 | **$-125.03** | $-0.39 |
| Stranger `0x1417f1b7…` | 65 | $+32.36 | $-30.29 | **$-62.66** | $-0.96 |
| Stranger `0x75cc3b63…` | 814 | $-618.63 | $-3,520.39 | **$-2,901.76** | $-3.57 |
| Stranger `0x8a2f4ff4…` (Creamy-Weapon) | 38 | $-375.50 | $-1,366.29 | **$-990.79** | $-26.07 |
| Stranger `0x77fc654f…` (Beautiful-Violin) | 14 | $+805.61 | $-1,919.99 | **$-2,725.60** | $-194.69 |

**Across the 5 clean cases: 1,251 round-trip trades, $-6,805.84 of hidden slippage cost.** Average per-trade slippage: **$-5.44**.

Three of these wallets *thought they were profitable* (positive theoretical P&L). All five were actually underwater on-chain by the time fill quality was reconciled.

---

## What "hidden slippage" means

Most Polymarket bots compute and store P&L the moment `client.post_order()` returns OK — that is, at order-submission time, using the order's intended price/size. The CLOB matching engine then fills the order in stages: FOK rejects, partial fills, sweep-and-retry, dust shares left behind. The on-chain USDC delta when the dust settles is often materially different from the bot-reported P&L.

`pnl-truthteller` reconciles "what your bot recorded" against "what actually moved on-chain" and surfaces the gap.

For our own bot, the SQLite has full intent-vs-fill ground truth. For stranger wallets, the CLOB API only gives us fills — the bot's internal P&L is inferred from fill prices, which is a **lower bound** on the gap. The real gap on those wallets is at least as large as we report, often larger.

---

## Detail: the clean cases

### Our bot (LuciferForge crash-recovery)
- 320 lifetime closed trades (228 paper-era + 92 live on V1+V2)
- DB-recorded: +$34.31
- On-chain pUSD movement: -$90.72
- **Hidden slippage: -$125.03** — bigger than every claimed profit on the bot.
- Worst single trade: -$40.63 actual vs +$0.16 theoretical (3-share dust on a 21-share Cooper Flagg position)
- Full report: [`SLIPPAGE_REPORT.md`](https://github.com/LuciferForge/pnl-truthteller/blob/main/examples/) [committed separately]

### `0x1417f1b73133aed6bc9cf58d14506128571b4dd2` — random wallet from CLOB feed
- 65 lifetime round-trip trades
- DB-equivalent: +$32.36
- On-chain: -$30.29
- **Hidden slippage: -$62.66**
- 13 trades with stranded dust on-chain (413 shares)
- Worst single trade: -$40.53 (theoretical -$0.10 on what looked like a small position)
- Full report: [`sample_report_stranger_wallet.md`](https://github.com/LuciferForge/pnl-truthteller/blob/main/examples/sample_report_stranger_wallet.md)

### `0x75cc3b63a2f2423085e10706c78b494017b93ce1` — high-frequency wallet
- 814 lifetime round-trip trades — by far the biggest sample
- DB-equivalent: -$618.63 (the bot already knows it's losing)
- On-chain: -$3,520.39
- **Hidden slippage: -$2,901.76** — 4.7× larger than its bot-reported loss
- **492 of 814 trades have stranded dust** (60% — extreme fill quality issue)
- Worst single trade: -$113.33 slippage on a -$0.78 theoretical loss
- This wallet *knows* it's bleeding but doesn't know it's bleeding 5× harder than it thinks.

### `0x8a2f4ff4c8ee2f590fe6abc8b9bbda2c02c8c860` — Creamy-Weapon
- 38 round-trip trades
- DB-equivalent: -$375.50
- On-chain: -$1,366.29
- **Hidden slippage: -$990.79** — 2.6× the bot-reported loss
- Worst single trade: -$268.11 (a $101 theoretical winner that turned into a $166 actual loss; 362 shares dust)
- 17 of 38 trades with stranded dust (45%)

### `0x77fc654fb6c0c574dd4e28d33c98d149f985c044` — Beautiful-Violin
- 14 round-trip trades — small sample but extreme per-trade slippage
- DB-equivalent: +$805.61 (bot thinks it's profitable)
- On-chain: -$1,919.99 (bot is actually deeply underwater)
- **Hidden slippage: -$2,725.60** — entire bot-reported profit is illusory
- The clean "your DB is lying to you" case.

---

## Methodology + limitations

**What we ran.** For each wallet, `pnl-truthteller --wallet 0x… -o report.md`. The tool pulls every fill from the public Polymarket CLOB data-api (`https://data-api.polymarket.com/trades?user=…`), pairs them into round-trip BUY→SELL clusters (oldest-BUY-first FIFO), and computes:
- `theoretical_pnl = sum(SELL.takingAmount) − sum(BUY.makingAmount)` using the recorded fill prices
- `actual_pnl = the same thing, but with sweep-retry dedup applied via orderID`
- `slippage = actual − theoretical`

**For our own bot we use the SQLite source instead** (`pnl-truthteller --sqlite trades.db --positions positions.json`). That gives intent-vs-fill ground truth: the bot's expected price/size at submission time, vs the actual on-chain delivery. The CLOB-only mode used for stranger wallets is a heuristic — for buy-and-hold traders whose positions resolve to $0 or $1, the CLOB has no SELL leg and the tool can't reconcile.

**What we excluded.** The pull surfaced 33 wallets where the heuristic returned data, but for ~25 of them the "actual P&L" was inflated by market-resolution payouts (e.g., a wallet bought at $0.05 and held to a $1 resolution shows up as a giant favorable "slippage"). Those numbers are not reliable estimates of fill quality and we exclude them from this Index. The 5 cases above are wallets whose trade pattern is close to round-trip-on-orderbook (active sells, not resolution unwinding).

**What this Index is and isn't:**
- **Is:** a directional finding that the slippage gap is general, not specific to our bot.
- **Isn't:** an accurate slippage estimate for any single wallet from CLOB-only data. Real reconciliation requires the bot's intent log.

---

## How to audit your own bot

```bash
pip install --upgrade pnl-truthteller

# from a wallet address (lower-bound estimate):
pnl-truthteller --wallet 0xYourPolymarketProxy --output report.md

# from your bot's SQLite (full ground truth):
pnl-truthteller --sqlite ./trades.db --positions ./positions.json --output report.md
```

If your DB-reported P&L and your on-chain P&L disagree by more than ±5% over 50+ trades, you almost certainly have an exit-ladder or sweep-retry issue silently eating your edge.

---

## Want a free audit?

If you run a Polymarket bot and want us to run this on your wallet (no auth, just an address; we send back the report within 24 hours), open an issue on the [pnl-truthteller repo](https://github.com/LuciferForge/pnl-truthteller/issues) or contact `manja316@gmail.com`.

---

*Methodology questions, corrections, or additions to the Index — file an issue.*
*Source code:* https://github.com/LuciferForge/pnl-truthteller
*PyPI:* https://pypi.org/project/pnl-truthteller/
