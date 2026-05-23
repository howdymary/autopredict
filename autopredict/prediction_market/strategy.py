"""Strategy interfaces for the Step 1 prediction-market scaffold."""

from __future__ import annotations

from typing import Protocol

from autopredict.core.types import Order

from autopredict.prediction_market.types import MarketSignal, MarketSnapshot, StrategyContext


class PredictionMarketStrategy(Protocol):
    """Protocol for turning market snapshots into signals and orders."""

    name: str

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> MarketSignal | None:
        """Return a market signal, or ``None`` to skip the snapshot."""
        ...

    def build_orders(
        self,
        snapshot: MarketSnapshot,
        signal: MarketSignal,
        context: StrategyContext,
    ) -> list[Order]:
        """Convert a market signal into executable orders."""
        ...


class DirectProbabilityStrategy:
    """Minimal built-in strategy that reads fair value from snapshot features."""

    name = "direct_probability"

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> MarketSignal | None:
        del context
        fair_prob = snapshot.features.get("fair_prob", snapshot.market.market_prob)
        confidence = snapshot.features.get("confidence", 1.0)
        return MarketSignal(
            fair_prob=float(fair_prob),
            confidence=float(confidence),
            rationale="Direct fair-probability signal from snapshot features",
            tags=("baseline", "direct"),
        )

    def build_orders(
        self,
        snapshot: MarketSnapshot,
        signal: MarketSignal,
        context: StrategyContext,
    ) -> list[Order]:
        del snapshot, signal, context
        return []
