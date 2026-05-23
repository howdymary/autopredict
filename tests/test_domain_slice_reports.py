"""Tests for grouped domain slice evaluation utilities."""

from __future__ import annotations

from autopredict.evaluation import (
    BacktestResult,
    BacktestTrade,
    BinaryForecast,
    summarize_backtest_slices,
    summarize_domain_slices,
)
from autopredict.evaluation.scoring import ProperScoringRules


def _trade(group: str, pnl: float, slippage_bps: float) -> BacktestTrade:
    return BacktestTrade(
        market_id=f"{group}-market",
        venue="fixture",
        side="buy",
        order_type="market",
        requested_size=10.0,
        filled_size=10.0,
        fill_price=0.50,
        reference_price=0.49,
        outcome=1,
        pnl=pnl,
        fee_paid=0.1,
        slippage_bps=slippage_bps,
        fill_rate=1.0,
        metadata={
            "domain": group,
            "market_family": f"{group}-family",
            "regime": f"{group}-regime",
        },
    )


def test_summarize_domain_slices_groups_forecasts_and_trades() -> None:
    """Grouped slice summaries should aggregate by metadata label."""

    forecasts = (
        BinaryForecast("finance-1", 0.80, 1, metadata={"domain": "finance"}),
        BinaryForecast("finance-2", 0.60, 1, metadata={"domain": "finance"}),
        BinaryForecast("weather-1", 0.20, 0, metadata={"domain": "weather"}),
    )
    trades = (
        _trade("finance", pnl=4.0, slippage_bps=3.0),
        _trade("weather", pnl=1.5, slippage_bps=1.0),
    )

    summaries = summarize_domain_slices(forecasts, trades, group_by="domain")

    by_group = {summary.group: summary for summary in summaries}
    assert tuple(sorted(by_group)) == ("finance", "weather")
    assert by_group["finance"].count == 2
    assert by_group["finance"].forecast_count == 2
    assert by_group["finance"].trade_count == 1
    assert by_group["finance"].total_pnl == 4.0
    assert by_group["finance"].avg_slippage_bps == 3.0
    assert by_group["weather"].count == 1
    assert by_group["weather"].total_pnl == 1.5
    assert by_group["weather"].mean_absolute_calibration_gap >= 0.0
    assert "sparse_support" in by_group["finance"].warning_flags


def test_summarize_backtest_slices_supports_family_and_regime_grouping() -> None:
    """BacktestResult summaries should support alternate metadata keys."""

    forecasts = (
        BinaryForecast(
            "finance-1",
            0.80,
            1,
            metadata={"market_family": "macro", "regime": "post_release"},
        ),
        BinaryForecast(
            "finance-2",
            0.30,
            0,
            metadata={"market_family": "macro", "regime": "post_release"},
        ),
        BinaryForecast(
            "politics-1",
            0.55,
            1,
            metadata={"market_family": "elections", "regime": "breaking_news"},
        ),
    )
    trades = (
        BacktestTrade(
            market_id="macro-1",
            venue="fixture",
            side="buy",
            order_type="market",
            requested_size=10.0,
            filled_size=10.0,
            fill_price=0.52,
            reference_price=0.50,
            outcome=1,
            pnl=3.2,
            fee_paid=0.1,
            slippage_bps=2.0,
            fill_rate=1.0,
            metadata={"market_family": "macro", "regime": "post_release"},
        ),
        BacktestTrade(
            market_id="elections-1",
            venue="fixture",
            side="buy",
            order_type="market",
            requested_size=10.0,
            filled_size=10.0,
            fill_price=0.57,
            reference_price=0.56,
            outcome=1,
            pnl=1.1,
            fee_paid=0.1,
            slippage_bps=1.0,
            fill_rate=1.0,
            metadata={"market_family": "elections", "regime": "breaking_news"},
        ),
    )
    result = BacktestResult(
        decisions=(),
        forecasts=forecasts,
        trades=trades,
        scoring=ProperScoringRules.evaluate_binary_forecasts(forecasts),
        metrics={},
    )

    family_summaries = summarize_backtest_slices(result, group_by="market_family")
    regime_summaries = summarize_backtest_slices(result, group_by="regime")

    family_groups = {summary.group for summary in family_summaries}
    regime_groups = {summary.group for summary in regime_summaries}

    assert family_groups == {"macro", "elections"}
    assert regime_groups == {"post_release", "breaking_news"}


def test_slice_reports_surface_sparse_and_unstable_groups() -> None:
    """Grouped summaries should flag thin or one-sided forecast slices."""

    forecasts = (
        BinaryForecast(
            "macro-1",
            0.92,
            0,
            metadata={"market_family": "macro", "regime": "post_release"},
        ),
        BinaryForecast(
            "macro-2",
            0.91,
            0,
            metadata={"market_family": "macro", "regime": "post_release"},
        ),
    )
    trades = (
        BacktestTrade(
            market_id="macro-1",
            venue="fixture",
            side="buy",
            order_type="market",
            requested_size=10.0,
            filled_size=10.0,
            fill_price=0.50,
            reference_price=0.49,
            outcome=0,
            pnl=-2.0,
            fee_paid=0.1,
            slippage_bps=4.0,
            fill_rate=1.0,
            metadata={"market_family": "macro", "regime": "post_release"},
        ),
    )

    summaries = summarize_domain_slices(forecasts, trades, group_by="market_family")

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.group == "macro"
    assert summary.forecast_count == 2
    assert summary.trade_count == 1
    assert summary.mean_absolute_error > 0.0
    assert summary.max_absolute_calibration_gap >= summary.mean_absolute_calibration_gap
    assert "sparse_support" in summary.warning_flags
    assert "single_class_outcomes" in summary.warning_flags
    assert "narrow_probability_band" in summary.warning_flags
    assert "high_calibration_gap" in summary.warning_flags
