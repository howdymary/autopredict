"""Tests for MispricedProbabilityStrategy."""

import pytest
from datetime import datetime, timedelta

from autopredict.core.types import (
    EdgeEstimate,
    MarketCategory,
    MarketState,
    OrderSide,
    OrderType,
    Portfolio,
    Position,
)
from autopredict.strategies.mispriced_probability import MispricedProbabilityStrategy
from autopredict.strategies.base import RiskLimits


class MockProbabilityModel:
    """Mock probability model for testing."""

    def __init__(self, fair_prob: float, confidence: float = 0.8):
        self.fair_prob = fair_prob
        self.confidence = confidence

    def predict(self, market: MarketState) -> dict:
        return {
            "probability": self.fair_prob,
            "confidence": self.confidence,
        }


class TestMispricedProbabilityStrategy:
    """Tests for MispricedProbabilityStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create strategy with default settings."""
        return MispricedProbabilityStrategy(
            risk_limits=RiskLimits(
                max_position_size=500.0,
                max_total_exposure=5000.0,
                min_edge_threshold=0.05,
                min_confidence=0.7,
            ),
            kelly_fraction=0.25,
        )

    @pytest.fixture
    def market(self):
        """Create sample market."""
        return MarketState(
            market_id="test-123",
            question="Test market",
            market_prob=0.50,
            expiry=datetime.now() + timedelta(days=7),
            category=MarketCategory.OTHER,
            best_bid=0.49,
            best_ask=0.51,
            bid_liquidity=1000.0,
            ask_liquidity=1000.0,
            volume_24h=5000.0,
        )

    @pytest.fixture
    def portfolio(self):
        """Create sample portfolio."""
        return Portfolio(cash=10000.0, starting_capital=10000.0)

    def test_estimate_edge(self, strategy, market):
        """Test edge estimation."""
        model = MockProbabilityModel(fair_prob=0.70, confidence=0.85)
        config = {"probability_model": model}

        edge = strategy.estimate_edge(market, config)

        assert edge is not None
        assert edge.fair_prob == 0.70
        assert edge.market_prob == 0.50
        assert abs(edge.edge - 0.20) < 1e-9
        assert edge.confidence == 0.85

    def test_no_edge_below_threshold(self, strategy, market, portfolio):
        """Test that strategy skips trades below edge threshold."""
        # Model predicts 0.54, market at 0.50 -> edge = 0.04 < 0.05 threshold
        model = MockProbabilityModel(fair_prob=0.54, confidence=0.8)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, None, config)

        assert len(orders) == 0

    def test_trade_with_sufficient_edge(self, strategy, market, portfolio):
        """Test that strategy trades with sufficient edge."""
        # Model predicts 0.60, market at 0.50 -> edge = 0.10 > 0.05 threshold
        model = MockProbabilityModel(fair_prob=0.60, confidence=0.85)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, None, config)

        assert len(orders) == 1
        order = orders[0]
        assert order.side == OrderSide.BUY  # Edge is positive
        assert order.size > 0

    def test_position_sizing_kelly(self, strategy, market, portfolio):
        """Test Kelly-based position sizing."""
        # Edge = 0.20, fair_prob = 0.70
        # Kelly = 0.20 / (1 - 0.70) = 0.20 / 0.30 = 0.667
        # Fractional Kelly (0.25) = 0.1667
        # Base size = 10000 * 0.1667 = 1667
        # With confidence 0.85: 1667 * 0.85 = 1417
        # Capped by max_position_size = 500
        model = MockProbabilityModel(fair_prob=0.70, confidence=0.85)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, None, config)

        assert len(orders) == 1
        order = orders[0]
        # Should be capped at 500
        assert order.size <= 500.0

    def test_respects_max_position_size(self, strategy, market, portfolio):
        """Test that position size respects max limit."""
        # Very large edge should still be capped
        model = MockProbabilityModel(fair_prob=0.95, confidence=0.9)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, None, config)

        assert len(orders) == 1
        order = orders[0]
        assert order.size <= strategy.risk_limits.max_position_size

    def test_respects_liquidity_constraints(self, strategy, portfolio):
        """Test that position size respects liquidity."""
        # Market with low liquidity
        low_liquidity_market = MarketState(
            market_id="test-low-liq",
            question="Low liquidity market",
            market_prob=0.50,
            expiry=datetime.now() + timedelta(days=7),
            category=MarketCategory.OTHER,
            best_bid=0.49,
            best_ask=0.51,
            bid_liquidity=50.0,  # Very low
            ask_liquidity=100.0,
        )

        model = MockProbabilityModel(fair_prob=0.70, confidence=0.85)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(low_liquidity_market, None, config)

        if len(orders) > 0:
            order = orders[0]
            # Should not exceed 20% of available liquidity (100.0 * 0.20 = 20.0)
            assert order.size <= 20.0

    def test_chooses_market_order_for_large_edge(self, strategy, market, portfolio):
        """Test that strategy uses market orders for large edges."""
        # Very large edge (0.20 > 0.15 threshold)
        model = MockProbabilityModel(fair_prob=0.70, confidence=0.85)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, None, config)

        assert len(orders) == 1
        order = orders[0]
        # Edge = 0.20 > 0.15 threshold -> should use market order
        assert order.order_type == OrderType.MARKET

    def test_chooses_limit_order_for_moderate_edge(self, strategy, market, portfolio):
        """Test that strategy uses limit orders for moderate edges."""
        # Moderate edge (0.06 < 0.15 threshold)
        # Spread is 0.02, so edge/spread = 0.06/0.02 = 3.0 (at threshold)
        # Use slightly smaller edge to ensure limit order
        model = MockProbabilityModel(fair_prob=0.555, confidence=0.85)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, None, config)

        assert len(orders) == 1
        order = orders[0]
        # Edge = 0.055 < 0.15 threshold and edge/spread < 3.0 -> should use limit order
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price is not None

    def test_exit_position_on_edge_reversal(self, strategy, market, portfolio):
        """Test that strategy exits position when edge reverses."""
        # Existing long position
        position = Position(
            market_id="test-123",
            size=100.0,
            entry_price=0.60,
            current_price=0.50,
        )

        # Edge has reversed (fair_prob < market_prob)
        model = MockProbabilityModel(fair_prob=0.40, confidence=0.85)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, position, config)

        assert len(orders) == 1
        order = orders[0]
        # Should exit (sell) the long position
        assert order.side == OrderSide.SELL
        assert order.size == 100.0

    def test_no_trade_below_confidence_threshold(self, strategy, market, portfolio):
        """Test that strategy skips trades below confidence threshold."""
        # Good edge but low confidence
        model = MockProbabilityModel(fair_prob=0.70, confidence=0.6)  # < 0.7 threshold
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, None, config)

        assert len(orders) == 0

    def test_no_trade_with_insufficient_liquidity(self, strategy, portfolio):
        """Test that strategy skips markets with insufficient liquidity."""
        # Market with very low liquidity
        thin_market = MarketState(
            market_id="test-thin",
            question="Thin market",
            market_prob=0.50,
            expiry=datetime.now() + timedelta(days=7),
            category=MarketCategory.OTHER,
            best_bid=0.49,
            best_ask=0.51,
            bid_liquidity=50.0,
            ask_liquidity=40.0,  # Total = 90 < 100 minimum
        )

        model = MockProbabilityModel(fair_prob=0.70, confidence=0.85)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(thin_market, None, config)

        assert len(orders) == 0

    def test_limit_price_inside_spread(self, strategy, market, portfolio):
        """Test that limit orders are placed inside the spread."""
        # Moderate edge to trigger limit order
        model = MockProbabilityModel(fair_prob=0.58, confidence=0.85)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, None, config)

        assert len(orders) == 1
        order = orders[0]

        if order.order_type == OrderType.LIMIT:
            # Limit price should be between best_bid and mid_price for buys
            if order.side == OrderSide.BUY:
                assert market.best_bid < order.limit_price <= market.mid_price
            # Limit price should be between mid_price and best_ask for sells
            else:
                assert market.mid_price <= order.limit_price < market.best_ask

    def test_doesnt_add_to_position_in_opposite_direction(self, strategy, market, portfolio):
        """Test that strategy doesn't add to position in opposite direction."""
        # Existing long position
        position = Position(
            market_id="test-123",
            size=100.0,
            entry_price=0.60,
            current_price=0.50,
        )

        # Edge favors selling, but not strong enough to exit
        model = MockProbabilityModel(fair_prob=0.48, confidence=0.85)
        config = {"probability_model": model, "portfolio": portfolio}

        orders = strategy.decide(market, position, config)

        # Should not generate new order (edge not strong enough to exit)
        # and shouldn't open opposite position
        assert len(orders) == 0 or (len(orders) == 1 and orders[0].side == OrderSide.SELL)
