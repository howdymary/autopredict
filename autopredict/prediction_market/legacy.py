"""Deprecated compatibility adapters excluded from maintained registries and genomes."""

from __future__ import annotations

from autopredict.prediction_market.types import MarketSignal, MarketSnapshot, StrategyContext
from autopredict.strategies.mispriced_probability import MispricedProbabilityStrategy


class LegacyMispricedStrategyAdapter:
    """Compatibility bridge for pre-provider callers; never registered by default."""

    def __init__(self, strategy: MispricedProbabilityStrategy | None = None) -> None:
        self._strategy = strategy or MispricedProbabilityStrategy()

    @property
    def name(self) -> str:
        return "legacy_mispriced_probability"

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> MarketSignal | None:
        model = context.metadata.get("probability_model")
        if model is None:
            return None
        edge = self._strategy.estimate_edge(snapshot.market, {"probability_model": model})
        if edge is None:
            return None
        return MarketSignal(
            fair_prob=edge.fair_prob,
            confidence=edge.confidence,
            rationale="Deprecated legacy probability-model adapter",
            tags=("legacy", "mispriced_probability"),
            metadata={
                "edge_bps": edge.edge_bps,
                "forecast": edge.metadata.get("forecast"),
                "model": edge.metadata.get("model"),
            },
        )

    def build_orders(
        self,
        snapshot: MarketSnapshot,
        signal: MarketSignal,
        context: StrategyContext,
    ):
        del signal
        model = context.metadata.get("probability_model")
        if model is None:
            return []
        return self._strategy.decide(
            snapshot.market,
            context.position,
            {"probability_model": model, "portfolio": context.portfolio},
        )


__all__ = ["LegacyMispricedStrategyAdapter"]
