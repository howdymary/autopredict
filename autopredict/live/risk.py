"""Risk management system for live trading.

Enforces position limits, exposure caps, and circuit breakers to protect capital.
All limits are checked before trades are executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..config.schema import RiskConfig
from .trader import Order


@dataclass
class Position:
    """Represents an open position.

    Attributes:
        market_id: Market identifier
        size: Position size (positive for long, negative for short)
        entry_price: Average entry price
        current_price: Current market price
        entry_time: When position was opened
        unrealized_pnl: Current unrealized P&L
        metadata: Additional position metadata
    """

    market_id: str
    size: float
    entry_price: float
    current_price: float
    entry_time: datetime = field(default_factory=datetime.now)
    unrealized_pnl: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_price(self, new_price: float) -> None:
        """Update current price and recalculate P&L."""
        self.current_price = new_price
        if self.size > 0:
            # Long position: profit when price increases
            self.unrealized_pnl = self.size * (new_price - self.entry_price)
        else:
            # Short position: profit when price decreases
            self.unrealized_pnl = abs(self.size) * (self.entry_price - new_price)

    def is_expired(self, timeout_hours: float) -> bool:
        """Check if position has exceeded timeout."""
        age = datetime.now() - self.entry_time
        return age > timedelta(hours=timeout_hours)


@dataclass
class RiskCheckResult:
    """Result of a risk check.

    Attributes:
        passed: Whether the order passed all risk checks
        reason: Explanation if check failed
        warnings: Non-blocking warnings
        metadata: Additional check metadata
    """

    passed: bool
    reason: str = "OK"
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_blocked(self) -> bool:
        """Check if order is blocked by risk limits."""
        return not self.passed


class RiskManager:
    """Risk management system with multiple safety layers.

    Enforces limits on:
    - Position size per market
    - Total exposure across all positions
    - Daily loss limits
    - Number of simultaneous positions
    - Position holding time

    Includes kill switch for emergency stops.

    Example:
        >>> from autopredict.config import RiskConfig
        >>> config = RiskConfig(
        ...     max_position_per_market=100.0,
        ...     max_total_exposure=500.0,
        ...     max_daily_loss=50.0,
        ...     kill_switch_threshold=-100.0
        ... )
        >>> risk_mgr = RiskManager(config)
        >>> order = Order(...)
        >>> result = risk_mgr.check_order(order, current_price=0.55)
        >>> if result.passed:
        ...     # Safe to execute
        ...     pass
    """

    def __init__(self, config: RiskConfig):
        """Initialize risk manager.

        Args:
            config: Risk configuration with limits and thresholds
        """
        self.config = config
        self.positions: dict[str, Position] = {}
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.current_exposure = 0.0
        self.day_start = datetime.now().date()
        self.kill_switch_active = False
        self.trade_count = 0

    def check_order(
        self,
        order: Order,
        current_price: float,
    ) -> RiskCheckResult:
        """Check if order passes all risk limits.

        Performs comprehensive pre-trade risk checks:
        1. Kill switch status
        2. Position size limit per market
        3. Total exposure limit
        4. Daily loss limit
        5. Maximum positions limit

        Args:
            order: Order to check
            current_price: Current market price

        Returns:
            RiskCheckResult indicating if order can proceed
        """
        warnings = []

        # Reset daily P&L if new day
        self._check_new_day()

        # Check 1: Kill switch
        if self.kill_switch_active:
            return RiskCheckResult(
                passed=False,
                reason="Kill switch is active - all trading halted",
                metadata={"kill_switch": True},
            )

        # Check 2: Daily loss limit exceeded
        if self.config.enable_kill_switch and self.daily_pnl <= self.config.kill_switch_threshold:
            self._trigger_kill_switch("Daily loss exceeded kill switch threshold")
            return RiskCheckResult(
                passed=False,
                reason=f"Kill switch triggered: daily P&L ({self.daily_pnl:.2f}) <= threshold ({self.config.kill_switch_threshold:.2f})",
                metadata={"kill_switch": True, "daily_pnl": self.daily_pnl},
            )

        if self.daily_pnl <= -abs(self.config.max_daily_loss):
            return RiskCheckResult(
                passed=False,
                reason=f"Daily loss limit exceeded: {self.daily_pnl:.2f} <= -{self.config.max_daily_loss:.2f}",
                metadata={"daily_pnl": self.daily_pnl},
            )

        # Check 3: Position size limit per market
        current_position_size = abs(self.positions.get(order.market_id, Position(
            order.market_id, 0.0, 0.0, 0.0
        )).size)
        new_position_size = current_position_size + order.size

        if new_position_size > self.config.max_position_per_market:
            return RiskCheckResult(
                passed=False,
                reason=f"Position limit exceeded for {order.market_id}: "
                       f"{new_position_size:.2f} > {self.config.max_position_per_market:.2f}",
                metadata={"market_id": order.market_id, "new_size": new_position_size},
            )

        # Check 4: Total exposure limit
        order_exposure = order.size * current_price
        new_total_exposure = self.current_exposure + order_exposure

        if new_total_exposure > self.config.max_total_exposure:
            return RiskCheckResult(
                passed=False,
                reason=f"Total exposure limit exceeded: "
                       f"{new_total_exposure:.2f} > {self.config.max_total_exposure:.2f}",
                metadata={"new_exposure": new_total_exposure},
            )

        # Check 5: Maximum positions limit
        if order.market_id not in self.positions and len(self.positions) >= self.config.max_positions:
            return RiskCheckResult(
                passed=False,
                reason=f"Maximum positions limit exceeded: {len(self.positions)} >= {self.config.max_positions}",
                metadata={"num_positions": len(self.positions)},
            )

        # Warning: Approaching daily loss limit
        if self.daily_pnl < -abs(self.config.max_daily_loss) * 0.75:
            warnings.append(f"Approaching daily loss limit: {self.daily_pnl:.2f}")

        # Warning: High exposure
        if new_total_exposure > self.config.max_total_exposure * 0.8:
            warnings.append(f"High exposure: {new_total_exposure:.2f} (80% of limit)")

        return RiskCheckResult(
            passed=True,
            reason="OK",
            warnings=warnings,
            metadata={
                "daily_pnl": self.daily_pnl,
                "total_exposure": new_total_exposure,
                "num_positions": len(self.positions),
            },
        )

    def update_position(
        self,
        market_id: str,
        size_delta: float,
        price: float,
        pnl_delta: float = 0.0,
    ) -> None:
        """Update position after trade execution.

        Args:
            market_id: Market identifier
            size_delta: Change in position size (positive for buys, negative for sells)
            price: Execution price
            pnl_delta: Realized P&L from this trade
        """
        self._check_new_day()

        # Update P&L
        self.daily_pnl += pnl_delta
        self.total_pnl += pnl_delta

        # Update or create position
        if market_id in self.positions:
            position = self.positions[market_id]

            # Calculate new position size
            old_size = position.size
            new_size = old_size + size_delta

            if abs(new_size) < 1e-6:
                # Position closed
                self.current_exposure -= abs(old_size * position.current_price)
                del self.positions[market_id]
            else:
                # Update position
                # Recalculate average entry price
                if (old_size > 0 and size_delta > 0) or (old_size < 0 and size_delta < 0):
                    # Adding to position - update average entry
                    total_cost = (old_size * position.entry_price) + (size_delta * price)
                    position.entry_price = total_cost / new_size
                else:
                    # Reducing position - keep same entry price
                    pass

                position.size = new_size
                position.update_price(price)

                # Update exposure
                old_exposure = abs(old_size * position.current_price)
                new_exposure = abs(new_size * price)
                self.current_exposure = self.current_exposure - old_exposure + new_exposure

        else:
            # New position
            position = Position(
                market_id=market_id,
                size=size_delta,
                entry_price=price,
                current_price=price,
            )
            self.positions[market_id] = position
            self.current_exposure += abs(size_delta * price)

        self.trade_count += 1

    def update_market_prices(self, prices: dict[str, float]) -> None:
        """Update current prices for all positions and recalculate P&L.

        Args:
            prices: Dictionary mapping market_id to current price
        """
        for market_id, price in prices.items():
            if market_id in self.positions:
                self.positions[market_id].update_price(price)

    def check_position_timeouts(self) -> list[str]:
        """Check for positions that have exceeded timeout.

        Returns:
            List of market IDs with expired positions
        """
        expired = []
        for market_id, position in self.positions.items():
            if position.is_expired(self.config.position_timeout_hours):
                expired.append(market_id)
        return expired

    def get_current_exposure(self) -> float:
        """Get current total exposure across all positions."""
        return self.current_exposure

    def get_daily_pnl(self) -> float:
        """Get current daily P&L."""
        self._check_new_day()
        return self.daily_pnl

    def get_total_unrealized_pnl(self) -> float:
        """Calculate total unrealized P&L across all positions."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    def get_positions_summary(self) -> dict[str, Any]:
        """Get summary of all current positions.

        Returns:
            Dictionary with position statistics
        """
        return {
            "num_positions": len(self.positions),
            "total_exposure": self.current_exposure,
            "daily_pnl": self.daily_pnl,
            "total_pnl": self.total_pnl,
            "unrealized_pnl": self.get_total_unrealized_pnl(),
            "positions": {
                market_id: {
                    "size": pos.size,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "age_hours": (datetime.now() - pos.entry_time).total_seconds() / 3600,
                }
                for market_id, pos in self.positions.items()
            },
        }

    def _trigger_kill_switch(self, reason: str) -> None:
        """Activate kill switch to halt all trading.

        Args:
            reason: Reason for activation
        """
        self.kill_switch_active = True
        print("\n" + "=" * 60)
        print("KILL SWITCH ACTIVATED")
        print("=" * 60)
        print(f"Reason: {reason}")
        print(f"Daily P&L: {self.daily_pnl:.2f}")
        print(f"Total exposure: {self.current_exposure:.2f}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("All trading has been HALTED")
        print("=" * 60 + "\n")

    def manual_kill_switch(self, reason: str = "Manual activation") -> None:
        """Manually activate kill switch.

        Args:
            reason: Reason for manual activation
        """
        self._trigger_kill_switch(reason)

    def is_kill_switch_active(self) -> bool:
        """Check if kill switch is currently active."""
        return self.kill_switch_active

    def reset_kill_switch(self, confirmation: str) -> bool:
        """Reset kill switch (requires explicit confirmation).

        Args:
            confirmation: Must be "RESET KILL SWITCH" to confirm

        Returns:
            True if reset successful, False otherwise
        """
        if confirmation != "RESET KILL SWITCH":
            print("Kill switch reset DENIED - incorrect confirmation")
            return False

        self.kill_switch_active = False
        print("Kill switch has been RESET - trading can resume")
        return True

    def _check_new_day(self) -> None:
        """Check if it's a new day and reset daily P&L if needed."""
        current_date = datetime.now().date()
        if current_date > self.day_start:
            print(f"\nNew trading day: {current_date}")
            print(f"Previous day P&L: {self.daily_pnl:.2f}")
            self.daily_pnl = 0.0
            self.day_start = current_date
            print(f"Daily P&L reset to 0.0\n")
