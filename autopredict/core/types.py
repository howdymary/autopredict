"""Core type definitions for the AutoPredict trading system.

This module defines all the fundamental data structures used throughout the system:
- Market representation (events, contracts, states)
- Decision objects (edges, orders, positions)
- Portfolio aggregation
- Execution reports

All types are immutable dataclasses with comprehensive field documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    """Side of the order: buy (go long) or sell (go short)."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order execution type."""

    MARKET = "market"  # Immediate execution at best available price
    LIMIT = "limit"  # Execute only at specified price or better


class MarketCategory(str, Enum):
    """Market category for filtering and analysis."""

    POLITICS = "politics"
    SPORTS = "sports"
    ECONOMICS = "economics"
    CRYPTO = "crypto"
    SCIENCE = "science"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


@dataclass(frozen=True)
class MarketState:
    """Complete state of a prediction market at a point in time.

    This is the primary input to trading strategies. Contains all information
    needed to make trading decisions: pricing, liquidity, timing, and metadata.

    Attributes:
        market_id: Unique identifier for this market (e.g., "polymarket-123456").
        question: Human-readable market question.
        market_prob: Current market-implied probability (0-1).
        expiry: Market resolution time (UTC).
        category: Market category for filtering.

        # Liquidity information
        best_bid: Best bid price (0-1).
        best_ask: Best ask price (0-1).
        bid_liquidity: Total liquidity available on bid side.
        ask_liquidity: Total liquidity available on ask side.

        # Additional metadata
        volume_24h: 24-hour trading volume.
        num_traders: Number of unique traders.
        metadata: Additional venue-specific data.

    Example:
        >>> state = MarketState(
        ...     market_id="polymarket-will-btc-hit-100k",
        ...     question="Will Bitcoin hit $100k in 2026?",
        ...     market_prob=0.65,
        ...     expiry=datetime(2026, 12, 31),
        ...     category=MarketCategory.CRYPTO,
        ...     best_bid=0.64,
        ...     best_ask=0.66,
        ...     bid_liquidity=50000.0,
        ...     ask_liquidity=45000.0,
        ...     volume_24h=125000.0,
        ...     num_traders=342
        ... )
    """

    market_id: str
    question: str
    market_prob: float
    expiry: datetime
    category: MarketCategory

    # Liquidity
    best_bid: float
    best_ask: float
    bid_liquidity: float
    ask_liquidity: float

    # Additional market data
    volume_24h: float = 0.0
    num_traders: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate market state invariants."""
        # Validate probabilities
        if not (0 <= self.market_prob <= 1):
            raise ValueError(f"market_prob must be in [0, 1], got {self.market_prob}")
        if not (0 <= self.best_bid <= 1):
            raise ValueError(f"best_bid must be in [0, 1], got {self.best_bid}")
        if not (0 <= self.best_ask <= 1):
            raise ValueError(f"best_ask must be in [0, 1], got {self.best_ask}")

        # Validate bid/ask relationship
        if self.best_bid > self.best_ask:
            raise ValueError(f"best_bid ({self.best_bid}) > best_ask ({self.best_ask})")

        # Validate liquidity is non-negative
        if self.bid_liquidity < 0:
            raise ValueError(f"bid_liquidity must be non-negative, got {self.bid_liquidity}")
        if self.ask_liquidity < 0:
            raise ValueError(f"ask_liquidity must be non-negative, got {self.ask_liquidity}")

    @property
    def spread(self) -> float:
        """Current bid-ask spread in absolute terms."""
        return self.best_ask - self.best_bid

    @property
    def spread_bps(self) -> float:
        """Current bid-ask spread in basis points."""
        mid = (self.best_bid + self.best_ask) / 2
        if mid == 0:
            return 0.0
        return (self.spread / mid) * 10_000

    @property
    def mid_price(self) -> float:
        """Midpoint between best bid and ask."""
        return (self.best_bid + self.best_ask) / 2

    @property
    def total_liquidity(self) -> float:
        """Total visible liquidity (both sides)."""
        return self.bid_liquidity + self.ask_liquidity

    @property
    def time_to_expiry_hours(self) -> float:
        """Hours until market expiry."""
        delta = self.expiry - datetime.now()
        return max(0.0, delta.total_seconds() / 3600)


@dataclass(frozen=True)
class EdgeEstimate:
    """Estimated edge in a prediction market.

    Represents the trader's view of mispricing: the difference between
    the true probability and the market-implied probability.

    Attributes:
        market_id: Market this edge estimate applies to.
        fair_prob: Estimated true probability (0-1).
        market_prob: Current market-implied probability (0-1).
        confidence: Confidence in this estimate (0-1), used for position sizing.
        timestamp: When this estimate was computed.
        metadata: Additional information (model version, features used, etc.).

    Example:
        >>> edge = EdgeEstimate(
        ...     market_id="polymarket-123",
        ...     fair_prob=0.75,
        ...     market_prob=0.65,
        ...     confidence=0.85,
        ...     timestamp=datetime.now()
        ... )
        >>> edge.edge  # 0.10 (10% edge)
        >>> edge.edge_bps  # 1000 (1000 basis points)
    """

    market_id: str
    fair_prob: float
    market_prob: float
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate edge estimate invariants."""
        if not (0 <= self.fair_prob <= 1):
            raise ValueError(f"fair_prob must be in [0, 1], got {self.fair_prob}")
        if not (0 <= self.market_prob <= 1):
            raise ValueError(f"market_prob must be in [0, 1], got {self.market_prob}")
        if not (0 <= self.confidence <= 1):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

    @property
    def edge(self) -> float:
        """Raw edge in probability units."""
        return self.fair_prob - self.market_prob

    @property
    def abs_edge(self) -> float:
        """Absolute edge magnitude."""
        return abs(self.edge)

    @property
    def edge_bps(self) -> float:
        """Edge in basis points."""
        return self.edge * 10_000

    @property
    def direction(self) -> OrderSide:
        """Which side to trade based on edge direction."""
        return OrderSide.BUY if self.edge > 0 else OrderSide.SELL


@dataclass(frozen=True)
class Order:
    """Order to be sent to a prediction market venue.

    Attributes:
        market_id: Market to trade in.
        side: Buy (go long) or sell (go short).
        order_type: Market (immediate) or limit (price-specific).
        size: Number of contracts to trade.
        limit_price: Required for limit orders; None for market orders.
        timestamp: When this order was created.
        metadata: Additional order data (strategy name, reason, etc.).

    Example:
        >>> order = Order(
        ...     market_id="polymarket-123",
        ...     side=OrderSide.BUY,
        ...     order_type=OrderType.LIMIT,
        ...     size=100.0,
        ...     limit_price=0.65,
        ...     timestamp=datetime.now(),
        ...     metadata={"strategy": "mispriced_probability", "edge": 0.15}
        ... )
    """

    market_id: str
    side: OrderSide
    order_type: OrderType
    size: float
    limit_price: float | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate order invariants."""
        object.__setattr__(self, "side", OrderSide(self.side))
        object.__setattr__(self, "order_type", OrderType(self.order_type))

        if self.size <= 0:
            raise ValueError(f"size must be positive, got {self.size}")

        if self.order_type == OrderType.LIMIT:
            if self.limit_price is None:
                raise ValueError("limit_price required for limit orders")
            if not (0 <= self.limit_price <= 1):
                raise ValueError(f"limit_price must be in [0, 1], got {self.limit_price}")

        if self.order_type == OrderType.MARKET and self.limit_price is not None:
            raise ValueError("limit_price should be None for market orders")

    def validate(self) -> None:
        """Retain compatibility with legacy call sites expecting explicit validation."""
        return None


@dataclass(frozen=True)
class ExecutionReport:
    """Report of order execution results.

    Returned by market adapters after attempting to execute an order.
    Contains fill information, costs, and execution quality metrics.

    Attributes:
        order: Original order that was executed.
        filled_size: Actual amount filled (may be partial).
        avg_fill_price: Volume-weighted average fill price.
        fills: List of individual fills (price, size pairs).
        slippage_bps: Slippage in basis points relative to mid price.
        fee_total: Total fees paid.
        timestamp: When execution completed.
        metadata: Additional execution data.

    Example:
        >>> report = ExecutionReport(
        ...     order=order,
        ...     filled_size=100.0,
        ...     avg_fill_price=0.652,
        ...     fills=[(0.65, 50.0), (0.654, 50.0)],
        ...     slippage_bps=20.0,
        ...     fee_total=0.20,
        ...     timestamp=datetime.now()
        ... )
    """

    order: Order
    filled_size: float = 0.0
    avg_fill_price: float | None = None
    fills: list[tuple[float, float]] = field(default_factory=list)
    slippage_bps: float = 0.0
    fee_total: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    execution_mode: str = "paper"
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def fill_rate(self) -> float:
        """Fraction of order that was filled."""
        if self.order.size == 0:
            return 0.0
        return self.filled_size / self.order.size

    @property
    def notional(self) -> float:
        """Total notional value of execution."""
        if self.avg_fill_price is None:
            return 0.0
        return self.filled_size * self.avg_fill_price

    @property
    def total_cost(self) -> float:
        """Total cost including fees."""
        return self.notional + self.fee_total

    @property
    def filled(self) -> bool:
        """Compatibility alias for legacy live-trading code."""
        return self.filled_size > 0.0 and self.avg_fill_price is not None

    @property
    def fill_price(self) -> float | None:
        """Compatibility alias for legacy live-trading code."""
        return self.avg_fill_price

    @property
    def fill_size(self) -> float:
        """Compatibility alias for legacy live-trading code."""
        return self.filled_size

    @property
    def fill_timestamp(self) -> datetime:
        """Compatibility alias for legacy live-trading code."""
        return self.timestamp

    @property
    def commission(self) -> float:
        """Compatibility alias for legacy live-trading code."""
        return self.fee_total

    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.filled and self.error_message is None

    def get_net_proceeds(self) -> float:
        """Calculate net proceeds after fees."""
        return self.notional - self.fee_total

    @property
    def is_complete(self) -> bool:
        """Whether order was completely filled."""
        return self.fill_rate >= 0.99  # Allow for rounding


@dataclass
class Position:
    """Current position in a single market.

    Tracks holdings, entry price, and unrealized PnL for one market.

    Attributes:
        market_id: Market this position is in.
        size: Current position size (positive = long, negative = short).
        entry_price: Average entry price for this position.
        current_price: Current market price.
        timestamp: When position was last updated.
        metadata: Additional position data.

    Example:
        >>> position = Position(
        ...     market_id="polymarket-123",
        ...     size=100.0,
        ...     entry_price=0.65,
        ...     current_price=0.70
        ... )
        >>> position.unrealized_pnl  # 5.0 (100 * (0.70 - 0.65))
        >>> position.unrealized_pnl_pct  # 0.0769 (7.69% gain)
    """

    market_id: str
    size: float
    entry_price: float
    current_price: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def notional(self) -> float:
        """Notional value of position at current price."""
        return abs(self.size) * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss in currency units."""
        return self.size * (self.current_price - self.entry_price)

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized PnL as percentage of entry value."""
        entry_value = abs(self.size) * self.entry_price
        if entry_value == 0:
            return 0.0
        return self.unrealized_pnl / entry_value

    @property
    def is_long(self) -> bool:
        """Whether this is a long position."""
        return self.size > 0

    @property
    def is_short(self) -> bool:
        """Whether this is a short position."""
        return self.size < 0

    def update_price(self, new_price: float) -> None:
        """Update current price (mutates position)."""
        self.current_price = new_price
        self.timestamp = datetime.now()


@dataclass
class Portfolio:
    """Aggregate portfolio state across all positions.

    Tracks cash, positions, and total portfolio value.

    Attributes:
        cash: Available cash for trading.
        positions: Dictionary of market_id -> Position.
        starting_capital: Initial capital at portfolio creation.
        timestamp: When portfolio was last updated.
        metadata: Additional portfolio data.

    Example:
        >>> portfolio = Portfolio(
        ...     cash=10000.0,
        ...     positions={
        ...         "market-1": Position("market-1", 100.0, 0.65, 0.70),
        ...         "market-2": Position("market-2", -50.0, 0.80, 0.75)
        ...     },
        ...     starting_capital=10000.0
        ... )
        >>> portfolio.total_value  # cash + sum of position values
        >>> portfolio.total_pnl  # total value - starting capital
    """

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    starting_capital: float = 10000.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_position_value(self) -> float:
        """Total notional value of all positions."""
        return sum(pos.notional for pos in self.positions.values())

    @property
    def total_value(self) -> float:
        """Total portfolio value (cash + positions)."""
        return self.cash + sum(pos.unrealized_pnl for pos in self.positions.values())

    @property
    def total_pnl(self) -> float:
        """Total profit/loss since inception."""
        return self.total_value - self.starting_capital

    @property
    def total_pnl_pct(self) -> float:
        """Total PnL as percentage of starting capital."""
        if self.starting_capital == 0:
            return 0.0
        return self.total_pnl / self.starting_capital

    @property
    def num_positions(self) -> int:
        """Number of active positions."""
        return len(self.positions)

    @property
    def leverage(self) -> float:
        """Portfolio leverage (position value / total value)."""
        if self.total_value == 0:
            return 0.0
        return self.total_position_value / self.total_value

    def add_position(self, position: Position) -> None:
        """Add or update a position (mutates portfolio)."""
        self.positions[position.market_id] = position
        self.timestamp = datetime.now()

    def remove_position(self, market_id: str) -> Position | None:
        """Remove a position and return it (mutates portfolio)."""
        self.timestamp = datetime.now()
        return self.positions.pop(market_id, None)

    def update_cash(self, delta: float) -> None:
        """Update cash balance (mutates portfolio)."""
        self.cash += delta
        self.timestamp = datetime.now()
