"""Manifold Markets adapter implementation.

Manifold is a play-money prediction market platform with an active community.
Good for testing strategies before deploying to real-money markets.

API Documentation: https://docs.manifold.markets/api
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from autopredict.core.types import (
    ExecutionReport,
    MarketCategory,
    MarketState,
    Order,
    OrderSide,
    OrderType,
)


class ManifoldAdapter:
    """Adapter for Manifold Markets.

    Manifold uses play money (mana) and has:
    - Binary, multiple choice, and numeric markets
    - Automated market maker (AMM) pricing
    - Simple API with no authentication for reads
    - API key required for trading

    Example:
        >>> adapter = ManifoldAdapter(api_key="your-api-key")
        >>> markets = adapter.get_markets({"category": "politics"})
        >>> for market in markets:
        ...     print(f"{market.question}: {market.market_prob:.1%}")
    """

    def __init__(self, api_key: str | None = None):
        """Initialize Manifold adapter.

        Args:
            api_key: Manifold API key (required for trading, optional for reads).
        """
        self.api_key = api_key
        self.base_url = "https://api.manifold.markets/v0"

    def get_markets(self, filters: dict | None = None) -> list[MarketState]:
        """Fetch markets from Manifold.

        Manifold API returns markets with:
        - question: Market question
        - id: Unique identifier
        - probability: Current probability (binary markets)
        - pool: AMM liquidity pool
        - volume24Hours: 24h trading volume
        - createdTime: Market creation time
        - closeTime: Market close time

        Args:
            filters: Optional filters:
                - category: Market category (tag)
                - min_liquidity: Minimum pool size
                - min_volume: Minimum 24h volume
                - binary_only: Only binary markets

        Returns:
            List of MarketState objects.

        Example:
            >>> markets = adapter.get_markets({
            ...     "min_liquidity": 1000,
            ...     "binary_only": True
            ... })
        """
        # TODO: Implement actual API call
        # import requests
        # response = requests.get(f"{self.base_url}/markets")
        # markets = response.json()
        #
        # # Filter binary markets
        # binary_markets = [m for m in markets if m["outcomeType"] == "BINARY"]
        #
        # # Apply filters
        # if filters:
        #     if filters.get("min_liquidity"):
        #         binary_markets = [m for m in binary_markets if m.get("pool", {}).get("YES", 0) + m.get("pool", {}).get("NO", 0) >= filters["min_liquidity"]]
        #     if filters.get("min_volume"):
        #         binary_markets = [m for m in binary_markets if m.get("volume24Hours", 0) >= filters["min_volume"]]
        #
        # return [self._convert_market(m) for m in binary_markets]

        # Placeholder
        return []

    def get_market(self, market_id: str) -> MarketState | None:
        """Fetch specific market by ID.

        Args:
            market_id: Manifold market ID.

        Returns:
            MarketState if found, None otherwise.
        """
        # TODO: Implement
        # import requests
        # response = requests.get(f"{self.base_url}/market/{market_id}")
        # if response.status_code == 200:
        #     return self._convert_market(response.json())
        return None

    def place_order(self, order: Order) -> ExecutionReport:
        """Place bet on Manifold.

        Manifold uses an AMM, so orders are always filled immediately
        at the current pool price. The "order" concept maps to "bet".

        Args:
            order: Order to execute (converted to bet).

        Returns:
            ExecutionReport with fill details.

        Raises:
            ValueError: If API key not set or order invalid.
        """
        if self.api_key is None:
            raise ValueError("API key required for trading")

        # TODO: Implement actual bet placement
        # import requests
        #
        # # Determine outcome based on side
        # outcome = "YES" if order.side == OrderSide.BUY else "NO"
        #
        # # Manifold uses amount (mana to spend), not size (shares to buy)
        # # We approximate: amount ≈ size * price
        # market = self.get_market(order.market_id)
        # if not market:
        #     raise ValueError(f"Market {order.market_id} not found")
        #
        # price = market.best_ask if order.side == OrderSide.BUY else market.best_bid
        # amount = order.size * price
        #
        # # Place bet
        # response = requests.post(
        #     f"{self.base_url}/bet",
        #     json={
        #         "contractId": order.market_id,
        #         "outcome": outcome,
        #         "amount": amount
        #     },
        #     headers={"Authorization": f"Key {self.api_key}"}
        # )
        #
        # if response.status_code != 200:
        #     raise Exception(f"Bet failed: {response.text}")
        #
        # result = response.json()
        # return self._convert_execution(order, result)

        raise NotImplementedError("Bet placement not yet implemented")

    def submit_order(self, order: Order) -> ExecutionReport:
        """Compatibility alias for live-trading adapters."""
        return self.place_order(order)

    def cancel_order(self, market_id: str, order_id: str) -> bool:
        """Cancel outstanding bet.

        Note: Manifold uses AMM, so bets are immediately filled.
        This method is a no-op for compatibility.

        Args:
            market_id: Market identifier.
            order_id: Bet identifier.

        Returns:
            False (cancellation not supported on AMM).
        """
        # AMM markets don't have pending orders to cancel
        return False

    def get_position(self, market_id: str) -> float:
        """Get current position in a market.

        Args:
            market_id: Market identifier.

        Returns:
            Position size (shares held).
        """
        # TODO: Implement
        # Get user's bets in this market and calculate net position
        # import requests
        # response = requests.get(
        #     f"{self.base_url}/bets",
        #     params={"contractId": market_id},
        #     headers={"Authorization": f"Key {self.api_key}"}
        # )
        # bets = response.json()
        #
        # # Calculate net shares
        # yes_shares = sum(b["shares"] for b in bets if b["outcome"] == "YES")
        # no_shares = sum(b["shares"] for b in bets if b["outcome"] == "NO")
        #
        # return yes_shares - no_shares

        return 0.0

    def get_balance(self) -> float:
        """Get mana balance.

        Returns:
            Available mana balance.
        """
        # TODO: Implement
        # import requests
        # response = requests.get(
        #     f"{self.base_url}/me",
        #     headers={"Authorization": f"Key {self.api_key}"}
        # )
        # user = response.json()
        # return user.get("balance", 0.0)

        return 0.0

    def _convert_market(self, raw_market: dict[str, Any]) -> MarketState:
        """Convert Manifold API response to MarketState.

        Manifold API format:
        {
            "id": "abc123",
            "question": "Will X happen?",
            "outcomeType": "BINARY",
            "probability": 0.65,
            "pool": {"YES": 1000, "NO": 538.46},
            "volume24Hours": 5000,
            "uniqueBettorCount": 42,
            "createdTime": 1234567890000,
            "closeTime": 1234567890000,
            ...
        }
        """
        # Parse basic info
        market_id = f"manifold-{raw_market['id']}"
        question = raw_market["question"]

        # Parse probability
        market_prob = raw_market["probability"]

        # Parse dates
        close_time_ms = raw_market.get("closeTime", 0)
        expiry = datetime.fromtimestamp(close_time_ms / 1000) if close_time_ms else datetime.now()

        # Determine category (Manifold doesn't have categories, use tags)
        tags = raw_market.get("tags", [])
        category = self._parse_category(tags)

        # Calculate bid/ask from AMM pool
        # Manifold uses constant product AMM: k = YES_pool * NO_pool
        # Price moves based on trade size
        pool_yes = raw_market.get("pool", {}).get("YES", 0)
        pool_no = raw_market.get("pool", {}).get("NO", 0)

        # Estimate spread (AMM has implicit spread based on trade size)
        # For small trades, spread is roughly 1-2%
        spread = 0.02
        best_bid = market_prob - spread / 2
        best_ask = market_prob + spread / 2

        # Liquidity is pool size
        bid_liquidity = pool_no  # To buy YES, we trade against NO pool
        ask_liquidity = pool_yes  # To sell YES, we trade against YES pool

        # Volume and traders
        volume_24h = raw_market.get("volume24Hours", 0)
        num_traders = raw_market.get("uniqueBettorCount", 0)

        return MarketState(
            market_id=market_id,
            question=question,
            market_prob=market_prob,
            expiry=expiry,
            category=category,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_liquidity=bid_liquidity,
            ask_liquidity=ask_liquidity,
            volume_24h=volume_24h,
            num_traders=num_traders,
            metadata={"raw": raw_market},
        )

    def _parse_category(self, tags: list[str]) -> MarketCategory:
        """Parse tags to category."""
        # Map common tags to categories
        tag_str = " ".join(tags).lower()

        if any(word in tag_str for word in ["politics", "election", "president"]):
            return MarketCategory.POLITICS
        elif any(word in tag_str for word in ["sports", "nfl", "nba", "soccer"]):
            return MarketCategory.SPORTS
        elif any(word in tag_str for word in ["economics", "economy", "gdp", "inflation"]):
            return MarketCategory.ECONOMICS
        elif any(word in tag_str for word in ["crypto", "bitcoin", "ethereum"]):
            return MarketCategory.CRYPTO
        elif any(word in tag_str for word in ["science", "ai", "technology"]):
            return MarketCategory.SCIENCE

        return MarketCategory.OTHER

    def _convert_execution(self, order: Order, result: dict[str, Any]) -> ExecutionReport:
        """Convert Manifold bet result to ExecutionReport.

        Manifold bet response:
        {
            "betId": "abc123",
            "amount": 100,
            "shares": 153.85,
            "probBefore": 0.65,
            "probAfter": 0.66,
            "fees": 1.0,
            ...
        }
        """
        # TODO: Parse actual result
        shares = result.get("shares", 0)
        amount = result.get("amount", 0)
        avg_price = amount / shares if shares > 0 else 0
        fees = result.get("fees", 0)

        # Calculate slippage
        prob_before = result.get("probBefore", 0)
        prob_after = result.get("probAfter", 0)
        slippage_bps = abs(prob_after - prob_before) / prob_before * 10_000 if prob_before > 0 else 0

        return ExecutionReport(
            order=order,
            filled_size=shares,
            avg_fill_price=avg_price,
            fills=[(avg_price, shares)],
            slippage_bps=slippage_bps,
            fee_total=fees,
            timestamp=datetime.now(),
            metadata={"bet_id": result.get("betId")},
        )
