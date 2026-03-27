"""Tests for trading execution (paper and live)."""

import pytest

from autopredict.live.trader import Order, PaperTrader, ExecutionReport


class TestOrder:
    """Test Order validation."""

    def test_valid_market_order(self):
        """Test valid market order."""
        order = Order(
            market_id="test",
            side="buy",
            order_type="market",
            size=100.0,
        )
        order.validate()  # Should not raise

    def test_valid_limit_order(self):
        """Test valid limit order."""
        order = Order(
            market_id="test",
            side="sell",
            order_type="limit",
            size=50.0,
            limit_price=0.55,
        )
        order.validate()  # Should not raise

    def test_invalid_side(self):
        """Test that invalid side raises error."""
        order = Order(
            market_id="test",
            side="invalid",
            order_type="market",
            size=100.0,
        )
        with pytest.raises(ValueError, match="side must be"):
            order.validate()

    def test_invalid_order_type(self):
        """Test that invalid order type raises error."""
        order = Order(
            market_id="test",
            side="buy",
            order_type="invalid",
            size=100.0,
        )
        with pytest.raises(ValueError, match="order_type must be"):
            order.validate()

    def test_negative_size(self):
        """Test that negative size raises error."""
        order = Order(
            market_id="test",
            side="buy",
            order_type="market",
            size=-10.0,
        )
        with pytest.raises(ValueError, match="size must be positive"):
            order.validate()

    def test_limit_order_requires_price(self):
        """Test that limit orders require limit_price."""
        order = Order(
            market_id="test",
            side="buy",
            order_type="limit",
            size=100.0,
            limit_price=None,
        )
        with pytest.raises(ValueError, match="limit_price required"):
            order.validate()

    def test_invalid_limit_price(self):
        """Test that limit price must be in (0, 1) for binary markets."""
        order = Order(
            market_id="test",
            side="buy",
            order_type="limit",
            size=100.0,
            limit_price=1.5,
        )
        with pytest.raises(ValueError, match="limit_price must be in"):
            order.validate()


class TestPaperTrader:
    """Test PaperTrader simulation."""

    def test_initialization(self):
        """Test paper trader initialization."""
        trader = PaperTrader(
            commission_rate=0.01,
            slippage_bps=5.0,
        )

        assert trader.commission_rate == 0.01
        assert trader.slippage_bps == 5.0
        assert len(trader.trade_history) == 0
        assert len(trader.positions) == 0

    def test_market_order_buy(self):
        """Test market order execution (buy side)."""
        trader = PaperTrader(commission_rate=0.01, slippage_bps=10.0)

        order = Order(
            market_id="test",
            side="buy",
            order_type="market",
            size=100.0,
        )

        report = trader.place_order(order, current_price=0.50)

        assert report.filled
        assert report.execution_mode == "paper"
        assert report.fill_size == 100.0
        # Buy order should have positive slippage (worse price)
        assert report.fill_price > 0.50
        assert report.commission == 1.0  # 100 * 0.01

    def test_market_order_sell(self):
        """Test market order execution (sell side)."""
        trader = PaperTrader(commission_rate=0.01, slippage_bps=10.0)

        order = Order(
            market_id="test",
            side="sell",
            order_type="market",
            size=100.0,
        )

        report = trader.place_order(order, current_price=0.50)

        assert report.filled
        # Sell order should have negative slippage (worse price)
        assert report.fill_price < 0.50
        assert report.commission == 1.0

    def test_limit_order_execution(self):
        """Test limit order execution."""
        trader = PaperTrader(commission_rate=0.01, limit_fill_rate=1.0)

        order = Order(
            market_id="test",
            side="buy",
            order_type="limit",
            size=100.0,
            limit_price=0.55,
        )

        # Limit order at better price should fill
        report = trader.place_order(order, current_price=0.50)

        assert report.filled
        assert report.fill_price == 0.55  # Fill at limit price
        assert report.slippage_bps == 0.0  # No slippage on limit orders

    def test_limit_order_no_fill(self):
        """Test limit order that doesn't fill."""
        trader = PaperTrader(commission_rate=0.01, limit_fill_rate=0.0)

        order = Order(
            market_id="test",
            side="buy",
            order_type="limit",
            size=100.0,
            limit_price=0.45,  # Below market
        )

        report = trader.place_order(order, current_price=0.50)

        # Should not fill (limit_fill_rate=0.0)
        assert not report.filled
        assert report.fill_price is None

    def test_position_tracking(self):
        """Test position tracking across trades."""
        trader = PaperTrader(commission_rate=0.01)

        # Buy
        order1 = Order(
            market_id="test",
            side="buy",
            order_type="market",
            size=100.0,
        )
        trader.place_order(order1, current_price=0.50)

        assert trader.get_position("test") == 100.0

        # Sell
        order2 = Order(
            market_id="test",
            side="sell",
            order_type="market",
            size=30.0,
        )
        trader.place_order(order2, current_price=0.55)

        assert trader.get_position("test") == 70.0  # 100 - 30

    def test_trade_history(self):
        """Test trade history recording."""
        trader = PaperTrader()

        order = Order(
            market_id="test",
            side="buy",
            order_type="market",
            size=100.0,
        )
        trader.place_order(order, current_price=0.50)

        history = trader.get_trade_history()
        assert len(history) == 1
        assert history[0].order.market_id == "test"

    def test_total_commission(self):
        """Test total commission calculation."""
        trader = PaperTrader(commission_rate=0.01)

        for i in range(5):
            order = Order(
                market_id=f"market{i}",
                side="buy",
                order_type="market",
                size=100.0,
            )
            trader.place_order(order, current_price=0.50)

        total_commission = trader.get_total_commission_paid()
        assert total_commission == 5.0  # 5 trades * 1.0 commission each

    def test_limit_order_randomness_is_seeded(self):
        """Paper limit fills should be reproducible with the same seed."""
        trader_a = PaperTrader(limit_fill_rate=0.5, seed=7)
        trader_b = PaperTrader(limit_fill_rate=0.5, seed=7)

        order_a = Order(
            market_id="test",
            side="buy",
            order_type="limit",
            size=100.0,
            limit_price=0.45,
        )
        order_b = Order(
            market_id="test",
            side="buy",
            order_type="limit",
            size=100.0,
            limit_price=0.45,
        )

        results_a = [trader_a.place_order(order_a, current_price=0.50).filled for _ in range(5)]
        results_b = [trader_b.place_order(order_b, current_price=0.50).filled for _ in range(5)]

        assert results_a == results_b


class TestExecutionReport:
    """Test ExecutionReport functionality."""

    def test_is_success(self):
        """Test is_success method."""
        order = Order(
            market_id="test",
            side="buy",
            order_type="market",
            size=100.0,
        )

        # Successful fill
        report1 = ExecutionReport(
            order=order,
            filled=True,
            fill_price=0.50,
            error_message=None,
        )
        assert report1.is_success()

        # Failed fill
        report2 = ExecutionReport(
            order=order,
            filled=False,
            error_message="Insufficient liquidity",
        )
        assert not report2.is_success()

    def test_net_proceeds(self):
        """Test net proceeds calculation."""
        order = Order(
            market_id="test",
            side="buy",
            order_type="market",
            size=100.0,
        )

        report = ExecutionReport(
            order=order,
            filled=True,
            fill_price=0.50,
            fill_size=100.0,
            commission=1.0,
        )

        # Gross = 100 * 0.50 = 50.0
        # Net = 50.0 - 1.0 = 49.0
        assert report.get_net_proceeds() == 49.0

    def test_unfilled_net_proceeds(self):
        """Test net proceeds for unfilled order."""
        order = Order(
            market_id="test",
            side="buy",
            order_type="market",
            size=100.0,
        )

        report = ExecutionReport(
            order=order,
            filled=False,
        )

        assert report.get_net_proceeds() == 0.0
