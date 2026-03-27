"""Base strategy protocol and utilities.

Defines the interface that all trading strategies must implement,
along with common risk management utilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from autopredict.core.types import EdgeEstimate, MarketState, Order, Position


@dataclass
class RiskLimits:
    """Risk limits for position sizing and portfolio management.

    All strategies should respect these limits when generating orders.

    Attributes:
        max_position_size: Maximum position size per market (in currency units).
        max_total_exposure: Maximum total exposure across all positions.
        max_daily_loss: Maximum loss allowed in a single day before kill switch.
        max_leverage: Maximum portfolio leverage (position value / total value).
        min_edge_threshold: Minimum edge required to consider trading.
        min_confidence: Minimum confidence required to trade an edge.

    Example:
        >>> limits = RiskLimits(
        ...     max_position_size=500.0,
        ...     max_total_exposure=5000.0,
        ...     max_daily_loss=1000.0,
        ...     max_leverage=2.0,
        ...     min_edge_threshold=0.05,
        ...     min_confidence=0.7
        ... )
    """

    max_position_size: float = 500.0
    max_total_exposure: float = 5000.0
    max_daily_loss: float = 1000.0
    max_leverage: float = 2.0
    min_edge_threshold: float = 0.05
    min_confidence: float = 0.7


class Strategy(Protocol):
    """Protocol for trading strategies.

    All strategies must implement these methods. The strategy is responsible for:
    1. Estimating edge (fair prob vs market prob)
    2. Deciding whether to trade
    3. Generating orders with appropriate sizing

    Example implementation:
        >>> class MyStrategy:
        ...     def __init__(self, risk_limits: RiskLimits):
        ...         self.risk_limits = risk_limits
        ...
        ...     def estimate_edge(self, market: MarketState, config: dict) -> EdgeEstimate | None:
        ...         # Implement your edge estimation logic
        ...         fair_prob = self._calculate_fair_prob(market)
        ...         return EdgeEstimate(
        ...             market_id=market.market_id,
        ...             fair_prob=fair_prob,
        ...             market_prob=market.market_prob,
        ...             confidence=0.8
        ...         )
        ...
        ...     def decide(
        ...         self,
        ...         market: MarketState,
        ...         position: Position | None,
        ...         config: dict
        ...     ) -> list[Order]:
        ...         edge = self.estimate_edge(market, config)
        ...         if not edge or edge.abs_edge < self.risk_limits.min_edge_threshold:
        ...             return []
        ...
        ...         size = self._calculate_size(edge)
        ...         return [Order(
        ...             market_id=market.market_id,
        ...             side=edge.direction,
        ...             order_type=OrderType.LIMIT,
        ...             size=size,
        ...             limit_price=market.best_bid if edge.direction == OrderSide.BUY else market.best_ask
        ...         )]
    """

    def estimate_edge(self, market: MarketState, config: dict) -> EdgeEstimate | None:
        """Estimate the edge in a market.

        Args:
            market: Current market state.
            config: Strategy-specific configuration.

        Returns:
            EdgeEstimate if there's a potential edge, None otherwise.

        Example:
            >>> edge = strategy.estimate_edge(market, {"model": "xgboost_v2"})
            >>> if edge and edge.abs_edge > 0.05:
            ...     print(f"Found {edge.abs_edge:.1%} edge")
        """
        ...

    def decide(
        self,
        market: MarketState,
        position: Position | None,
        config: dict,
    ) -> list[Order]:
        """Make trading decision for a market.

        This is the main entry point for the strategy. Called periodically
        for each market the strategy is monitoring.

        Args:
            market: Current market state.
            position: Current position in this market (None if no position).
            config: Strategy-specific configuration.

        Returns:
            List of orders to execute (empty list if no action).

        Example:
            >>> orders = strategy.decide(market, position, config)
            >>> for order in orders:
            ...     print(f"{order.side} {order.size} @ {order.limit_price}")
        """
        ...
