"""Built-in bridge strategies for the prediction-market scaffold."""

from __future__ import annotations

from autopredict.prediction_market.registry import StrategyRegistry


def create_default_registry() -> StrategyRegistry:
    """Create the maintained registry without opaque legacy model injection."""

    from autopredict.domains.finance import FinanceSpecialistStrategy
    from autopredict.domains.politics import PoliticsSpecialistStrategy
    from autopredict.domains.router import RoutedSpecialistStrategy
    from autopredict.domains.weather import WeatherSpecialistStrategy

    registry = StrategyRegistry()
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
    registry.register(
        "routed_specialist",
        factory=RoutedSpecialistStrategy,
        description="Routes markets to question-conditioned specialist models by domain/category.",
        tags=("domain", "routing", "phase3"),
    )
    return registry
