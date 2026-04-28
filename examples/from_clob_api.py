#!/usr/bin/env python3
"""Example: reconcile a wallet's full history from CLOB data-api.

Usage:
    POLYMARKET_PROXY_ADDRESS=0xYourProxy python examples/from_clob_api.py

You don't need a private key or API key for this — wallet address only.
"""
import os
import sys

from pnl_truthteller import reconcile_trades, build_report
from pnl_truthteller.sources import load_clob_api

WALLET = os.environ.get("POLYMARKET_PROXY_ADDRESS")
if not WALLET:
    print("Set POLYMARKET_PROXY_ADDRESS env var to your proxy wallet address.", file=sys.stderr)
    sys.exit(1)

print(f"Fetching fills for {WALLET}...", file=sys.stderr)
trades, fills = load_clob_api(wallet=WALLET)
print(f"Got {len(trades)} inferred trades from {len(fills)} fills.", file=sys.stderr)

records = reconcile_trades(trades, fills)
print(build_report(records, label=WALLET[:10] + "..."))
