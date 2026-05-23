"""Tests for the package-native evaluation layer."""

from __future__ import annotations

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
from autopredict.evaluation import (
    BinaryForecast,
    PredictionMarketBacktester,
    ProperScoringRules,
    ResolvedMarketSnapshot,
)
from autopredict.prediction_market import (
    AgentRunConfig,
    LegacyMispricedStrategyAdapter,
    MarketSignal,
    PredictionMarketAgent,
    VenueConfig,
    VenueName,
)


class StaticStrategy:
    """Deterministic strategy used for backtest assertions."""

    def __init__(self, signal: MarketSignal | None, orders: list[Order]):
        self.signal = signal
        self.orders = orders
        self.name = "static"

    def generate_signal(self, snapshot, context) -> MarketSignal | None:
        del snapshot, context
        return self.signal

    def build_orders(self, snapshot, signal, context) -> list[Order]:
        del snapshot, signal, context
        return list(self.orders)


class MockProbabilityModel:
    """Deterministic probability model for the legacy adapter path."""

    def __init__(self, probability: float, confidence: float):
        self.probability = probability
        self.confidence = confidence

    def predict(self, market: MarketState) -> dict[str, float]:
        del market
        return {
            "probability": self.probability,
            "confidence": self.confidence,
        }


@pytest.fixture
def market() -> MarketState:
    """Create a stable binary market snapshot."""

    return MarketState(
        market_id="eval-1",
        question="Will the evaluation test pass?",
        market_prob=0.50,
        expiry=datetime.now() + timedelta(days=5),
        category=MarketCategory.OTHER,
        best_bid=0.49,
        best_ask=0.51,
        bid_liquidity=100.0,
        ask_liquidity=120.0,
    )


@pytest.fixture
def venue() -> VenueConfig:
    """Create a venue config with explicit fee assumptions."""

    return VenueConfig(name=VenueName.POLYMARKET, fee_bps=10.0, tick_size=0.01)


def test_scoring_rules_perfect_forecasts():
    """Perfect forecasts should achieve the optimal proper scores."""

    forecasts = [
        BinaryForecast("m1", 1.0, 1),
        BinaryForecast("m2", 0.0, 0),
    ]

    report = ProperScoringRules.evaluate_binary_forecasts(forecasts)

    assert report.brier_score == 0.0
    assert report.log_score == pytest.approx(0.0)
    assert report.log_loss == pytest.approx(0.0)
    assert report.spherical_score == pytest.approx(1.0)


def test_log_score_clips_extreme_probabilities():
    """Extreme probabilities should remain finite after clipping."""

    forecasts = [
        BinaryForecast("m1", 0.0, 1),
        BinaryForecast("m2", 1.0, 0),
    ]

    report = ProperScoringRules.evaluate_binary_forecasts(forecasts)

    assert math.isfinite(report.log_score)
    assert math.isfinite(report.log_loss)
    assert report.log_score < 0.0
    assert report.log_loss > 0.0


def test_calibration_summary_uses_fixed_buckets():
    """Calibration summary should provide deterministic bucket statistics."""

    forecasts = [
        BinaryForecast("m1", 0.12, 0),
        BinaryForecast("m2", 0.18, 1),
        BinaryForecast("m3", 0.82, 1),
        BinaryForecast("m4", 0.88, 1),
    ]

    calibration = ProperScoringRules.calibration_summary(forecasts, num_buckets=5)

    assert len(calibration.buckets) == 2
    assert calibration.buckets[0].count == 2
    assert calibration.buckets[1].count == 2
    assert calibration.base_rate == pytest.approx(0.75)
    assert calibration.max_absolute_gap >= calibration.mean_absolute_gap


def test_backtester_partial_fills_marketable_orders(market: MarketState, venue: VenueConfig):
    """Marketable orders should cap fills at visible opposite-side liquidity."""

    signal = MarketSignal(fair_prob=0.70, confidence=0.90)
    order = Order(
        market_id=market.market_id,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=150.0,
    )
    agent = PredictionMarketAgent(strategy=StaticStrategy(signal, [order]))
    backtester = PredictionMarketBacktester()

    result = backtester.run(
        agent,
        [
            ResolvedMarketSnapshot(
                market=market,
                venue=venue,
                outcome=1,
            )
        ],
        starting_cash=1_000.0,
    )

    trade = result.trades[0]
    assert trade.filled_size == pytest.approx(market.ask_liquidity)
    assert trade.fill_rate == pytest.approx(market.ask_liquidity / order.size)
    assert trade.fee_paid > 0.0
    assert trade.slippage_bps > 0.0
    assert result.metrics["num_filled_trades"] == 1


def test_backtester_scales_passive_fills_by_aggressiveness(market: MarketState, venue: VenueConfig):
    """Passive inside-spread quotes should fill deterministically by aggressiveness."""

    signal = MarketSignal(fair_prob=0.62, confidence=0.80)
    order = Order(
        market_id=market.market_id,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=100.0,
        limit_price=0.50,
    )
    agent = PredictionMarketAgent(strategy=StaticStrategy(signal, [order]))
    backtester = PredictionMarketBacktester()

    result = backtester.run(
        agent,
        [
            ResolvedMarketSnapshot(
                market=market,
                venue=venue,
                outcome=1,
            )
        ],
    )

    trade = result.trades[0]
    assert trade.filled_size == pytest.approx(50.0)
    assert trade.fill_rate == pytest.approx(0.5)
    assert trade.fill_price == pytest.approx(order.limit_price or 0.0)
    assert trade.slippage_bps == pytest.approx(0.0)


def test_backtester_scores_legacy_adapter_end_to_end(market: MarketState, venue: VenueConfig):
    """Legacy strategy adapter should produce forecasts and trade metrics in Step 2."""

    agent = PredictionMarketAgent(
        strategy=LegacyMispricedStrategyAdapter(),
        config=AgentRunConfig(min_signal_confidence=0.5),
    )
    backtester = PredictionMarketBacktester()

    result = backtester.run(
        agent,
        [
            ResolvedMarketSnapshot(
                market=market,
                venue=venue,
                outcome=1,
                context_metadata={
                    "probability_model": MockProbabilityModel(0.72, 0.9)
                },
            )
        ],
    )

    assert result.scoring.count == 1
    assert result.metrics["num_trade_decisions"] == 1
    assert result.metrics["brier_score"] == pytest.approx((0.72 - 1.0) ** 2)
    assert "log_score" in result.metrics
    assert "spherical_score" in result.metrics
