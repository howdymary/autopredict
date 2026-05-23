"""Routing strategy that selects a specialist model based on snapshot labels."""

from __future__ import annotations

from autopredict.domains.base import SpecialistOrderPolicy, snapshot_label
from autopredict.domains.finance import FinanceSpecialistStrategy
from autopredict.domains.generic import GenericSpecialistStrategy
from autopredict.domains.politics import PoliticsSpecialistStrategy
from autopredict.domains.weather import WeatherSpecialistStrategy
from autopredict.prediction_market.types import MarketSignal, MarketSnapshot, StrategyContext


class RoutedSpecialistStrategy:
    """Route markets to finance, politics, or generic specialist strategies."""

    name = "routed_specialist"

    def __init__(self, policy: SpecialistOrderPolicy | None = None) -> None:
        self.policy = policy or SpecialistOrderPolicy()
        self.finance = FinanceSpecialistStrategy(policy=self.policy)
        self.politics = PoliticsSpecialistStrategy(policy=self.policy)
        self.weather = WeatherSpecialistStrategy(policy=self.policy)
        self.generic = GenericSpecialistStrategy(policy=self.policy)

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> MarketSignal | None:
        strategy = self._select_strategy(snapshot)
        return strategy.generate_signal(snapshot, context)

    def build_orders(
        self,
        snapshot: MarketSnapshot,
        signal: MarketSignal,
        context: StrategyContext,
    ) -> list:
        strategy = self._select_strategy(snapshot)
        return strategy.build_orders(snapshot, signal, context)

    def _select_strategy(self, snapshot: MarketSnapshot):
        domain = snapshot_label(snapshot, "domain", "")
        category = snapshot.market.category.value
        if domain == "finance" or category in {"economics", "crypto"}:
            return self.finance
        if domain == "politics" or category == "politics":
            return self.politics
        if domain == "weather":
            return self.weather
        return self.generic
