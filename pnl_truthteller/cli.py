"""Command-line interface for pnl-truthteller."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pnl_truthteller.reconcile import reconcile_trades
from pnl_truthteller.report import build_report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pnl-truthteller",
        description=(
            "Audit your Polymarket bot's actual on-chain P&L vs DB-recorded P&L. "
            "Pick exactly one input mode: --wallet, --sqlite, or --trades+--fills."
        ),
    )

    src = p.add_argument_group("input source (pick one mode)")
    src.add_argument(
        "--wallet",
        help="Polymarket proxy wallet address (0x...). Pulls fills from CLOB data-api.",
    )
    src.add_argument(
        "--sqlite",
        help="Path to a SQLite DB with a `live_trades` table containing raw_response JSON.",
    )
    src.add_argument(
        "--positions",
        help="Path to positions.json (required with --sqlite).",
    )
    src.add_argument(
        "--trades",
        help="Path to trades.jsonl (used with --fills).",
    )
    src.add_argument(
        "--fills",
        help="Path to fills.jsonl (used with --trades).",
    )

    p.add_argument(
        "-o",
        "--output",
        default="-",
        help="Output path for the markdown report. Default: stdout.",
    )
    p.add_argument(
        "--jsonl-out",
        help="If set, also write per-trade SlippageRecords as JSONL to this path.",
    )
    p.add_argument(
        "--label",
        help="Optional label to include in the report title (e.g., bot name).",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Mode resolution
    modes_used = sum(
        [
            bool(args.wallet),
            bool(args.sqlite or args.positions),
            bool(args.trades or args.fills),
        ]
    )
    if modes_used == 0:
        print(
            "ERROR: pick one input mode: --wallet, --sqlite + --positions, or --trades + --fills.",
            file=sys.stderr,
        )
        return 2
    if modes_used > 1:
        print(
            "ERROR: pick exactly one input mode (--wallet, --sqlite, or --trades/--fills).",
            file=sys.stderr,
        )
        return 2

    if args.wallet:
        from pnl_truthteller.sources import load_clob_api

        trades, fills = load_clob_api(wallet=args.wallet)
        label = args.label or args.wallet[:10] + "..."

    elif args.sqlite:
        if not args.positions:
            print("ERROR: --sqlite requires --positions.", file=sys.stderr)
            return 2
        from pnl_truthteller.sources import load_sqlite

        trades, fills = load_sqlite(
            sqlite_path=args.sqlite,
            positions_path=args.positions,
        )
        label = args.label

    else:  # JSONL mode
        if not (args.trades and args.fills):
            print("ERROR: JSONL mode requires both --trades and --fills.", file=sys.stderr)
            return 2
        from pnl_truthteller.sources import load_jsonl

        trades, fills = load_jsonl(
            trades_path=args.trades,
            fills_path=args.fills,
        )
        label = args.label

    if not trades:
        print("WARN: no trades loaded — nothing to reconcile.", file=sys.stderr)

    records = reconcile_trades(trades, fills)
    report = build_report(records, label=label)

    if args.output == "-":
        sys.stdout.write(report)
    else:
        Path(args.output).write_text(report)
        print(f"Wrote report → {args.output}", file=sys.stderr)

    if args.jsonl_out:
        with Path(args.jsonl_out).open("w") as f:
            for r in records:
                f.write(json.dumps(r.to_dict()) + "\n")
        print(f"Wrote per-trade JSONL → {args.jsonl_out}", file=sys.stderr)

    # Print one-liner summary to stderr for cron/script use
    from pnl_truthteller.report import aggregate_summary

    s = aggregate_summary(records)
    print(
        f"[pnl-truthteller] live={s['n_live']} "
        f"theoretical=${s['total_theoretical']:+.2f} "
        f"actual=${s['total_actual']:+.2f} "
        f"slippage=${s['total_slippage']:+.2f}",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
