"""Shared domain adapter contracts and specialist-strategy helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from autopredict.core.types import Order, OrderSide, OrderType

if TYPE_CHECKING:
    from autopredict.prediction_market.types import (
        MarketSignal,
        MarketSnapshot,
        StrategyContext,
    )

REQUIRED_METADATA_KEYS = ("domain", "market_family", "regime", "feature_version")


@dataclass(frozen=True)
class DomainFeatureBundle:
    """Normalized domain payload for later strategy and split logic."""

    domain: str
    features: dict[str, Any]
    metadata: dict[str, Any]
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        missing = set(REQUIRED_METADATA_KEYS).difference(self.metadata)
        if missing:
            raise ValueError(f"missing required metadata keys: {sorted(missing)}")
        if self.metadata["domain"] != self.domain:
            raise ValueError("metadata.domain must match bundle domain")

    def as_snapshot_inputs(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return copies shaped for scaffold market snapshots."""

        return dict(self.features), dict(self.metadata)


class DomainAdapter(Protocol):
    """Protocol for turning normalized evidence into a feature bundle."""

    name: str

    def build_bundle(self) -> DomainFeatureBundle:
        """Return normalized features plus stable split labels."""


@dataclass(frozen=True)
class SpecialistOrderPolicy:
    """Shared order policy for simple domain-specialist strategies."""

    min_abs_edge: float = 0.03
    max_bankroll_fraction: float = 0.05
    aggressive_edge: float = 0.08
    urgency_regimes: tuple[str, ...] = field(
        default_factory=lambda: ("post_release", "warning", "breaking_news")
    )

    def __post_init__(self) -> None:
        if self.min_abs_edge < 0:
            raise ValueError("min_abs_edge must be non-negative")
        if not (0.0 < self.max_bankroll_fraction <= 1.0):
            raise ValueError("max_bankroll_fraction must be in (0, 1]")
        if self.aggressive_edge < self.min_abs_edge:
            raise ValueError("aggressive_edge must be >= min_abs_edge")


def snapshot_label(snapshot: "MarketSnapshot", key: str, default: str = "unknown") -> str:
    """Return one stable label from the snapshot labels or features."""

    if key in snapshot.labels:
        return str(snapshot.labels[key])
    if key in snapshot.features:
        return str(snapshot.features[key])
    return default


def build_single_edge_order(
    snapshot: "MarketSnapshot",
    signal: "MarketSignal",
    context: "StrategyContext",
    *,
    strategy_name: str,
    policy: SpecialistOrderPolicy,
) -> list[Order]:
    """Translate one signal into a single executable scaffold order."""

    edge = signal.edge_against(snapshot.market.market_prob)
    abs_edge = abs(edge)
    if abs_edge < policy.min_abs_edge:
        return []

    side = OrderSide.BUY if edge > 0 else OrderSide.SELL
    visible_liquidity = (
        snapshot.market.ask_liquidity if side == OrderSide.BUY else snapshot.market.bid_liquidity
    )
    if visible_liquidity <= 0.0:
        return []

    bankroll_budget = context.portfolio.cash * policy.max_bankroll_fraction * max(
        signal.confidence,
        0.25,
    )
    estimated_contract_cost = max(snapshot.market.mid_price, snapshot.venue.tick_size, 0.01)
    target_size = bankroll_budget / estimated_contract_cost
    size = min(visible_liquidity, target_size)
    if size < snapshot.venue.min_order_size:
        return []

    regime = snapshot_label(snapshot, "regime", "")
    report_card = signal.metadata.get("report_card")
    selection_features = (
        report_card.get("selection_features", {})
        if isinstance(report_card, dict)
        else {}
    )
    order_metadata = {
        "strategy": strategy_name,
        "model": signal.metadata.get("model"),
        "dataset_name": signal.metadata.get("dataset_name"),
        "dataset_version": signal.metadata.get("dataset_version"),
        "domain": snapshot_label(snapshot, "domain"),
        "market_family": snapshot_label(snapshot, "market_family"),
        "regime": regime or "unknown",
        "feature_version": snapshot_label(snapshot, "feature_version"),
        "edge": edge,
        "confidence": signal.confidence,
    }
    if isinstance(report_card, dict) and report_card:
        order_metadata["report_card"] = dict(report_card)
    if isinstance(selection_features, dict):
        coverage_score = selection_features.get("coverage_score")
        stability = selection_features.get("held_out_calibration_stability")
        if isinstance(coverage_score, (int, float)):
            order_metadata["coverage_score"] = float(coverage_score)
        if isinstance(stability, (int, float)):
            order_metadata["held_out_calibration_stability"] = float(stability)
    if abs_edge >= policy.aggressive_edge or regime in policy.urgency_regimes:
        return [
            Order(
                market_id=snapshot.market.market_id,
                side=side,
                order_type=OrderType.MARKET,
                size=size,
                timestamp=datetime.now(),
                metadata=order_metadata,
            )
        ]

    limit_price = min(max(snapshot.market.mid_price, snapshot.market.best_bid), snapshot.market.best_ask)
    return [
        Order(
            market_id=snapshot.market.market_id,
            side=side,
            order_type=OrderType.LIMIT,
            size=size,
            limit_price=limit_price,
            timestamp=datetime.now(),
            metadata=order_metadata,
        )
    ]
