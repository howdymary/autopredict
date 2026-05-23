"""Contract tests for the Step 2 evaluation layer."""

from __future__ import annotations

import importlib
import math
from datetime import datetime, timedelta

import pytest

from autopredict.core.types import (
    MarketCategory,
    MarketState,
    Order,
    OrderSide,
    OrderType,
    Portfolio,
)
from autopredict.evaluation.scoring import BinaryForecast, CalibrationSummary, ProperScoringRules
from autopredict.evaluation.backtest import ResolvedMarketSnapshot
from autopredict.prediction_market import (
    MarketSignal,
    MarketSnapshot,
    PredictionMarketAgent,
    StrategyContext,
    VenueConfig,
    VenueName,
)


def _load_module(module_name: str):
    """Import a Step 2 module and fail with a clear message if it is missing."""

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised when module lands
        pytest.fail(f"missing expected evaluation module: {module_name} ({exc})")


class ScriptedStrategy:
    """Deterministic strategy used to drive the scaffold backtester."""

    name = "scripted"

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> MarketSignal | None:
        del context
        if snapshot.market.market_id == "buy-market":
            return MarketSignal(
                fair_prob=0.70,
                confidence=0.90,
                rationale="scripted buy",
            )
        if snapshot.market.market_id == "sell-market":
            return MarketSignal(
                fair_prob=0.30,
                confidence=0.90,
                rationale="scripted sell",
            )
        return None

    def build_orders(
        self,
        snapshot: MarketSnapshot,
        signal: MarketSignal,
        context: StrategyContext,
    ) -> list[Order]:
        del signal, context
        if snapshot.market.market_id == "buy-market":
            return [
                Order(
                    market_id=snapshot.market.market_id,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    size=25.0,
                )
            ]
        if snapshot.market.market_id == "sell-market":
            return [
                Order(
                    market_id=snapshot.market.market_id,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    size=8.0,
                )
            ]
        return []


@pytest.fixture
def venue() -> VenueConfig:
    """Create a stable venue config for evaluation tests."""

    return VenueConfig(name=VenueName.POLYMARKET, fee_bps=10.0, tick_size=0.01)


@pytest.fixture
def portfolio() -> Portfolio:
    """Create a stable portfolio for evaluation tests."""

    return Portfolio(cash=1_000.0, starting_capital=1_000.0)


def _market(
    market_id: str,
    *,
    market_prob: float,
    fair_prob: float,
    bid: float,
    ask: float,
    bid_liquidity: float,
    ask_liquidity: float,
) -> MarketState:
    return MarketState(
        market_id=market_id,
        question=f"Will {market_id} resolve YES?",
        market_prob=market_prob,
        expiry=datetime.now() + timedelta(days=2),
        category=MarketCategory.OTHER,
        best_bid=bid,
        best_ask=ask,
        bid_liquidity=bid_liquidity,
        ask_liquidity=ask_liquidity,
        metadata={"fair_prob": fair_prob},
    )


def _buy_market_snapshot() -> MarketState:
    return _market(
        "buy-market",
        market_prob=0.45,
        fair_prob=0.70,
        bid=0.49,
        ask=0.51,
        bid_liquidity=20.0,
        ask_liquidity=15.0,
    )


def _sell_market_snapshot() -> MarketState:
    return _market(
        "sell-market",
        market_prob=0.55,
        fair_prob=0.30,
        bid=0.48,
        ask=0.52,
        bid_liquidity=20.0,
        ask_liquidity=20.0,
    )


def _backtest_cases(venue: VenueConfig, portfolio: Portfolio) -> list[ResolvedMarketSnapshot]:
    return [
        ResolvedMarketSnapshot(
            market=_buy_market_snapshot(),
            venue=venue,
            outcome=1,
            context_metadata={"portfolio_cash": portfolio.cash},
            snapshot_features={"book_depth": 35.0},
            metadata={"next_mid_price": 0.73},
        ),
        ResolvedMarketSnapshot(
            market=_sell_market_snapshot(),
            venue=venue,
            outcome=0,
            context_metadata={"portfolio_cash": portfolio.cash},
            snapshot_features={"book_depth": 40.0},
            metadata={"next_mid_price": 0.26},
        ),
    ]


def test_evaluation_modules_export_expected_surfaces() -> None:
    """The new package should expose scoring, calibration, and backtest entrypoints."""

    evaluation = _load_module("autopredict.evaluation")
    scoring = _load_module("autopredict.evaluation.scoring")
    backtest = _load_module("autopredict.evaluation.backtest")

    for name in ("BinaryForecast", "CalibrationSummary", "ProperScoringRules"):
        assert hasattr(scoring, name), f"missing scoring function: {name}"

    for name in ("BinaryForecast", "CalibrationSummary", "ProperScoringRules"):
        assert hasattr(evaluation, name), f"missing package export: {name}"

    for name in ("BacktestResult", "ExecutionAssumptions", "PredictionMarketBacktester"):
        assert hasattr(backtest, name), f"missing backtest export: {name}"


@pytest.mark.parametrize(
    "probability,outcome,expected_brier,expected_log,expected_spherical",
    [
        (0.80, 1, 0.04, math.log(0.80), 0.80 / math.sqrt(0.80**2 + 0.20**2)),
        (0.20, 0, 0.04, math.log(0.80), 0.80 / math.sqrt(0.20**2 + 0.80**2)),
    ],
)
def test_binary_scoring_rules_match_closed_forms(
    probability: float,
    outcome: int,
    expected_brier: float,
    expected_log: float,
    expected_spherical: float,
) -> None:
    """Brier, log, and spherical scores should match the closed-form binary formulas."""

    forecast = BinaryForecast("m", probability, outcome)

    assert ProperScoringRules.brier_score([forecast]) == pytest.approx(expected_brier)
    assert ProperScoringRules.log_score([forecast]) == pytest.approx(expected_log)
    assert ProperScoringRules.spherical_score([forecast]) == pytest.approx(expected_spherical)


def test_log_score_is_finite_at_probability_boundaries() -> None:
    """Log scoring should clamp probabilities instead of exploding at 0 or 1."""

    zero_positive = BinaryForecast("m1", 0.0, 1)
    one_negative = BinaryForecast("m2", 1.0, 0)

    assert math.isfinite(ProperScoringRules.log_score([zero_positive]))
    assert math.isfinite(ProperScoringRules.log_score([one_negative]))
    assert ProperScoringRules.log_score([zero_positive]) < ProperScoringRules.log_score(
        [BinaryForecast("m3", 0.5, 1)]
    )
    assert ProperScoringRules.log_score([one_negative]) < ProperScoringRules.log_score(
        [BinaryForecast("m4", 0.5, 0)]
    )


def test_calibration_summary_buckets_and_errors() -> None:
    """Calibration summaries should be deterministic and bucketed by forecast range."""

    forecasts = [
        BinaryForecast("m1", 0.10, 0),
        BinaryForecast("m2", 0.15, 0),
        BinaryForecast("m3", 0.80, 1),
        BinaryForecast("m4", 0.90, 1),
    ]

    summary = ProperScoringRules.calibration_summary(forecasts, num_buckets=2)

    assert isinstance(summary, CalibrationSummary)
    assert len(summary.buckets) == 2
    assert summary.base_rate == pytest.approx(0.5)
    assert summary.mean_absolute_gap == pytest.approx(0.1375)
    assert summary.max_absolute_gap == pytest.approx(0.15)
    assert len(summary.buckets) == 2

    lower_bucket, upper_bucket = summary.buckets
    assert lower_bucket.lower == pytest.approx(0.0)
    assert lower_bucket.upper == pytest.approx(0.5)
    assert lower_bucket.count == 2
    assert lower_bucket.avg_probability == pytest.approx(0.125)
    assert lower_bucket.realized_rate == pytest.approx(0.0)
    assert lower_bucket.absolute_gap == pytest.approx(0.125)

    assert upper_bucket.lower == pytest.approx(0.5)
    assert upper_bucket.upper == pytest.approx(1.0)
    assert upper_bucket.count == 2
    assert upper_bucket.avg_probability == pytest.approx(0.85)
    assert upper_bucket.realized_rate == pytest.approx(1.0)
    assert upper_bucket.absolute_gap == pytest.approx(0.15)

    as_dict = summary.to_dict()
    assert as_dict["base_rate"] == pytest.approx(0.5)
    assert as_dict["mean_absolute_gap"] == pytest.approx(0.1375)
    assert as_dict["max_absolute_gap"] == pytest.approx(0.15)


def test_scaffold_backtester_uses_agent_outputs_and_liquidity(
    venue: VenueConfig,
    portfolio: Portfolio,
) -> None:
    """The backtester should deterministically evaluate agent orders against book depth."""

    backtest = _load_module("autopredict.evaluation.backtest")
    agent = PredictionMarketAgent(strategy=ScriptedStrategy())
    backtester = backtest.PredictionMarketBacktester()

    result = backtester.run(agent, _backtest_cases(venue, portfolio))

    assert result.scoring.count == 2
    assert result.metrics["brier_score"] == pytest.approx(0.09)
    assert result.metrics["log_score"] == pytest.approx(math.log(0.70))
    assert result.metrics["spherical_score"] == pytest.approx(
        0.70 / math.sqrt(0.70**2 + 0.30**2)
    )
    assert result.metrics["avg_fill_rate"] == pytest.approx(0.8)
    assert result.metrics["avg_slippage_bps"] > 0
    assert result.metrics["total_pnl"] > 0

    assert len(result.decisions) == 2
    assert len(result.forecasts) == 2
    assert len(result.trades) == 2

    buy_trade, sell_trade = result.trades
    assert buy_trade.market_id == "buy-market"
    assert buy_trade.requested_size == pytest.approx(25.0)
    assert buy_trade.filled_size == pytest.approx(15.0)
    assert buy_trade.fill_rate == pytest.approx(0.6)

    assert sell_trade.market_id == "sell-market"
    assert sell_trade.requested_size == pytest.approx(8.0)
    assert sell_trade.filled_size == pytest.approx(8.0)
    assert sell_trade.fill_rate == pytest.approx(1.0)


def test_scaffold_backtester_is_deterministic(
    venue: VenueConfig,
    portfolio: Portfolio,
) -> None:
    """Repeated runs over the same inputs should return identical outputs."""

    backtest = _load_module("autopredict.evaluation.backtest")
    agent = PredictionMarketAgent(strategy=ScriptedStrategy())
    backtester = backtest.PredictionMarketBacktester()

    first = backtester.run(agent, _backtest_cases(venue, portfolio))
    second = backtester.run(agent, _backtest_cases(venue, portfolio))

    assert first.to_dict() == second.to_dict()
