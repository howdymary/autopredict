"""Agent entrypoints for the Step 1 prediction-market scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autopredict.agent import (
    AgentConfig as LegacyAgentConfig,
    AutoPredictAgent as LegacyAutoPredictAgent,
    ExecutionStrategy as LegacyExecutionStrategy,
    MarketState as LegacyMarketState,
    ProposedOrder as LegacyProposedOrder,
)
from autopredict.core.types import MarketState, Portfolio

from autopredict.prediction_market.strategy import (
    DirectProbabilityStrategy,
    PredictionMarketStrategy,
)
from autopredict.prediction_market.types import (
    AgentDecision,
    DecisionStatus,
    MarketSnapshot,
    StrategyContext,
    VenueConfig,
)


@dataclass(frozen=True)
class AgentRunConfig:
    """Runtime config for the new prediction-market scaffold."""

    min_signal_confidence: float = 0.5
    max_orders_per_decision: int = 10

    def __post_init__(self) -> None:
        if not (0.0 <= self.min_signal_confidence <= 1.0):
            raise ValueError(
                "min_signal_confidence must be in [0, 1], "
                f"got {self.min_signal_confidence}"
            )
        if self.max_orders_per_decision <= 0:
            raise ValueError("max_orders_per_decision must be positive")


class PredictionMarketAgent:
    """Composable agent that evaluates one market snapshot at a time."""

    def __init__(
        self,
        strategy: PredictionMarketStrategy | None = None,
        config: AgentRunConfig | None = None,
    ) -> None:
        self.strategy = strategy or DirectProbabilityStrategy()
        self.config = config or AgentRunConfig()

    def evaluate_market(
        self,
        market: MarketState,
        *,
        venue: VenueConfig,
        portfolio: Portfolio,
        position=None,
        context_metadata: dict[str, Any] | None = None,
        snapshot_features: dict[str, Any] | None = None,
    ) -> AgentDecision:
        """Evaluate a single market and return a typed decision."""

        metadata = dict(context_metadata or {})
        features = dict(snapshot_features or {})
        for key, value in metadata.items():
            features.setdefault(key, value)
        labels = _derive_snapshot_labels(market, metadata, features)

        snapshot = MarketSnapshot(
            market=market,
            venue=venue,
            features=features,
            labels=labels,
        )
        context = StrategyContext(
            portfolio=portfolio,
            position=position or portfolio.positions.get(market.market_id),
            metadata=metadata,
        )

        signal = self.strategy.generate_signal(snapshot, context)
        if signal is None:
            return AgentDecision(
                market_id=market.market_id,
                status=DecisionStatus.SKIP,
                reasons=("strategy_returned_no_signal",),
                metadata=labels,
            )

        if signal.confidence < self.config.min_signal_confidence:
            return AgentDecision(
                market_id=market.market_id,
                status=DecisionStatus.SKIP,
                signal=signal,
                reasons=("signal_below_confidence_floor",),
                metadata=labels,
            )

        orders = tuple(self.strategy.build_orders(snapshot, signal, context))
        if not orders:
            return AgentDecision(
                market_id=market.market_id,
                status=DecisionStatus.HOLD,
                signal=signal,
                metadata=labels,
            )

        return AgentDecision(
            market_id=market.market_id,
            status=DecisionStatus.TRADE,
            signal=signal,
            orders=orders[: self.config.max_orders_per_decision],
            metadata=labels,
        )


def _derive_snapshot_labels(
    market: MarketState,
    metadata: dict[str, Any],
    features: dict[str, Any],
) -> dict[str, Any]:
    """Extract stable snapshot labels without polluting them with runtime objects."""

    labels: dict[str, Any] = {}
    for key in ("domain", "market_family", "regime", "feature_version", "category"):
        if key in metadata:
            labels[key] = metadata[key]
        elif key in features:
            labels[key] = features[key]
        elif key in market.metadata:
            labels[key] = market.metadata[key]
    labels.setdefault("category", market.category.value)
    return labels


# Compatibility exports for the legacy root-level experiment harness.
AgentConfig = LegacyAgentConfig
AutoPredictAgent = LegacyAutoPredictAgent
ExecutionStrategy = LegacyExecutionStrategy
MarketState = LegacyMarketState
LegacyMarketState = LegacyMarketState
ProposedOrder = LegacyProposedOrder


__all__ = [
    "AgentConfig",
    "AgentRunConfig",
    "AutoPredictAgent",
    "ExecutionStrategy",
    "MarketState",
    "LegacyMarketState",
    "PredictionMarketAgent",
    "ProposedOrder",
]
