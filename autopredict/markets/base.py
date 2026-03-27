"""Base market adapter protocol.

Defines the interface that all market venue adapters must implement.
This abstraction allows the trading system to work with any prediction
market venue (Polymarket, Manifold, etc.) through a uniform interface.
"""

from __future__ import annotations

from typing import Protocol

from autopredict.core.types import ExecutionReport, MarketState, Order


class MarketAdapter(Protocol):
    """Protocol for prediction market venue adapters.

    Each venue (Polymarket, Manifold, etc.) implements this interface,
    providing a uniform way to:
    - Fetch market data
    - Place orders
    - Query positions
    - Get execution reports

    Example implementation:
        >>> class PolymarketAdapter:
        ...     def __init__(self, api_key: str):
        ...         self.api_key = api_key
        ...         self.client = PolymarketClient(api_key)
        ...
        ...     def get_markets(self, filters: dict | None = None) -> list[MarketState]:
        ...         # Fetch markets from Polymarket API
        ...         raw_markets = self.client.get_markets()
        ...         return [self._convert_to_market_state(m) for m in raw_markets]
        ...
        ...     def place_order(self, order: Order) -> ExecutionReport:
        ...         # Submit order to Polymarket
        ...         result = self.client.place_order(
        ...             market_id=order.market_id,
        ...             side=order.side,
        ...             size=order.size,
        ...             price=order.limit_price
        ...         )
        ...         return self._convert_to_execution_report(order, result)
    """

    def get_markets(self, filters: dict | None = None) -> list[MarketState]:
        """Fetch available markets from the venue.

        Args:
            filters: Optional filters (category, min_liquidity, etc.).

        Returns:
            List of MarketState objects representing current markets.

        Example:
            >>> markets = adapter.get_markets({"category": "politics", "min_liquidity": 10000})
            >>> print(f"Found {len(markets)} markets")
        """
        ...

    def get_market(self, market_id: str) -> MarketState | None:
        """Fetch a specific market by ID.

        Args:
            market_id: Venue-specific market identifier.

        Returns:
            MarketState if found, None otherwise.

        Example:
            >>> market = adapter.get_market("polymarket-123456")
            >>> if market:
            ...     print(f"Market: {market.question}")
            ...     print(f"Prob: {market.market_prob:.1%}")
        """
        ...

    def place_order(self, order: Order) -> ExecutionReport:
        """Place an order on the venue.

        Args:
            order: Order to execute.

        Returns:
            ExecutionReport with fill details.

        Raises:
            OrderRejected: If order is rejected by venue.
            InsufficientBalance: If insufficient funds.
            MarketClosed: If market is no longer accepting orders.

        Example:
            >>> order = Order(
            ...     market_id="polymarket-123",
            ...     side=OrderSide.BUY,
            ...     order_type=OrderType.LIMIT,
            ...     size=100.0,
            ...     limit_price=0.65
            ... )
            >>> report = adapter.place_order(order)
            >>> print(f"Filled {report.filled_size} @ {report.avg_fill_price}")
        """
        ...

    def cancel_order(self, market_id: str, order_id: str) -> bool:
        """Cancel an outstanding order.

        Args:
            market_id: Market the order is in.
            order_id: Venue-specific order identifier.

        Returns:
            True if cancelled successfully, False otherwise.

        Example:
            >>> if adapter.cancel_order("polymarket-123", "order-789"):
            ...     print("Order cancelled")
        """
        ...

    def get_position(self, market_id: str) -> float:
        """Get current position size in a market.

        Args:
            market_id: Market to query.

        Returns:
            Current position size (positive = long, negative = short, 0 = no position).

        Example:
            >>> position = adapter.get_position("polymarket-123")
            >>> print(f"Position: {position}")
        """
        ...

    def get_balance(self) -> float:
        """Get current cash balance.

        Returns:
            Available cash for trading.

        Example:
            >>> balance = adapter.get_balance()
            >>> print(f"Balance: ${balance:.2f}")
        """
        ...
