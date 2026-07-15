"""Learnable market-recalibration forecast for self-improving agents.

This module closes the central gap in the self-improvement loop: the loop can
search risk and execution genes, but the only source of trading edge -- the
forecast -- was frozen at the market-implied no-edge model (``fair_prob ==
market_prob``). With a frozen forecast every candidate produces identical
scores and zero trades, so the search landscape is flat.

The recalibration model gives the loop a real, *honest* forecast to improve. It
applies a monotonic recalibration of the market's own price::

    fair_prob = sigmoid(scale * logit(market_prob) + shift)

- ``scale = 1.0, shift = 0.0`` is the identity: ``fair_prob == market_prob``
  (no edge). This is the default, so nothing is fabricated out of thin air.
- Fitting on *real resolved outcomes* estimates how the market's historical
  prices deviate from realized frequencies (e.g. favorite-longshot bias). The
  fit is regularized toward the identity, so with little or well-calibrated
  data it stays close to no-edge; it only departs from the market where real
  data supports it. Held-out promotion in the walk-forward loop is the final
  guard against overfitting.

No market datasets are bundled here. Fitting requires the caller's own resolved
data, consistent with the package data policy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from autopredict.domains.base import (
    SpecialistOrderPolicy,
    build_single_edge_order,
    snapshot_label,
)
from autopredict.prediction_market.types import (
    MarketSignal,
    MarketSnapshot,
    StrategyContext,
)

_PROB_EPSILON = 1e-6

# Bounds keep the recalibration monotonic and prevent degenerate extrapolation.
MIN_SCALE = 0.2
MAX_SCALE = 3.0
MIN_SHIFT = -2.0
MAX_SHIFT = 2.0


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def logit(probability: float) -> float:
    """Return the log-odds of a probability, clipped away from 0 and 1."""

    clipped = _clamp(probability, _PROB_EPSILON, 1.0 - _PROB_EPSILON)
    return math.log(clipped / (1.0 - clipped))


def sigmoid(score: float) -> float:
    """Numerically stable logistic function."""

    if score >= 0:
        exp_term = math.exp(-score)
        return 1.0 / (1.0 + exp_term)
    exp_term = math.exp(score)
    return exp_term / (1.0 + exp_term)


@dataclass(frozen=True)
class MarketRecalibrationModel:
    """Monotonic two-parameter recalibration of a market-implied probability."""

    scale: float = 1.0
    shift: float = 0.0
    name: str = "market_recalibration"
    fit_sample_size: int = 0

    def __post_init__(self) -> None:
        if not (MIN_SCALE <= self.scale <= MAX_SCALE):
            raise ValueError(f"scale must be in [{MIN_SCALE}, {MAX_SCALE}], got {self.scale}")
        if not (MIN_SHIFT <= self.shift <= MAX_SHIFT):
            raise ValueError(f"shift must be in [{MIN_SHIFT}, {MAX_SHIFT}], got {self.shift}")

    @property
    def is_identity(self) -> bool:
        """Return whether the model reproduces the market price (no edge)."""

        return abs(self.scale - 1.0) < 1e-9 and abs(self.shift) < 1e-9

    def fair_probability(self, market_prob: float) -> float:
        """Return the recalibrated fair probability for a market price."""

        if self.is_identity:
            return _clamp(market_prob, 0.0, 1.0)
        return sigmoid(self.scale * logit(market_prob) + self.shift)

    def edge_against(self, market_prob: float) -> float:
        """Return the recalibrated edge in probability units."""

        return self.fair_probability(market_prob) - _clamp(market_prob, 0.0, 1.0)

    @classmethod
    def identity(cls) -> "MarketRecalibrationModel":
        """Return the no-edge identity model."""

        return cls(scale=1.0, shift=0.0)

    @classmethod
    def fit(
        cls,
        pairs: Sequence[Tuple[float, int]],
        *,
        learning_rate: float = 0.1,
        epochs: int = 400,
        identity_regularization: float = 0.05,
        min_samples: int = 0,
        name: str = "market_recalibration",
    ) -> "MarketRecalibrationModel":
        """Fit ``scale``/``shift`` from real ``(market_prob, outcome)`` pairs.

        This is a deterministic one-feature logistic regression on the market
        log-odds, regularized toward the identity (``scale -> 1``, ``shift ->
        0``). The identity prior keeps the forecast honest: without strong
        evidence of miscalibration it stays at the market price.

        The regularization is scaled by ``1 / N`` so that it behaves like a
        single fixed L2 penalty over the whole batch. With few samples the
        penalty dominates and the fit stays near the identity; as real evidence
        accumulates the data term outweighs it and the estimate converges toward
        the market's true miscalibration. Fewer than ``min_samples`` pairs are
        treated as untrustworthy and return the no-edge identity.
        """

        if identity_regularization < 0:
            raise ValueError("identity_regularization must be non-negative")
        if min_samples < 0:
            raise ValueError("min_samples must be non-negative")

        cleaned = [
            (float(prob), float(outcome)) for prob, outcome in pairs if outcome in (0, 1, 0.0, 1.0)
        ]
        if len(cleaned) < max(min_samples, 1):
            return cls.identity()

        log_odds = [logit(prob) for prob, _ in cleaned]
        outcomes = [outcome for _, outcome in cleaned]

        scale = 1.0
        shift = 0.0
        sample_size = len(cleaned)
        # Evidence-scaled penalty: fixed relative to the whole batch, so its pull
        # shrinks as the data term grows with N.
        regularization = identity_regularization / sample_size
        for _ in range(epochs):
            for x, y in zip(log_odds, outcomes):
                prediction = sigmoid(shift + scale * x)
                error = prediction - y
                shift -= learning_rate * (error + regularization * shift)
                scale -= learning_rate * (error * x + regularization * (scale - 1.0))
                # Project back onto the monotonic, bounded region every step so
                # a single extreme quote can never invert the recalibration.
                scale = _clamp(scale, MIN_SCALE, MAX_SCALE)
                shift = _clamp(shift, MIN_SHIFT, MAX_SHIFT)

        return cls(
            scale=scale,
            shift=shift,
            name=name,
            fit_sample_size=sample_size,
        )

    def predict(
        self,
        question: str,
        features: Mapping[str, Any],
        labels: Mapping[str, Any],
    ) -> "RecalibrationPrediction":
        """Return a recalibrated prediction for one market snapshot."""

        del question, labels
        market_prob = _clamp(float(features.get("market_prob", 0.5)), 0.0, 1.0)
        fair_prob = self.fair_probability(market_prob)
        edge = fair_prob - market_prob
        # Confidence rises with the strength of the recalibrated edge, but the
        # identity model stays at the neutral floor so it never over-asserts.
        confidence = _clamp(0.5 + min(abs(edge) * 4.0, 0.45), 0.5, 0.95)
        return RecalibrationPrediction(
            probability=fair_prob,
            confidence=confidence,
            edge=edge,
            model=self,
        )

    def to_metadata(self) -> dict:
        """Return an auditable description of the forecast source."""

        return {
            "model": self.name,
            "forecast_source": "market_recalibration",
            "calibration_logit_scale": self.scale,
            "calibration_logit_shift": self.shift,
            "is_identity": self.is_identity,
            "fit_sample_size": self.fit_sample_size,
        }


@dataclass(frozen=True)
class RecalibrationPrediction:
    """Prediction bundle returned by :class:`MarketRecalibrationModel`."""

    probability: float
    confidence: float
    edge: float
    model: MarketRecalibrationModel


class RecalibratedMarketStrategy:
    """Specialist strategy that trades a recalibrated market forecast."""

    name = "market_recalibrated"

    def __init__(
        self,
        model: MarketRecalibrationModel | None = None,
        policy: SpecialistOrderPolicy | None = None,
    ) -> None:
        self.model = model or MarketRecalibrationModel.identity()
        self.policy = policy or SpecialistOrderPolicy()

    def generate_signal(
        self,
        snapshot: MarketSnapshot,
        context: StrategyContext,
    ) -> MarketSignal | None:
        del context
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
        family = snapshot_label(snapshot, "market_family", snapshot.market.category.value)
        regime = snapshot_label(snapshot, "regime", "steady")
        rationale = (
            "Market-implied price recalibrated on real resolved outcomes "
            f"(scale={self.model.scale:.3f}, shift={self.model.shift:.3f})."
        )
        return MarketSignal(
            fair_prob=prediction.probability,
            confidence=prediction.confidence,
            rationale=rationale,
            tags=("domain", "recalibrated", "model", family, regime),
            metadata={
                **self.model.to_metadata(),
                "domain": snapshot_label(snapshot, "domain", "generic"),
                "market_family": family,
                "regime": regime,
                "edge": prediction.edge,
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
