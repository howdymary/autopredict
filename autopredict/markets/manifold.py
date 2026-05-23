"""Explicitly unsupported Manifold Markets adapter scaffold.

The repository does not currently maintain a verified Manifold API adapter.
Failing closed is safer than shipping inferred API payload parsing or simulated
venue behavior under a production adapter name.
"""

from __future__ import annotations

from autopredict.core.types import ExecutionReport, MarketState, Order


class ManifoldAdapter:
    """Fail-closed scaffold for a future verified Manifold integration.

    Manifold is a play-money prediction market platform. AutoPredict keeps this
    class as a named venue scaffold, but all public methods raise until a real
    adapter is implemented and tested against live API responses.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self.base_url = "https://api.manifold.markets/v0"

    def _unsupported(self, operation: str) -> NotImplementedError:
        return NotImplementedError(
            f"Manifold {operation} is not implemented. "
            "Implement and test against live Manifold API responses before enabling this venue."
        )

    def get_markets(self, filters: dict | None = None) -> list[MarketState]:
        """Fetch markets from Manifold."""

        raise self._unsupported("market discovery")

    def get_market(self, market_id: str) -> MarketState | None:
        """Fetch a specific market by ID."""

        raise self._unsupported("single-market fetch")

    def place_order(self, order: Order) -> ExecutionReport:
        """Place a Manifold bet."""

        raise self._unsupported("bet placement")

    def submit_order(self, order: Order) -> ExecutionReport:
        """Compatibility alias for live-trading adapters."""

        return self.place_order(order)

    def cancel_order(self, market_id: str, order_id: str) -> bool:
        """Cancel an outstanding order."""

        raise self._unsupported("order cancellation")

    def get_position(self, market_id: str) -> float:
        """Get current position in a market."""

        raise self._unsupported("position lookup")

    def get_balance(self) -> float:
        """Get venue balance."""

        raise self._unsupported("balance lookup")
