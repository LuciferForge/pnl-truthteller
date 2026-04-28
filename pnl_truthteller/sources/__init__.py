"""Data source adapters — load Trades and Fills from various backends."""
from pnl_truthteller.sources.jsonl import load_jsonl
from pnl_truthteller.sources.sqlite_source import load_sqlite

__all__ = ["load_jsonl", "load_sqlite", "load_clob_api"]


def load_clob_api(*args, **kwargs):
    """Lazy import to avoid hard dependency on py-clob-client-v2."""
    from pnl_truthteller.sources.clob_api import load_clob_api as _impl

    return _impl(*args, **kwargs)
