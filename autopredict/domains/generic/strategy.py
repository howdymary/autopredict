"""Generic specialist strategy backed by a combined question-conditioned model."""

from __future__ import annotations

from autopredict.domains.base import (
    SpecialistOrderPolicy,
    build_single_edge_order,
    snapshot_label,
)
from autopredict.domains.generic.model import build_default_generic_model
from autopredict.domains.modeling import QuestionConditionedLinearModel
from autopredict.prediction_market.types import MarketSignal, MarketSnapshot, StrategyContext


class GenericSpecialistStrategy:
    """Fallback strategy for categories without a dedicated domain model."""

    name = "generic_specialist"

    def __init__(
        self,
        policy: SpecialistOrderPolicy | None = None,
        model: QuestionConditionedLinearModel | None = None,
    ) -> None:
        self.policy = policy or SpecialistOrderPolicy(
            min_abs_edge=0.03,
            max_bankroll_fraction=0.05,
            aggressive_edge=0.08,
            urgency_regimes=("short", "breaking_news", "warning"),
        )
        self.model = model or build_default_generic_model()

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> MarketSignal | None:
        del context
        family = snapshot_label(snapshot, "market_family", snapshot.market.category.value)
        regime = snapshot_label(snapshot, "regime", "steady")
        prediction = self.model.predict(
            snapshot.market.question,
            {
                **snapshot.features,
                "market_prob": snapshot.market.market_prob,
                "spread_bps": snapshot.market.spread_bps,
                "total_liquidity": snapshot.market.total_liquidity,
            },
            snapshot.labels,
        )
        return MarketSignal(
            fair_prob=prediction.probability,
            confidence=prediction.confidence,
            rationale=prediction.rationale,
            tags=("domain", "generic", "model", family, regime),
            metadata={
                **prediction.metadata,
                "domain": snapshot_label(snapshot, "domain", "generic"),
                "market_family": family,
                "regime": regime,
            },
        )

    def build_orders(
        self,
        snapshot: MarketSnapshot,
        signal: MarketSignal,
        context: StrategyContext,
    ) -> list:
        return build_single_edge_order(
            snapshot,
            signal,
            context,
            strategy_name=self.name,
            policy=self.policy,
        )
