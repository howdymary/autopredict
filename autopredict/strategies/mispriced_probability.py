"""Mispriced probability strategy.

This strategy identifies markets where the model's probability estimate
differs significantly from the market-implied probability, and trades
to capture the edge.

Strategy logic:
1. Estimate fair probability using a forecasting model
2. Compare to market probability to identify edge
3. Trade when edge exceeds threshold
4. Size position using Kelly criterion with caps for safety
5. Use limit orders for passive execution when possible
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from autopredict.core.types import (
    EdgeEstimate,
    MarketState,
    Order,
    OrderSide,
    OrderType,
    Position,
)
from autopredict.strategies.base import RiskLimits


class MispricedProbabilityStrategy:
    """Strategy that trades mispriced probabilities.

    This is the foundational strategy: buy when fair_prob > market_prob,
    sell when fair_prob < market_prob, with appropriate risk controls.

    Attributes:
        risk_limits: Risk management parameters.
        kelly_fraction: Fraction of Kelly to use (0.25 = quarter-Kelly).
        aggressive_edge_threshold: Edge above which to use market orders.
        min_spread_capture: Minimum spread to capture with limit orders (bps).

    Example:
        >>> strategy = MispricedProbabilityStrategy(
        ...     risk_limits=RiskLimits(
        ...         max_position_size=500.0,
        ...         max_total_exposure=5000.0,
        ...         min_edge_threshold=0.05
        ...     ),
        ...     kelly_fraction=0.25
        ... )
        >>> edge = strategy.estimate_edge(market, config)
        >>> orders = strategy.decide(market, position, config)
    """

    def __init__(
        self,
        risk_limits: RiskLimits | None = None,
        kelly_fraction: float = 0.25,
        aggressive_edge_threshold: float = 0.15,
        min_spread_capture: float = 10.0,
    ):
        """Initialize strategy.

        Args:
            risk_limits: Risk management parameters.
            kelly_fraction: Fraction of Kelly to use for sizing (0-1).
            aggressive_edge_threshold: Edge threshold for market orders.
            min_spread_capture: Minimum spread to capture with limits (bps).
        """
        self.risk_limits = risk_limits or RiskLimits()
        self.kelly_fraction = kelly_fraction
        self.aggressive_edge_threshold = aggressive_edge_threshold
        self.min_spread_capture = min_spread_capture

    def estimate_edge(self, market: MarketState, config: dict) -> EdgeEstimate | None:
        """Estimate edge using configured probability model.

        Args:
            market: Current market state.
            config: Must contain 'probability_model' key with model instance.

        Returns:
            EdgeEstimate if model produces valid probability, None otherwise.

        Example:
            >>> config = {"probability_model": MyForecastModel()}
            >>> edge = strategy.estimate_edge(market, config)
            >>> if edge:
            ...     print(f"Edge: {edge.edge:.1%}")
        """
        # Get probability model from config
        model = config.get("probability_model")
        if model is None:
            return None

        # Generate forecast
        try:
            forecast = model.predict(market)
            fair_prob = forecast.get("probability")
            confidence = forecast.get("confidence", 0.8)

            if fair_prob is None or not (0 <= fair_prob <= 1):
                return None

            return EdgeEstimate(
                market_id=market.market_id,
                fair_prob=fair_prob,
                market_prob=market.market_prob,
                confidence=confidence,
                timestamp=datetime.now(),
                metadata={"model": str(type(model).__name__), "forecast": forecast},
            )
        except Exception as e:
            # Log error and return None
            return None

    def decide(
        self,
        market: MarketState,
        position: Position | None,
        config: dict,
    ) -> list[Order]:
        """Make trading decision based on edge and risk limits.

        Decision logic:
        1. Estimate edge using probability model
        2. Check if edge exceeds minimum threshold
        3. Check if market has sufficient liquidity
        4. Calculate position size using Kelly criterion
        5. Apply risk limits (max position, max exposure)
        6. Choose order type (market vs limit) based on edge/spread
        7. Generate order

        Args:
            market: Current market state.
            position: Current position in this market (None if no position).
            config: Must contain 'probability_model' and 'portfolio'.

        Returns:
            List of orders (empty if no trade warranted).

        Example:
            >>> config = {
            ...     "probability_model": model,
            ...     "portfolio": portfolio
            ... }
            >>> orders = strategy.decide(market, position, config)
        """
        # 1. Estimate edge
        edge = self.estimate_edge(market, config)
        if edge is None:
            return []

        # 2. Check edge threshold
        if edge.abs_edge < self.risk_limits.min_edge_threshold:
            return []

        # 3. Check confidence threshold
        if edge.confidence < self.risk_limits.min_confidence:
            return []

        # 4. Check liquidity
        min_liquidity = 100.0  # Minimum $100 liquidity
        if market.total_liquidity < min_liquidity:
            return []

        # 5. Check if we should exit existing position
        if position and self._should_exit_position(edge, position):
            return self._generate_exit_order(market, position)

        # 6. Check if we already have a position in the same direction
        if position and not self._should_add_to_position(edge, position):
            return []

        # 7. Calculate position size
        size = self._calculate_position_size(edge, market, config)
        if size <= 0:
            return []

        # 8. Reduce size if we already have a position
        if position:
            size = max(0, size - abs(position.size))

        if size <= 0:
            return []

        # 9. Choose order type
        order_type = self._choose_order_type(edge, market)

        # 10. Calculate limit price
        limit_price = None
        if order_type == OrderType.LIMIT:
            limit_price = self._calculate_limit_price(edge, market)

        # 11. Generate order
        order = Order(
            market_id=market.market_id,
            side=edge.direction,
            order_type=order_type,
            size=size,
            limit_price=limit_price,
            timestamp=datetime.now(),
            metadata={
                "strategy": "mispriced_probability",
                "edge": edge.edge,
                "confidence": edge.confidence,
                "fair_prob": edge.fair_prob,
            },
        )

        return [order]

    def _should_exit_position(self, edge: EdgeEstimate, position: Position) -> bool:
        """Check if we should exit an existing position.

        Exit if edge has reversed beyond a threshold.
        """
        # Exit if edge flipped direction significantly
        edge_threshold = self.risk_limits.min_edge_threshold * 0.5

        if position.is_long and edge.edge < -edge_threshold:
            return True
        if position.is_short and edge.edge > edge_threshold:
            return True

        return False

    def _should_add_to_position(self, edge: EdgeEstimate, position: Position) -> bool:
        """Check if we should add to an existing position.

        Only add if edge is in same direction as position.
        """
        if position.is_long and edge.edge > 0:
            return True
        if position.is_short and edge.edge < 0:
            return True

        return False

    def _generate_exit_order(self, market: MarketState, position: Position) -> list[Order]:
        """Generate order to exit a position."""
        # Exit at market to close quickly
        order = Order(
            market_id=market.market_id,
            side=OrderSide.SELL if position.is_long else OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=abs(position.size),
            limit_price=None,
            timestamp=datetime.now(),
            metadata={"strategy": "mispriced_probability", "action": "exit"},
        )
        return [order]

    def _calculate_position_size(
        self,
        edge: EdgeEstimate,
        market: MarketState,
        config: dict,
    ) -> float:
        """Calculate position size using Kelly criterion with caps.

        Kelly fraction = edge / variance
        For binary outcomes with edge e and probability p:
        Kelly = e / (1 - p) for longs
        Kelly = e / p for shorts

        We use fractional Kelly (kelly_fraction) for safety.

        Args:
            edge: Edge estimate.
            market: Market state.
            config: Must contain 'portfolio' key.

        Returns:
            Position size in currency units.
        """
        portfolio = config.get("portfolio")
        if portfolio is None:
            return 0.0

        # Calculate Kelly fraction
        if edge.direction == OrderSide.BUY:
            # Long: Kelly = edge / (1 - fair_prob)
            kelly = edge.edge / (1 - edge.fair_prob + 1e-9)
        else:
            # Short: Kelly = -edge / fair_prob
            kelly = -edge.edge / (edge.fair_prob + 1e-9)

        # Apply fractional Kelly
        kelly = kelly * self.kelly_fraction

        # Cap Kelly at reasonable bounds
        kelly = max(0.0, min(kelly, 0.25))  # Max 25% of bankroll

        # Calculate base size from Kelly
        base_size = portfolio.total_value * kelly

        # Apply confidence scaling
        base_size = base_size * edge.confidence

        # Apply risk limits
        size = min(
            base_size,
            self.risk_limits.max_position_size,
            self.risk_limits.max_total_exposure - portfolio.total_position_value,
        )

        # Apply liquidity constraints
        # Don't take more than 20% of available liquidity on our side
        available_liquidity = (
            market.ask_liquidity if edge.direction == OrderSide.BUY else market.bid_liquidity
        )
        size = min(size, available_liquidity * 0.20)

        return max(0.0, size)

    def _choose_order_type(self, edge: EdgeEstimate, market: MarketState) -> OrderType:
        """Choose between market and limit order.

        Use market orders when:
        - Edge is very large (> aggressive_edge_threshold)
        - Spread is tight relative to edge
        - Time to expiry is short

        Otherwise use limit orders to capture spread.
        """
        # Use market order for very large edges
        if edge.abs_edge >= self.aggressive_edge_threshold:
            return OrderType.MARKET

        # Use market order when spread is tight relative to edge
        edge_to_spread_ratio = edge.abs_edge / (market.spread + 1e-9)
        if edge_to_spread_ratio > 3.0:
            return OrderType.MARKET

        # Use market order when time is short
        if market.time_to_expiry_hours < 12:
            return OrderType.MARKET

        # Default to limit orders to capture spread
        return OrderType.LIMIT

    def _calculate_limit_price(self, edge: EdgeEstimate, market: MarketState) -> float:
        """Calculate limit price for passive execution.

        Strategy: Place limit inside the spread to improve fill probability
        while still capturing spread value.

        For buys: Bid slightly above best bid
        For sells: Ask slightly below best ask
        """
        # Calculate improvement in bps
        improvement_bps = 10.0  # Improve by 10 bps

        if edge.direction == OrderSide.BUY:
            # Improve bid by moving toward mid
            improvement = market.mid_price * (improvement_bps / 10_000)
            limit_price = market.best_bid + improvement
            # Cap at mid price
            limit_price = min(limit_price, market.mid_price)
        else:
            # Improve ask by moving toward mid
            improvement = market.mid_price * (improvement_bps / 10_000)
            limit_price = market.best_ask - improvement
            # Cap at mid price
            limit_price = max(limit_price, market.mid_price)

        # Ensure limit price is in valid range
        return max(0.0, min(1.0, limit_price))
