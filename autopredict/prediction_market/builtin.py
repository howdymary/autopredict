"""Built-in bridge strategies for the prediction-market scaffold."""

from __future__ import annotations

from autopredict.prediction_market.registry import StrategyRegistry
from autopredict.prediction_market.types import MarketSignal, MarketSnapshot, StrategyContext
from autopredict.strategies.mispriced_probability import MispricedProbabilityStrategy


class LegacyMispricedStrategyAdapter:
    """Expose ``MispricedProbabilityStrategy`` via the new scaffold protocol."""

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
        """Generate a typed market signal from the legacy strategy."""

        model = self._resolve_probability_model(snapshot, context)
        if model is None:
            return None

        edge = self._strategy.estimate_edge(
            snapshot.market,
            {"probability_model": model},
        )
        if edge is None:
            return None

        return MarketSignal(
            fair_prob=edge.fair_prob,
            confidence=edge.confidence,
            rationale="Delegated from MispricedProbabilityStrategy",
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
        """Delegate executable order construction to the legacy strategy."""

        del signal
        model = self._resolve_probability_model(snapshot, context)
        if model is None:
            return []

        return self._strategy.decide(
            snapshot.market,
            context.position,
            {
                "probability_model": model,
                "portfolio": context.portfolio,
            },
        )

    @staticmethod
    def _resolve_probability_model(
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> object | None:
        return context.metadata.get("probability_model") or snapshot.features.get(
            "probability_model"
        )


def create_default_registry() -> StrategyRegistry:
    """Create a registry preloaded with the legacy baseline strategy."""

    from autopredict.domains.finance import FinanceSpecialistStrategy
    from autopredict.domains.politics import PoliticsSpecialistStrategy
    from autopredict.domains.weather import WeatherSpecialistStrategy

    registry = StrategyRegistry()
    registry.register(
        "legacy_mispriced_probability",
        factory=LegacyMispricedStrategyAdapter,
        description="Adapter around the existing mispriced probability strategy.",
        tags=("baseline", "legacy", "step1"),
    )
    registry.register(
        "finance_specialist",
        factory=FinanceSpecialistStrategy,
        description="Simple macro- and rates-aware finance specialist heuristic.",
        tags=("domain", "finance", "phase2"),
    )
    registry.register(
        "weather_specialist",
        factory=WeatherSpecialistStrategy,
        description="Simple forecast- and severity-aware weather specialist heuristic.",
        tags=("domain", "weather", "phase2"),
    )
    registry.register(
        "politics_specialist",
        factory=PoliticsSpecialistStrategy,
        description="Simple polling- and event-aware politics specialist heuristic.",
        tags=("domain", "politics", "phase2"),
    )
    return registry
