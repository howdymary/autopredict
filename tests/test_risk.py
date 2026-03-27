"""Tests for risk management system."""

from datetime import datetime, timedelta

import pytest

from autopredict.config import RiskConfig
from autopredict.live.risk import RiskManager, Position
from autopredict.live.trader import Order


class TestRiskManager:
    """Test RiskManager risk checks and limits."""

    def test_initialization(self):
        """Test risk manager initialization."""
        config = RiskConfig()
        risk_mgr = RiskManager(config)

        assert risk_mgr.daily_pnl == 0.0
        assert risk_mgr.total_pnl == 0.0
        assert risk_mgr.current_exposure == 0.0
        assert not risk_mgr.is_kill_switch_active()

    def test_position_size_limit(self):
        """Test that position size limit is enforced."""
        config = RiskConfig(max_position_per_market=100.0)
        risk_mgr = RiskManager(config)

        # Order within limit should pass
        order = Order(
            market_id="test_market",
            side="buy",
            order_type="market",
            size=50.0,
        )
        result = risk_mgr.check_order(order, current_price=0.5)
        assert result.passed

        # Simulate existing position
        risk_mgr.update_position("test_market", 60.0, 0.5)

        # Order that would exceed limit should fail
        order2 = Order(
            market_id="test_market",
            side="buy",
            order_type="market",
            size=50.0,
        )
        result = risk_mgr.check_order(order2, current_price=0.5)
        assert not result.passed
        assert "Position limit exceeded" in result.reason

    def test_total_exposure_limit(self):
        """Test that total exposure limit is enforced."""
        config = RiskConfig(max_total_exposure=100.0, max_position_per_market=500.0)
        risk_mgr = RiskManager(config)

        # First order should pass
        order1 = Order(
            market_id="market1",
            side="buy",
            order_type="market",
            size=100.0,
        )
        result = risk_mgr.check_order(order1, current_price=0.5)
        assert result.passed

        # Simulate execution (exposure = 100 * 0.5 = 50)
        risk_mgr.update_position("market1", 100.0, 0.5)

        # Second order that exceeds total exposure should fail
        # This order would add 300 * 0.5 = 150, total = 200 > 100 limit
        order2 = Order(
            market_id="market2",
            side="buy",
            order_type="market",
            size=300.0,
        )
        result = risk_mgr.check_order(order2, current_price=0.5)
        assert not result.passed
        assert "Total exposure limit exceeded" in result.reason

    def test_daily_loss_limit(self):
        """Test that daily loss limit is enforced."""
        config = RiskConfig(max_daily_loss=50.0, kill_switch_threshold=-200.0)
        risk_mgr = RiskManager(config)

        # Simulate a losing trade
        risk_mgr.update_position("market1", 100.0, 0.5, pnl_delta=-60.0)

        # New order should be blocked due to daily loss limit
        order = Order(
            market_id="market2",
            side="buy",
            order_type="market",
            size=50.0,
        )
        result = risk_mgr.check_order(order, current_price=0.5)
        assert not result.passed
        assert "Daily loss limit exceeded" in result.reason

    def test_kill_switch_activation(self):
        """Test kill switch activation on severe losses."""
        config = RiskConfig(
            max_daily_loss=50.0,
            kill_switch_threshold=-100.0,
            enable_kill_switch=True,
        )
        risk_mgr = RiskManager(config)

        # Simulate severe loss that triggers kill switch
        risk_mgr.update_position("market1", 100.0, 0.5, pnl_delta=-150.0)

        # Now trigger kill switch by checking an order
        order_test = Order(
            market_id="market1",
            side="buy",
            order_type="market",
            size=10.0,
        )
        result_test = risk_mgr.check_order(order_test, current_price=0.5)

        # Kill switch should now be active
        assert risk_mgr.is_kill_switch_active()

        # All orders should be blocked
        order = Order(
            market_id="market2",
            side="buy",
            order_type="market",
            size=10.0,
        )
        result = risk_mgr.check_order(order, current_price=0.5)
        assert not result.passed
        assert "Kill switch" in result.reason

    def test_manual_kill_switch(self):
        """Test manual kill switch activation."""
        config = RiskConfig()
        risk_mgr = RiskManager(config)

        assert not risk_mgr.is_kill_switch_active()

        # Manually activate kill switch
        risk_mgr.manual_kill_switch("Testing manual activation")

        assert risk_mgr.is_kill_switch_active()

        # Orders should be blocked
        order = Order(
            market_id="test",
            side="buy",
            order_type="market",
            size=10.0,
        )
        result = risk_mgr.check_order(order, current_price=0.5)
        assert not result.passed

    def test_kill_switch_reset(self):
        """Test kill switch reset with confirmation."""
        config = RiskConfig()
        risk_mgr = RiskManager(config)

        risk_mgr.manual_kill_switch("Test")
        assert risk_mgr.is_kill_switch_active()

        # Wrong confirmation should fail
        assert not risk_mgr.reset_kill_switch("wrong confirmation")
        assert risk_mgr.is_kill_switch_active()

        # Correct confirmation should succeed
        assert risk_mgr.reset_kill_switch("RESET KILL SWITCH")
        assert not risk_mgr.is_kill_switch_active()

    def test_max_positions_limit(self):
        """Test maximum number of positions limit."""
        config = RiskConfig(max_positions=3)
        risk_mgr = RiskManager(config)

        # Fill up to max positions
        for i in range(3):
            risk_mgr.update_position(f"market{i}", 10.0, 0.5)

        # New position should be blocked
        order = Order(
            market_id="market_new",
            side="buy",
            order_type="market",
            size=10.0,
        )
        result = risk_mgr.check_order(order, current_price=0.5)
        assert not result.passed
        assert "Maximum positions limit exceeded" in result.reason

        # Order for existing position should still work
        order2 = Order(
            market_id="market0",
            side="buy",
            order_type="market",
            size=10.0,
        )
        result2 = risk_mgr.check_order(order2, current_price=0.5)
        assert result2.passed

    def test_position_update_and_pnl(self):
        """Test position updates and P&L calculation."""
        config = RiskConfig()
        risk_mgr = RiskManager(config)

        # Open position
        risk_mgr.update_position("market1", 100.0, 0.50, pnl_delta=0.0)
        assert "market1" in risk_mgr.positions
        assert risk_mgr.positions["market1"].size == 100.0
        assert risk_mgr.positions["market1"].entry_price == 0.50

        # Add to position
        risk_mgr.update_position("market1", 50.0, 0.55, pnl_delta=0.0)
        # Average entry price should be updated
        position = risk_mgr.positions["market1"]
        assert position.size == 150.0
        expected_avg = (100.0 * 0.50 + 50.0 * 0.55) / 150.0
        assert abs(position.entry_price - expected_avg) < 0.001

        # Close part of position with profit
        risk_mgr.update_position("market1", -75.0, 0.60, pnl_delta=7.5)
        assert risk_mgr.daily_pnl == 7.5
        assert risk_mgr.total_pnl == 7.5
        assert risk_mgr.positions["market1"].size == 75.0

        # Close entire position
        risk_mgr.update_position("market1", -75.0, 0.60, pnl_delta=7.5)
        assert "market1" not in risk_mgr.positions
        assert risk_mgr.daily_pnl == 15.0

    def test_position_timeout_check(self):
        """Test position timeout detection."""
        config = RiskConfig(position_timeout_hours=24.0)
        risk_mgr = RiskManager(config)

        # Create position with old entry time
        old_time = datetime.now() - timedelta(hours=30)
        position = Position(
            market_id="old_market",
            size=100.0,
            entry_price=0.5,
            current_price=0.5,
            entry_time=old_time,
        )
        risk_mgr.positions["old_market"] = position

        # Check for timeouts
        expired = risk_mgr.check_position_timeouts()
        assert "old_market" in expired

    def test_exposure_calculation(self):
        """Test current exposure calculation."""
        config = RiskConfig()
        risk_mgr = RiskManager(config)

        assert risk_mgr.get_current_exposure() == 0.0

        # Add position
        risk_mgr.update_position("market1", 100.0, 0.50)
        assert risk_mgr.get_current_exposure() == 50.0  # 100 * 0.50

        # Add another position
        risk_mgr.update_position("market2", 200.0, 0.30)
        assert risk_mgr.get_current_exposure() == 110.0  # 50 + 60

    def test_positions_summary(self):
        """Test positions summary report."""
        config = RiskConfig()
        risk_mgr = RiskManager(config)

        risk_mgr.update_position("market1", 100.0, 0.50, pnl_delta=10.0)
        risk_mgr.update_position("market2", 50.0, 0.60, pnl_delta=-5.0)

        summary = risk_mgr.get_positions_summary()

        assert summary["num_positions"] == 2
        assert summary["daily_pnl"] == 5.0
        assert summary["total_pnl"] == 5.0
        assert "market1" in summary["positions"]
        assert "market2" in summary["positions"]


class TestPosition:
    """Test Position class."""

    def test_position_creation(self):
        """Test position creation."""
        pos = Position(
            market_id="test",
            size=100.0,
            entry_price=0.50,
            current_price=0.50,
        )

        assert pos.market_id == "test"
        assert pos.size == 100.0
        assert pos.entry_price == 0.50
        assert pos.unrealized_pnl == 0.0

    def test_long_position_pnl(self):
        """Test P&L calculation for long position."""
        pos = Position(
            market_id="test",
            size=100.0,
            entry_price=0.50,
            current_price=0.50,
        )

        # Price increases - profit
        pos.update_price(0.60)
        assert abs(pos.unrealized_pnl - 10.0) < 0.01  # 100 * (0.60 - 0.50)

        # Price decreases - loss
        pos.update_price(0.40)
        assert abs(pos.unrealized_pnl - (-10.0)) < 0.01  # 100 * (0.40 - 0.50)

    def test_short_position_pnl(self):
        """Test P&L calculation for short position."""
        pos = Position(
            market_id="test",
            size=-100.0,  # Short position
            entry_price=0.50,
            current_price=0.50,
        )

        # Price decreases - profit for short
        pos.update_price(0.40)
        assert abs(pos.unrealized_pnl - 10.0) < 0.01  # 100 * (0.50 - 0.40)

        # Price increases - loss for short
        pos.update_price(0.60)
        assert abs(pos.unrealized_pnl - (-10.0)) < 0.01  # 100 * (0.50 - 0.60)

    def test_position_timeout(self):
        """Test position timeout detection."""
        old_time = datetime.now() - timedelta(hours=25)
        pos = Position(
            market_id="test",
            size=100.0,
            entry_price=0.50,
            current_price=0.50,
            entry_time=old_time,
        )

        assert pos.is_expired(timeout_hours=24.0)
        assert not pos.is_expired(timeout_hours=48.0)
