"""Finance specialist strategy backed by a question-conditioned model."""

from __future__ import annotations

from autopredict.domains.base import (
    SpecialistOrderPolicy,
    build_single_edge_order,
    snapshot_label,
)
from autopredict.domains.finance.model import build_default_finance_model
from autopredict.domains.modeling import QuestionConditionedLinearModel
from autopredict.prediction_market.types import MarketSignal, MarketSnapshot, StrategyContext


class FinanceSpecialistStrategy:
    """Model-backed finance strategy driven by question and bundle features."""

    name = "finance_specialist"

    def __init__(
        self,
        policy: SpecialistOrderPolicy | None = None,
        model: QuestionConditionedLinearModel | None = None,
    ) -> None:
        self.policy = policy or SpecialistOrderPolicy(
            min_abs_edge=0.025,
            max_bankroll_fraction=0.06,
            aggressive_edge=0.07,
            urgency_regimes=("post_release", "high_vol"),
        )
        self.model = model or build_default_finance_model()

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> MarketSignal | None:
        del context
        if snapshot_label(snapshot, "domain", "") != "finance":
            return None

        family = snapshot_label(snapshot, "market_family", "macro")
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
            tags=("domain", "finance", "model", family, regime),
            metadata={
                **prediction.metadata,
                "domain": "finance",
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
