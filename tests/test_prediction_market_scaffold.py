"""Tests for the prediction-market agent scaffold."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from autopredict.core.types import MarketCategory, MarketState, Order, OrderSide, OrderType, Portfolio
from autopredict.prediction_market import (
    AgentRunConfig,
    DecisionStatus,
    LegacyMispricedStrategyAdapter,
    MarketSignal,
    MarketSnapshot,
    PredictionMarketAgent,
    StrategyContext,
    StrategyRegistry,
    VenueConfig,
    VenueName,
)


class StaticStrategy:
    """Simple deterministic strategy for scaffold tests."""

    def __init__(self, *, signal: MarketSignal | None, orders: list[Order]):
        self._signal = signal
        self._orders = orders

    @property
    def name(self) -> str:
        return "static"

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> MarketSignal | None:
        del snapshot, context
        return self._signal

    def build_orders(
        self,
        snapshot: MarketSnapshot,
        signal: MarketSignal,
        context: StrategyContext,
    ) -> list[Order]:
        del snapshot, signal, context
        return list(self._orders)


class MockProbabilityModel:
    """Deterministic probability model for adapter tests."""

    def __init__(self, fair_prob: float, confidence: float = 0.8):
        self.fair_prob = fair_prob
        self.confidence = confidence

    def predict(self, market: MarketState) -> dict[str, float]:
        del market
        return {
            "probability": self.fair_prob,
            "confidence": self.confidence,
        }


@pytest.fixture
def market() -> MarketState:
    """Create a sample market."""
    return MarketState(
        market_id="pm-123",
        question="Will Step 1 pass?",
        market_prob=0.45,
        expiry=datetime.now() + timedelta(days=3),
        category=MarketCategory.OTHER,
        best_bid=0.44,
        best_ask=0.46,
        bid_liquidity=1_000.0,
        ask_liquidity=1_200.0,
    )


@pytest.fixture
def venue() -> VenueConfig:
    """Create a sample venue config."""
    return VenueConfig(name=VenueName.POLYMARKET, fee_bps=10.0, tick_size=0.01)


@pytest.fixture
def portfolio() -> Portfolio:
    """Create a basic portfolio."""
    return Portfolio(cash=1_000.0, starting_capital=1_000.0)


def test_venue_config_validation() -> None:
    """Venue config rejects invalid constraints."""
    with pytest.raises(ValueError, match="min_order_size"):
        VenueConfig(name=VenueName.KALSHI, min_order_size=0)


def test_registry_round_trip() -> None:
    """Strategy registry can register and instantiate strategies."""
    registry = StrategyRegistry()
    registry.register(
        "static",
        factory=lambda **_: StaticStrategy(signal=None, orders=[]),
        description="Static test strategy",
    )

    strategy = registry.create("static")

    assert strategy.name == "static"
    assert registry.names() == ("static",)


def test_agent_skips_when_strategy_has_no_signal(
    market: MarketState,
    venue: VenueConfig,
    portfolio: Portfolio,
) -> None:
    """Agent should skip if strategy does not emit a signal."""
    agent = PredictionMarketAgent(strategy=StaticStrategy(signal=None, orders=[]))

    decision = agent.evaluate_market(market, venue=venue, portfolio=portfolio)

    assert decision.status == DecisionStatus.SKIP
    assert decision.reasons == ("strategy_returned_no_signal",)


def test_agent_respects_signal_confidence_floor(
    market: MarketState,
    venue: VenueConfig,
    portfolio: Portfolio,
) -> None:
    """Agent should skip low-confidence signals before order generation."""
    signal = MarketSignal(fair_prob=0.60, confidence=0.40)
    agent = PredictionMarketAgent(
        strategy=StaticStrategy(signal=signal, orders=[]),
        config=AgentRunConfig(min_signal_confidence=0.5),
    )

    decision = agent.evaluate_market(market, venue=venue, portfolio=portfolio)

    assert decision.status == DecisionStatus.SKIP
    assert decision.reasons == ("signal_below_confidence_floor",)


def test_agent_holds_when_signal_has_no_orders(
    market: MarketState,
    venue: VenueConfig,
    portfolio: Portfolio,
) -> None:
    """Agent should hold when a signal exists but produces no executable orders."""
    signal = MarketSignal(fair_prob=0.60, confidence=0.75)
    agent = PredictionMarketAgent(strategy=StaticStrategy(signal=signal, orders=[]))

    decision = agent.evaluate_market(market, venue=venue, portfolio=portfolio)

    assert decision.status == DecisionStatus.HOLD
    assert decision.signal == signal


def test_agent_trades_with_executable_orders(
    market: MarketState,
    venue: VenueConfig,
    portfolio: Portfolio,
) -> None:
    """Agent should return trade decisions when orders are present."""
    signal = MarketSignal(fair_prob=0.62, confidence=0.85)
    order = Order(
        market_id=market.market_id,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=10.0,
        limit_price=0.45,
    )
    agent = PredictionMarketAgent(strategy=StaticStrategy(signal=signal, orders=[order]))

    decision = agent.evaluate_market(market, venue=venue, portfolio=portfolio)

    assert decision.status == DecisionStatus.TRADE
    assert decision.orders == (order,)
    assert decision.should_trade


def test_legacy_adapter_generates_signal_and_order(
    market: MarketState,
    venue: VenueConfig,
    portfolio: Portfolio,
) -> None:
    """Legacy adapter should make the new scaffold usable immediately."""
    strategy = LegacyMispricedStrategyAdapter()
    agent = PredictionMarketAgent(strategy=strategy)

    decision = agent.evaluate_market(
        market,
        venue=venue,
        portfolio=portfolio,
        context_metadata={"probability_model": MockProbabilityModel(0.70, 0.9)},
    )

    assert decision.signal is not None
    assert decision.signal.fair_prob == pytest.approx(0.70)
    assert decision.status == DecisionStatus.TRADE
    assert len(decision.orders) == 1
    assert decision.orders[0].side == OrderSide.BUY
