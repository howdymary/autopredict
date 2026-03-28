"""Mutation utilities for self-improving prediction-market agents."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from autopredict.domains import RoutedSpecialistStrategy, SpecialistOrderPolicy
from autopredict.prediction_market import (
    AgentRunConfig,
    LegacyMispricedStrategyAdapter,
    PredictionMarketAgent,
)
from autopredict.strategies.base import RiskLimits
from autopredict.strategies.mispriced_probability import MispricedProbabilityStrategy


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


@dataclass(frozen=True)
class StrategyGenome:
    """Serializable parameter set for one strategy variant."""

    name: str
    strategy_kind: str = "legacy_mispriced"
    kelly_fraction: float = 0.25
    aggressive_edge_threshold: float = 0.15
    min_spread_capture: float = 10.0
    max_position_size: float = 500.0
    max_total_exposure: float = 5000.0
    max_daily_loss: float = 1000.0
    max_leverage: float = 2.0
    min_edge_threshold: float = 0.05
    min_confidence: float = 0.70
    max_bankroll_fraction: float = 0.05
    metadata: dict[str, Any] = field(default_factory=dict)

    def build_strategy(self):
        """Construct the scaffold bridge strategy for this genome."""

        if self.strategy_kind == "routed_question_model":
            return RoutedSpecialistStrategy(
                policy=SpecialistOrderPolicy(
                    min_abs_edge=self.min_edge_threshold,
                    max_bankroll_fraction=self.max_bankroll_fraction,
                    aggressive_edge=self.aggressive_edge_threshold,
                )
            )

        strategy = MispricedProbabilityStrategy(
            risk_limits=RiskLimits(
                max_position_size=self.max_position_size,
                max_total_exposure=self.max_total_exposure,
                max_daily_loss=self.max_daily_loss,
                max_leverage=self.max_leverage,
                min_edge_threshold=self.min_edge_threshold,
                min_confidence=self.min_confidence,
            ),
            kelly_fraction=self.kelly_fraction,
            aggressive_edge_threshold=self.aggressive_edge_threshold,
            min_spread_capture=self.min_spread_capture,
        )
        return LegacyMispricedStrategyAdapter(strategy=strategy)

    def build_agent(
        self,
        run_config: AgentRunConfig | None = None,
    ) -> PredictionMarketAgent:
        """Construct a scaffold agent for this genome."""

        return PredictionMarketAgent(
            strategy=self.build_strategy(),
            config=run_config or AgentRunConfig(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable dictionary form for logging."""

        return {
            "name": self.name,
            "strategy_kind": self.strategy_kind,
            "kelly_fraction": self.kelly_fraction,
            "aggressive_edge_threshold": self.aggressive_edge_threshold,
            "min_spread_capture": self.min_spread_capture,
            "max_position_size": self.max_position_size,
            "max_total_exposure": self.max_total_exposure,
            "max_daily_loss": self.max_daily_loss,
            "max_leverage": self.max_leverage,
            "min_edge_threshold": self.min_edge_threshold,
            "min_confidence": self.min_confidence,
            "max_bankroll_fraction": self.max_bankroll_fraction,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MutationConfig:
    """Settings for deterministic strategy mutation."""

    seed: int = 0
    population_size: int = 5
    relative_step: float = 0.25

    def __post_init__(self) -> None:
        if self.population_size <= 0:
            raise ValueError("population_size must be positive")
        if self.relative_step <= 0:
            raise ValueError("relative_step must be positive")


class StrategyMutator:
    """Generate deterministic variants from a baseline genome."""

    def __init__(self, config: MutationConfig | None = None) -> None:
        self.config = config or MutationConfig()

    def generate_population(self, base: StrategyGenome) -> tuple[StrategyGenome, ...]:
        """Return baseline plus directional and stochastic variants."""

        population = [base]
        if self.config.population_size == 1:
            return tuple(population)

        population.append(self._directional_variant(base, label="aggressive", direction=1.0))
        if self.config.population_size == 2:
            return tuple(population)

        population.append(self._directional_variant(base, label="conservative", direction=-1.0))
        if self.config.population_size == 3:
            return tuple(population)

        rng = random.Random(self.config.seed)
        for index in range(3, self.config.population_size):
            population.append(self._stochastic_variant(base, rng, index))
        return tuple(population)

    def _directional_variant(
        self,
        base: StrategyGenome,
        *,
        label: str,
        direction: float,
    ) -> StrategyGenome:
        step = self.config.relative_step
        return StrategyGenome(
            name=f"{base.name}_{label}",
            strategy_kind=base.strategy_kind,
            kelly_fraction=_clamp(base.kelly_fraction * (1.0 + direction * step), 0.05, 1.0),
            aggressive_edge_threshold=_clamp(
                base.aggressive_edge_threshold * (1.0 - direction * step * 0.5),
                0.02,
                0.50,
            ),
            min_spread_capture=_clamp(
                base.min_spread_capture * (1.0 - direction * step),
                0.0,
                100.0,
            ),
            max_position_size=_clamp(
                base.max_position_size * (1.0 + direction * step),
                10.0,
                5_000.0,
            ),
            max_total_exposure=_clamp(
                base.max_total_exposure * (1.0 + direction * step),
                100.0,
                50_000.0,
            ),
            max_daily_loss=_clamp(
                base.max_daily_loss * (1.0 + direction * step * 0.5),
                10.0,
                10_000.0,
            ),
            max_leverage=_clamp(
                base.max_leverage * (1.0 + direction * step * 0.25),
                1.0,
                5.0,
            ),
            min_edge_threshold=_clamp(
                base.min_edge_threshold * (1.0 - direction * step * 0.5),
                0.01,
                0.30,
            ),
            min_confidence=_clamp(
                base.min_confidence * (1.0 - direction * step * 0.25),
                0.50,
                0.99,
            ),
            max_bankroll_fraction=_clamp(
                base.max_bankroll_fraction * (1.0 + direction * step * 0.5),
                0.01,
                0.25,
            ),
            metadata={"parent": base.name, "mutation": label},
        )

    def _stochastic_variant(
        self,
        base: StrategyGenome,
        rng: random.Random,
        index: int,
    ) -> StrategyGenome:
        def perturb(value: float, lower: float, upper: float) -> float:
            factor = 1.0 + rng.uniform(-self.config.relative_step, self.config.relative_step)
            return _clamp(value * factor, lower, upper)

        return StrategyGenome(
            name=f"{base.name}_mutant_{index:02d}",
            strategy_kind=base.strategy_kind,
            kelly_fraction=perturb(base.kelly_fraction, 0.05, 1.0),
            aggressive_edge_threshold=perturb(base.aggressive_edge_threshold, 0.02, 0.50),
            min_spread_capture=perturb(base.min_spread_capture, 0.0, 100.0),
            max_position_size=perturb(base.max_position_size, 10.0, 5_000.0),
            max_total_exposure=perturb(base.max_total_exposure, 100.0, 50_000.0),
            max_daily_loss=perturb(base.max_daily_loss, 10.0, 10_000.0),
            max_leverage=perturb(base.max_leverage, 1.0, 5.0),
            min_edge_threshold=perturb(base.min_edge_threshold, 0.01, 0.30),
            min_confidence=perturb(base.min_confidence, 0.50, 0.99),
            max_bankroll_fraction=perturb(base.max_bankroll_fraction, 0.01, 0.25),
            metadata={"parent": base.name, "mutation": "stochastic", "index": index},
        )
