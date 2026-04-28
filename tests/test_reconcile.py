"""Unit tests for the core reconciliation logic."""
from pnl_truthteller.reconcile import Trade, Fill, reconcile_one, reconcile_trades
from pnl_truthteller.report import aggregate_summary, build_report


def test_perfect_fill_no_slippage():
    """A trade where actual fills match theoretical exactly → zero slippage."""
    trade = Trade(
        token_id="0xabc",
        entry_time="2026-04-25T12:00:00+00:00",
        entry_price=0.05,
        shares=100.0,
        size_usd=5.0,
        exit_time="2026-04-25T14:00:00+00:00",
        exit_price=0.10,
        exit_reason="TARGET",
        question="Test market",
    )
    fills = [
        Fill(
            token_id="0xabc",
            side="BUY",
            timestamp="2026-04-25T12:00:30+00:00",
            making_amount=5.0,
            taking_amount=100.0,
            order_id="buy-1",
        ),
        Fill(
            token_id="0xabc",
            side="SELL",
            timestamp="2026-04-25T14:00:30+00:00",
            making_amount=100.0,
            taking_amount=10.0,
            order_id="sell-1",
        ),
    ]
    rec = reconcile_one(trade, fills)
    assert rec is not None
    assert rec.is_paper_era is False
    assert rec.actual_buy_usdc == 5.0
    assert rec.actual_sell_usdc == 10.0
    assert rec.theoretical_pnl == 5.0
    assert rec.actual_pnl == 5.0
    assert rec.slippage_usd == 0.0
    assert rec.dust_shares_remaining == 0.0


def test_slippage_due_to_partial_fill():
    """Bot expected $5 cost, $10 proceeds, but actual proceeds were only $8."""
    trade = Trade(
        token_id="0xabc",
        entry_time="2026-04-25T12:00:00+00:00",
        entry_price=0.05,
        shares=100.0,
        size_usd=5.0,
        exit_time="2026-04-25T14:00:00+00:00",
        exit_price=0.10,
        exit_reason="TIMEOUT",
    )
    fills = [
        Fill("0xabc", "BUY", "2026-04-25T12:00:30+00:00", 5.0, 100.0, "buy-1"),
        Fill("0xabc", "SELL", "2026-04-25T14:00:30+00:00", 100.0, 8.0, "sell-1"),
    ]
    rec = reconcile_one(trade, fills)
    assert rec.theoretical_pnl == 5.0
    assert rec.actual_pnl == 3.0
    assert rec.slippage_usd == -2.0


def test_dedup_by_order_id():
    """Same orderID logged twice (sweep retry) — should count once."""
    trade = Trade(
        token_id="0xabc",
        entry_time="2026-04-25T12:00:00+00:00",
        entry_price=0.05,
        shares=100.0,
        size_usd=5.0,
        exit_time="2026-04-25T14:00:00+00:00",
        exit_price=0.10,
    )
    # Two SELL fills with the same orderID
    fills = [
        Fill("0xabc", "BUY", "2026-04-25T12:00:30+00:00", 5.0, 100.0, "buy-1"),
        Fill("0xabc", "SELL", "2026-04-25T14:00:30+00:00", 100.0, 9.0, "sell-X"),
        Fill("0xabc", "SELL", "2026-04-25T14:00:35+00:00", 100.0, 9.0, "sell-X"),  # dup!
    ]
    rec = reconcile_one(trade, fills)
    # Only ONE sell counted, so actual sell = $9 (not $18)
    assert rec.actual_sell_usdc == 9.0
    assert rec.n_sell_orders == 1


def test_paper_era_trade_excluded_from_totals():
    """A trade with no live BUY found is marked paper-era."""
    trade = Trade(
        token_id="0xabc",
        entry_time="2026-04-25T12:00:00+00:00",
        entry_price=0.05,
        shares=100.0,
        size_usd=5.0,
        exit_time="2026-04-25T14:00:00+00:00",
        exit_price=0.10,
    )
    fills: list[Fill] = []  # no fills logged
    rec = reconcile_one(trade, fills)
    assert rec.is_paper_era is True
    assert rec.actual_buy_usdc == 0.0
    assert rec.slippage_usd == 0.0  # no slippage attributed to paper-era


def test_dust_remaining():
    """Bot bought 100 shares but only sold 90 — 10 shares stranded on-chain."""
    trade = Trade(
        token_id="0xabc",
        entry_time="2026-04-25T12:00:00+00:00",
        entry_price=0.05,
        shares=100.0,
        size_usd=5.0,
        exit_time="2026-04-25T14:00:00+00:00",
        exit_price=0.10,
    )
    fills = [
        Fill("0xabc", "BUY", "2026-04-25T12:00:30+00:00", 5.0, 100.0, "buy-1"),
        Fill("0xabc", "SELL", "2026-04-25T14:00:30+00:00", 90.0, 9.0, "sell-1"),
    ]
    rec = reconcile_one(trade, fills)
    assert rec.dust_shares_remaining == 10.0


def test_window_excludes_unrelated_fills():
    """Fills outside the matching window for that trade are ignored."""
    trade = Trade(
        token_id="0xabc",
        entry_time="2026-04-25T12:00:00+00:00",
        entry_price=0.05,
        shares=100.0,
        size_usd=5.0,
        exit_time="2026-04-25T14:00:00+00:00",
        exit_price=0.10,
    )
    fills = [
        Fill("0xabc", "BUY", "2026-04-25T12:00:30+00:00", 5.0, 100.0, "buy-1"),
        Fill("0xabc", "SELL", "2026-04-25T14:00:30+00:00", 100.0, 10.0, "sell-1"),
        # Far-future SELL on the same token — different trade, should be ignored
        Fill("0xabc", "SELL", "2026-05-01T12:00:00+00:00", 100.0, 10.0, "sell-future"),
    ]
    rec = reconcile_one(trade, fills)
    # Only one sell counted (the one within window)
    assert rec.n_sell_orders == 1


def test_aggregate_summary_excludes_paper():
    """Aggregate metrics should ignore paper-era trades."""
    live = Trade(
        token_id="0xabc",
        entry_time="2026-04-25T12:00:00+00:00",
        entry_price=0.05,
        shares=100.0,
        size_usd=5.0,
        exit_time="2026-04-25T14:00:00+00:00",
        exit_price=0.10,
        exit_reason="TARGET",
    )
    paper = Trade(
        token_id="0xdef",
        entry_time="2026-03-01T12:00:00+00:00",
        entry_price=0.05,
        shares=100.0,
        size_usd=5.0,
        exit_time="2026-03-01T14:00:00+00:00",
        exit_price=0.10,
        exit_reason="TARGET",
    )
    fills = [
        Fill("0xabc", "BUY", "2026-04-25T12:00:30+00:00", 5.0, 100.0, "buy-1"),
        Fill("0xabc", "SELL", "2026-04-25T14:00:30+00:00", 100.0, 8.0, "sell-1"),
    ]
    records = reconcile_trades([live, paper], fills)
    summary = aggregate_summary(records)
    assert summary["n_total"] == 2
    assert summary["n_live"] == 1
    assert summary["n_paper"] == 1
    # Slippage attributed only to live trade
    assert summary["total_slippage"] == -2.0


def test_build_report_smoke():
    """Report should render without raising."""
    trade = Trade(
        token_id="0xabc",
        entry_time="2026-04-25T12:00:00+00:00",
        entry_price=0.05,
        shares=100.0,
        size_usd=5.0,
        exit_time="2026-04-25T14:00:00+00:00",
        exit_price=0.10,
        exit_reason="TARGET",
        question="Will X happen?",
    )
    fills = [
        Fill("0xabc", "BUY", "2026-04-25T12:00:30+00:00", 5.0, 100.0, "buy-1"),
        Fill("0xabc", "SELL", "2026-04-25T14:00:30+00:00", 100.0, 8.0, "sell-1"),
    ]
    records = reconcile_trades([trade], fills)
    report = build_report(records, label="test-bot")
    assert "Slippage Report" in report
    assert "test-bot" in report
    assert "TARGET" in report
