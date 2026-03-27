"""Core typed objects for the Step 1 prediction-market scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from autopredict.core.types import MarketState, Order, Portfolio, Position


class VenueName(str, Enum):
    """Supported venue families for market snapshots."""

    POLYMARKET = "polymarket"
    KALSHI = "kalshi"
    MANIFOLD = "manifold"
    CUSTOM = "custom"


@dataclass(frozen=True)
class VenueConfig:
    """Venue metadata that later steps can extend with execution realism."""

    name: VenueName
    fee_bps: float = 0.0
    tick_size: float = 0.01
    min_order_size: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.fee_bps < 0:
            raise ValueError("fee_bps must be non-negative")
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if self.min_order_size <= 0:
            raise ValueError("min_order_size must be positive")


@dataclass(frozen=True)
class MarketSignal:
    """Forecast signal produced before execution details are chosen."""

    fair_prob: float
    confidence: float
    rationale: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.fair_prob <= 1.0):
            raise ValueError(f"fair_prob must be in [0, 1], got {self.fair_prob}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

    def edge_against(self, market_prob: float) -> float:
        """Return edge in probability units against a market price."""

        if not (0.0 <= market_prob <= 1.0):
            raise ValueError(f"market_prob must be in [0, 1], got {market_prob}")
        return self.fair_prob - market_prob


@dataclass(frozen=True)
class MarketSnapshot:
    """One venue-specific market observation passed to strategies."""

    market: MarketState
    venue: VenueConfig
    observed_at: datetime = field(default_factory=datetime.now)
    features: dict[str, Any] = field(default_factory=dict)
    labels: dict[str, Any] = field(default_factory=dict)

    @property
    def market_id(self) -> str:
        """Return the underlying market identifier."""

        return self.market.market_id


@dataclass
class StrategyContext:
    """Runtime context available to strategies during one evaluation."""

    portfolio: Portfolio
    position: Position | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DecisionStatus(str, Enum):
    """High-level action chosen by the scaffold agent."""

    TRADE = "trade"
    HOLD = "hold"
    SKIP = "skip"


@dataclass(frozen=True)
class AgentDecision:
    """Full result of evaluating one market snapshot."""

    market_id: str
    status: DecisionStatus
    signal: MarketSignal | None = None
    orders: tuple[Order, ...] = ()
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def should_trade(self) -> bool:
        """Return whether the agent decided to emit executable orders."""

        return self.status == DecisionStatus.TRADE
