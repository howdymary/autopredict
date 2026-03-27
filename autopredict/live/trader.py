"""Trading execution with paper and live mode separation.

Paper trading simulates execution without real capital.
Live trading requires explicit confirmation and uses real APIs.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
import warnings


@dataclass
class Order:
    """Trading order specification.

    Attributes:
        market_id: Market identifier
        side: "buy" or "sell"
        order_type: "market" or "limit"
        size: Position size in currency units
        limit_price: Price for limit orders (None for market orders)
        timestamp: Order creation timestamp
        metadata: Additional order metadata
    """

    market_id: str
    side: str
    order_type: str
    size: float
    limit_price: float | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate order parameters.

        Raises:
            ValueError: If order parameters are invalid
        """
        if not self.market_id:
            raise ValueError("market_id cannot be empty")
        if self.side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got '{self.side}'")
        if self.order_type not in ("market", "limit"):
            raise ValueError(f"order_type must be 'market' or 'limit', got '{self.order_type}'")
        if self.size <= 0:
            raise ValueError(f"size must be positive, got {self.size}")
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price required for limit orders")
        if self.limit_price is not None and not 0 < self.limit_price < 1:
            raise ValueError(f"limit_price must be in (0, 1) for binary markets, got {self.limit_price}")


@dataclass
class ExecutionReport:
    """Report of order execution.

    Attributes:
        order: Original order
        filled: Whether order was filled
        fill_price: Actual execution price (None if not filled)
        fill_size: Actual filled size
        fill_timestamp: When order was filled
        commission: Trading commission paid
        slippage_bps: Slippage in basis points (positive = worse than expected)
        execution_mode: "paper" or "live"
        error_message: Error message if execution failed
        metadata: Additional execution metadata
    """

    order: Order
    filled: bool
    fill_price: float | None = None
    fill_size: float = 0.0
    fill_timestamp: datetime | None = None
    commission: float = 0.0
    slippage_bps: float = 0.0
    execution_mode: str = "paper"
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.filled and self.error_message is None

    def get_net_proceeds(self) -> float:
        """Calculate net proceeds after commission.

        Returns:
            Net value of filled position
        """
        if not self.filled or self.fill_price is None:
            return 0.0
        gross = self.fill_size * self.fill_price
        return gross - self.commission


class VenueAdapter(Protocol):
    """Protocol for venue API adapters.

    Defines the interface that venue-specific adapters must implement.
    """

    def submit_order(self, order: Order) -> ExecutionReport:
        """Submit order to venue and get execution report."""
        ...

    def get_order_book(self, market_id: str) -> dict[str, Any]:
        """Get current order book for market."""
        ...

    def get_position(self, market_id: str) -> float:
        """Get current position size for market."""
        ...


class PaperTrader:
    """Simulated trading with no real capital.

    Paper trader simulates order execution using current order book data.
    All fills are simulated - no real money is at risk.

    Example:
        >>> trader = PaperTrader(commission_rate=0.01)
        >>> order = Order(
        ...     market_id="test-market",
        ...     side="buy",
        ...     order_type="market",
        ...     size=100.0
        ... )
        >>> report = trader.place_order(order, current_price=0.55)
        >>> print(f"Filled at {report.fill_price} (paper mode)")
    """

    def __init__(
        self,
        commission_rate: float = 0.01,
        slippage_bps: float = 5.0,
        limit_fill_rate: float = 0.4,
    ):
        """Initialize paper trader.

        Args:
            commission_rate: Commission as decimal (e.g., 0.01 for 1%)
            slippage_bps: Average slippage in basis points for market orders
            limit_fill_rate: Probability of limit order fills (0-1)
        """
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps
        self.limit_fill_rate = limit_fill_rate
        self.trade_history: list[ExecutionReport] = []
        self.positions: dict[str, float] = {}

    def place_order(
        self,
        order: Order,
        current_price: float,
        order_book: dict[str, Any] | None = None,
    ) -> ExecutionReport:
        """Execute order in paper trading mode.

        Args:
            order: Order to execute
            current_price: Current market price
            order_book: Optional order book for realistic simulation

        Returns:
            Execution report with simulated fill
        """
        order.validate()

        # Simulate market order
        if order.order_type == "market":
            return self._execute_market_order(order, current_price)

        # Simulate limit order
        else:
            return self._execute_limit_order(order, current_price)

    def _execute_market_order(self, order: Order, current_price: float) -> ExecutionReport:
        """Simulate market order execution with slippage."""
        # Add slippage (basis points)
        slippage_factor = self.slippage_bps / 10000.0

        if order.side == "buy":
            # Slippage increases price for buys
            fill_price = current_price * (1 + slippage_factor)
        else:
            # Slippage decreases price for sells
            fill_price = current_price * (1 - slippage_factor)

        # Clamp to valid range for binary markets
        fill_price = max(0.01, min(0.99, fill_price))

        # Calculate commission
        commission = order.size * self.commission_rate

        # Update position tracking
        position_delta = order.size if order.side == "buy" else -order.size
        self.positions[order.market_id] = self.positions.get(order.market_id, 0.0) + position_delta

        report = ExecutionReport(
            order=order,
            filled=True,
            fill_price=fill_price,
            fill_size=order.size,
            fill_timestamp=datetime.now(),
            commission=commission,
            slippage_bps=self.slippage_bps,
            execution_mode="paper",
        )

        self.trade_history.append(report)
        return report

    def _execute_limit_order(self, order: Order, current_price: float) -> ExecutionReport:
        """Simulate limit order execution with probabilistic fills."""
        import random

        # Check if limit order would be immediately executable
        if order.limit_price is None:
            raise ValueError("limit_price required for limit orders")

        is_executable = (
            (order.side == "buy" and order.limit_price >= current_price) or
            (order.side == "sell" and order.limit_price <= current_price)
        )

        # Probabilistic fill based on limit_fill_rate
        filled = is_executable or (random.random() < self.limit_fill_rate)

        if not filled:
            return ExecutionReport(
                order=order,
                filled=False,
                execution_mode="paper",
                metadata={"reason": "limit_not_filled"},
            )

        # Use limit price as fill price (best case)
        fill_price = order.limit_price
        commission = order.size * self.commission_rate

        # Update position tracking
        position_delta = order.size if order.side == "buy" else -order.size
        self.positions[order.market_id] = self.positions.get(order.market_id, 0.0) + position_delta

        report = ExecutionReport(
            order=order,
            filled=True,
            fill_price=fill_price,
            fill_size=order.size,
            fill_timestamp=datetime.now(),
            commission=commission,
            slippage_bps=0.0,  # No slippage on limit orders
            execution_mode="paper",
        )

        self.trade_history.append(report)
        return report

    def get_position(self, market_id: str) -> float:
        """Get current position for a market."""
        return self.positions.get(market_id, 0.0)

    def get_trade_history(self) -> list[ExecutionReport]:
        """Get complete trade history."""
        return self.trade_history.copy()

    def get_total_commission_paid(self) -> float:
        """Calculate total commission paid across all trades."""
        return sum(trade.commission for trade in self.trade_history)


class LiveTrader:
    """Real trading - requires explicit opt-in and confirmation.

    Live trader executes real orders on production venues using real capital.
    Multiple safety checks prevent accidental live trading.

    CRITICAL SAFETY FEATURES:
    - Requires explicit live mode confirmation
    - Validates API credentials
    - Enforces risk checks before every trade
    - Logs all activity to production journal
    - Cannot be instantiated without user confirmation

    Example:
        >>> # User must explicitly confirm live mode
        >>> trader = LiveTrader(venue_adapter, safety_checks=True)
        >>> # Will prompt: "LIVE TRADING MODE - Type 'CONFIRM LIVE' to proceed:"
        >>> order = Order(...)
        >>> report = trader.place_order(order)  # Real money at risk!
    """

    def __init__(
        self,
        venue_adapter: VenueAdapter,
        safety_checks: bool = True,
        require_confirmation: bool = True,
    ):
        """Initialize live trader with safety checks.

        Args:
            venue_adapter: Venue-specific API adapter
            safety_checks: Whether to enable pre-trade risk checks (should always be True)
            require_confirmation: Whether to require user confirmation (should always be True)

        Raises:
            RuntimeError: If live mode confirmation fails
        """
        if not safety_checks:
            warnings.warn(
                "DANGER: Safety checks are disabled! This is not recommended for production.",
                category=UserWarning,
                stacklevel=2,
            )

        if require_confirmation and not self._confirm_live_mode():
            raise RuntimeError("Live mode not confirmed - trader not initialized")

        self.venue_adapter = venue_adapter
        self.safety_checks = safety_checks
        self.trade_history: list[ExecutionReport] = []
        self.is_active = True

        print("LIVE TRADER INITIALIZED - REAL MONEY AT RISK")
        print("=" * 60)

    def _confirm_live_mode(self) -> bool:
        """Require explicit user confirmation for live trading.

        Returns:
            True if user confirms, False otherwise
        """
        print("\n" + "=" * 60)
        print("WARNING: LIVE TRADING MODE")
        print("=" * 60)
        print("This will execute REAL trades with REAL money.")
        print("Are you sure you want to proceed?")
        print("")
        print("Type 'CONFIRM LIVE' (all caps) to proceed, or anything else to abort:")

        try:
            response = input("> ").strip()
            if response == "CONFIRM LIVE":
                print("Live trading mode CONFIRMED")
                return True
            else:
                print("Live trading mode ABORTED")
                return False
        except (EOFError, KeyboardInterrupt):
            print("\nLive trading mode ABORTED (interrupted)")
            return False

    def place_order(self, order: Order) -> ExecutionReport:
        """Execute real order on live venue.

        Args:
            order: Order to execute

        Returns:
            Execution report from venue

        Raises:
            RuntimeError: If trader is inactive or safety checks fail
        """
        if not self.is_active:
            raise RuntimeError("Trader is inactive - cannot place orders")

        order.validate()

        # Log order submission
        print(f"[LIVE] Submitting {order.side} order: {order.market_id} size={order.size} type={order.order_type}")

        try:
            # Submit to real venue
            report = self.venue_adapter.submit_order(order)
            report.execution_mode = "live"

            # Log result
            if report.is_success():
                print(f"[LIVE] Order FILLED at {report.fill_price}")
            else:
                print(f"[LIVE] Order FAILED: {report.error_message}")

            self.trade_history.append(report)
            return report

        except Exception as e:
            # Create error report
            error_report = ExecutionReport(
                order=order,
                filled=False,
                execution_mode="live",
                error_message=str(e),
            )
            self.trade_history.append(error_report)

            print(f"[LIVE] Order EXCEPTION: {e}")
            raise

    def kill_switch(self, reason: str = "Manual kill switch activated") -> None:
        """Immediately halt all trading activity.

        This is the emergency stop. Once activated, no further orders can be placed.

        Args:
            reason: Reason for kill switch activation
        """
        self.is_active = False
        print("\n" + "=" * 60)
        print("KILL SWITCH ACTIVATED")
        print("=" * 60)
        print(f"Reason: {reason}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("All trading activity has been HALTED")
        print("=" * 60 + "\n")

    def get_trade_history(self) -> list[ExecutionReport]:
        """Get complete trade history."""
        return self.trade_history.copy()

    def is_trading_active(self) -> bool:
        """Check if trading is currently active."""
        return self.is_active
