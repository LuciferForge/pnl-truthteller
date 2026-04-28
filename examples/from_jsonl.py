#!/usr/bin/env python3
"""Example: reconcile from a pair of JSONL files.

Run:
    python examples/from_jsonl.py
"""
from pathlib import Path

from pnl_truthteller import reconcile_trades, build_report
from pnl_truthteller.sources import load_jsonl

HERE = Path(__file__).parent
FIXTURES = HERE.parent / "tests" / "fixtures"

trades, fills = load_jsonl(
    trades_path=FIXTURES / "sample_trades.jsonl",
    fills_path=FIXTURES / "sample_fills.jsonl",
)
records = reconcile_trades(trades, fills)
print(build_report(records, label="sample-bot"))
