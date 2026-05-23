"""Tests for core types."""

from datetime import datetime, timedelta, timezone

import pytest

from autopredict.core.types import (
    EdgeEstimate,
    ExecutionReport,
    MarketCategory,
    MarketState,
    Order,
    OrderSide,
    OrderType,
    Position,
    Portfolio,
)


class TestMarketState:
    """Tests for MarketState dataclass."""

    def test_market_state_creation(self):
        """Test creating a valid MarketState."""
        expiry = datetime.now() + timedelta(days=7)
        state = MarketState(
            market_id="test-123",
            question="Will this test pass?",
            market_prob=0.65,
            expiry=expiry,
            category=MarketCategory.OTHER,
            best_bid=0.64,
            best_ask=0.66,
            bid_liquidity=1000.0,
            ask_liquidity=900.0,
        )

        assert state.market_id == "test-123"
        assert state.market_prob == 0.65
        assert abs(state.spread - 0.02) < 1e-9
        assert abs(state.mid_price - 0.65) < 1e-9
        assert state.total_liquidity == 1900.0

    def test_market_state_validation(self):
        """Test MarketState validation."""
        expiry = datetime.now() + timedelta(days=7)

        # Invalid probability
        with pytest.raises(ValueError, match="market_prob"):
            MarketState(
                market_id="test",
                question="Test",
                market_prob=1.5,
                expiry=expiry,
                category=MarketCategory.OTHER,
                best_bid=0.5,
                best_ask=0.5,
                bid_liquidity=100,
                ask_liquidity=100,
            )

        # Bid > ask
        with pytest.raises(ValueError, match="best_bid"):
            MarketState(
                market_id="test",
                question="Test",
                market_prob=0.5,
                expiry=expiry,
                category=MarketCategory.OTHER,
                best_bid=0.7,
                best_ask=0.6,
                bid_liquidity=100,
                ask_liquidity=100,
            )

        # Negative liquidity
        with pytest.raises(ValueError, match="liquidity"):
            MarketState(
                market_id="test",
                question="Test",
                market_prob=0.5,
                expiry=expiry,
                category=MarketCategory.OTHER,
                best_bid=0.4,
                best_ask=0.6,
                bid_liquidity=-100,
                ask_liquidity=100,
            )

    def test_spread_bps(self):
        """Test spread calculation in basis points."""
        expiry = datetime.now() + timedelta(days=7)
        state = MarketState(
            market_id="test",
            question="Test",
            market_prob=0.5,
            expiry=expiry,
            category=MarketCategory.OTHER,
            best_bid=0.49,
            best_ask=0.51,
            bid_liquidity=100,
            ask_liquidity=100,
        )

        # Spread = 0.02, mid = 0.5, bps = 0.02 / 0.5 * 10000 = 400
        assert abs(state.spread_bps - 400.0) < 1.0

    def test_time_to_expiry_hours_supports_timezone_aware_expiry(self):
        """Live venue markets can carry timezone-aware expiries without crashing."""
        state = MarketState(
            market_id="aware-market",
            question="Will this test remain timezone safe?",
            market_prob=0.5,
            expiry=datetime.now(timezone.utc) + timedelta(hours=12),
            category=MarketCategory.OTHER,
            best_bid=0.49,
            best_ask=0.51,
            bid_liquidity=100.0,
            ask_liquidity=100.0,
        )

        assert 0.0 < state.time_to_expiry_hours <= 12.1


class TestEdgeEstimate:
    """Tests for EdgeEstimate."""

    def test_edge_estimate_creation(self):
        """Test creating EdgeEstimate."""
        edge = EdgeEstimate(
            market_id="test-123",
            fair_prob=0.75,
            market_prob=0.65,
            confidence=0.85,
        )

        assert abs(edge.edge - 0.10) < 1e-9
        assert abs(edge.abs_edge - 0.10) < 1e-9
        assert abs(edge.edge_bps - 1000.0) < 1e-6
        assert edge.direction == OrderSide.BUY

    def test_edge_direction(self):
        """Test edge direction determination."""
        # Positive edge -> BUY
        edge_up = EdgeEstimate(
            market_id="test",
            fair_prob=0.75,
            market_prob=0.65,
            confidence=0.8,
        )
        assert edge_up.direction == OrderSide.BUY

        # Negative edge -> SELL
        edge_down = EdgeEstimate(
            market_id="test",
            fair_prob=0.55,
            market_prob=0.65,
            confidence=0.8,
        )
        assert edge_down.direction == OrderSide.SELL


class TestOrder:
    """Tests for Order."""

    def test_limit_order_creation(self):
        """Test creating a limit order."""
        order = Order(
            market_id="test-123",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=100.0,
            limit_price=0.65,
        )

        assert order.market_id == "test-123"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.size == 100.0
        assert order.limit_price == 0.65

    def test_market_order_creation(self):
        """Test creating a market order."""
        order = Order(
            market_id="test-123",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            size=50.0,
        )

        assert order.order_type == OrderType.MARKET
        assert order.limit_price is None

    def test_order_validation(self):
        """Test order validation."""
        # Negative size
        with pytest.raises(ValueError, match="size"):
            Order(
                market_id="test",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                size=-100.0,
            )

        # Limit order without price
        with pytest.raises(ValueError, match="limit_price"):
            Order(
                market_id="test",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                size=100.0,
            )

        # Market order with price
        with pytest.raises(ValueError, match="limit_price"):
            Order(
                market_id="test",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                size=100.0,
                limit_price=0.5,
            )


class TestPosition:
    """Tests for Position."""

    def test_position_pnl(self):
        """Test position PnL calculation."""
        position = Position(
            market_id="test-123",
            size=100.0,
            entry_price=0.60,
            current_price=0.70,
        )

        # Long 100 @ 0.60, current 0.70
        # PnL = 100 * (0.70 - 0.60) = 10.0
        assert abs(position.unrealized_pnl - 10.0) < 1e-9
        assert abs(position.unrealized_pnl_pct - 0.1667) < 0.001

    def test_short_position(self):
        """Test short position PnL."""
        position = Position(
            market_id="test-123",
            size=-100.0,
            entry_price=0.70,
            current_price=0.60,
        )

        # Short 100 @ 0.70, current 0.60
        # PnL = -100 * (0.60 - 0.70) = 10.0
        assert abs(position.unrealized_pnl - 10.0) < 1e-9
        assert position.is_short


class TestPortfolio:
    """Tests for Portfolio."""

    def test_portfolio_creation(self):
        """Test creating a portfolio."""
        portfolio = Portfolio(
            cash=10000.0,
            starting_capital=10000.0,
        )

        assert portfolio.total_value == 10000.0
        assert portfolio.total_pnl == 0.0
        assert portfolio.num_positions == 0

    def test_portfolio_with_positions(self):
        """Test portfolio with positions."""
        portfolio = Portfolio(
            cash=9000.0,
            starting_capital=10000.0,
        )

        # Add profitable position
        position1 = Position(
            market_id="market-1",
            size=100.0,
            entry_price=0.60,
            current_price=0.70,
        )
        portfolio.add_position(position1)

        # Add losing position
        position2 = Position(
            market_id="market-2",
            size=100.0,
            entry_price=0.80,
            current_price=0.75,
        )
        portfolio.add_position(position2)

        # Total unrealized PnL = 10.0 + (-5.0) = 5.0
        # Total value = 9000 + 5.0 = 9005.0
        # Total PnL = total_value - starting_capital = 9005.0 - 10000.0 = -995.0
        assert portfolio.num_positions == 2
        assert abs(portfolio.total_value - 9005.0) < 1e-9
        assert abs(portfolio.total_pnl - (-995.0)) < 1e-9

    def test_portfolio_leverage(self):
        """Test portfolio leverage calculation."""
        portfolio = Portfolio(
            cash=5000.0,
            starting_capital=10000.0,
        )

        # Add position worth $7000 notional
        position = Position(
            market_id="market-1",
            size=10000.0,
            entry_price=0.70,
            current_price=0.70,
        )
        portfolio.add_position(position)

        # Leverage = position_value / total_value
        # position_value = 10000 * 0.70 = 7000
        # total_value = 5000 + 0 (no PnL) = 5000
        # leverage = 7000 / 5000 = 1.4
        assert abs(portfolio.leverage - 1.4) < 0.01


class TestExecutionReport:
    """Tests for ExecutionReport."""

    def test_execution_report(self):
        """Test ExecutionReport creation and properties."""
        order = Order(
            market_id="test",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=100.0,
            limit_price=0.65,
        )

        report = ExecutionReport(
            order=order,
            filled_size=80.0,
            avg_fill_price=0.652,
            fills=[(0.65, 50.0), (0.654, 30.0)],
            slippage_bps=20.0,
            fee_total=0.20,
        )

        assert report.fill_rate == 0.8
        assert report.notional == 80.0 * 0.652
        assert report.total_cost == 80.0 * 0.652 + 0.20
        assert not report.is_complete
