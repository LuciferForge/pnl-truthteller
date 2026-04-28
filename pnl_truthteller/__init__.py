"""pnl-truthteller — Polymarket on-chain P&L vs DB-recorded P&L reconciliation.

Public API:
    from pnl_truthteller import reconcile_trades, build_report
    from pnl_truthteller.sources import load_clob_api, load_sqlite, load_jsonl

See README.md for usage examples.
"""

from pnl_truthteller.reconcile import (
    SlippageRecord,
    Trade,
    Fill,
    reconcile_trades,
    reconcile_one,
)
from pnl_truthteller.report import build_report, aggregate_summary

__version__ = "0.1.0"
__all__ = [
    "SlippageRecord",
    "Trade",
    "Fill",
    "reconcile_trades",
    "reconcile_one",
    "build_report",
    "aggregate_summary",
    "__version__",
]
