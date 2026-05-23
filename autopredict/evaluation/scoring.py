"""Proper scoring rules and calibration helpers for prediction markets."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Sequence

EPSILON = 1e-12


@dataclass(frozen=True)
class BinaryForecast:
    """One binary probability forecast paired with a realized outcome."""

    market_id: str
    probability: float
    outcome: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.market_id:
            raise ValueError("market_id cannot be empty")
        if not (0.0 <= self.probability <= 1.0):
            raise ValueError(
                f"probability must be in [0, 1], got {self.probability}"
            )
        if self.outcome not in (0, 1):
            raise ValueError(f"outcome must be 0 or 1, got {self.outcome}")


@dataclass(frozen=True)
class CalibrationBucket:
    """Calibration statistics for one probability bucket."""

    lower: float
    upper: float
    count: int
    avg_probability: float
    realized_rate: float

    @property
    def absolute_gap(self) -> float:
        """Absolute calibration gap for this bucket."""

        return abs(self.avg_probability - self.realized_rate)

    def to_dict(self) -> dict[str, float]:
        """Serialize the bucket to a plain dictionary."""

        return {
            "lower": self.lower,
            "upper": self.upper,
            "count": float(self.count),
            "avg_probability": self.avg_probability,
            "realized_rate": self.realized_rate,
            "absolute_gap": self.absolute_gap,
        }


@dataclass(frozen=True)
class CalibrationSummary:
    """Calibration summary over all forecasts."""

    buckets: tuple[CalibrationBucket, ...]
    mean_absolute_gap: float
    max_absolute_gap: float
    base_rate: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize the summary to a dictionary."""

        return {
            "base_rate": self.base_rate,
            "mean_absolute_gap": self.mean_absolute_gap,
            "max_absolute_gap": self.max_absolute_gap,
            "buckets": [bucket.to_dict() for bucket in self.buckets],
        }


@dataclass(frozen=True)
class ScoringReport:
    """Bundle of proper scoring rules plus calibration diagnostics."""

    count: int
    brier_score: float
    log_score: float
    log_loss: float
    spherical_score: float
    calibration: CalibrationSummary

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a dictionary."""

        return {
            "count": self.count,
            "brier_score": self.brier_score,
            "log_score": self.log_score,
            "log_loss": self.log_loss,
            "spherical_score": self.spherical_score,
            "calibration": self.calibration.to_dict(),
        }


class ProperScoringRules:
    """Utility methods for binary proper scoring rules."""

    @staticmethod
    def clip_probability(probability: float, epsilon: float = EPSILON) -> float:
        """Clip probabilities away from 0 and 1 for stable log scoring."""

        return min(max(probability, epsilon), 1.0 - epsilon)

    @staticmethod
    def brier_score(forecasts: Sequence[BinaryForecast]) -> float:
        """Return mean squared error of binary probability forecasts."""

        if not forecasts:
            return 0.0
        return statistics.fmean(
            (forecast.probability - forecast.outcome) ** 2 for forecast in forecasts
        )

    @staticmethod
    def log_score(forecasts: Sequence[BinaryForecast]) -> float:
        """Return mean logarithmic score.

        This is the mean log-probability assigned to realized outcomes, so
        larger values are better and the maximum is 0.0.
        """

        if not forecasts:
            return 0.0

        def _score(forecast: BinaryForecast) -> float:
            realized_prob = (
                forecast.probability if forecast.outcome == 1 else 1.0 - forecast.probability
            )
            realized_prob = max(realized_prob, EPSILON)
            return math.log(realized_prob)

        return statistics.fmean(_score(forecast) for forecast in forecasts)

    @staticmethod
    def log_loss(forecasts: Sequence[BinaryForecast]) -> float:
        """Return mean negative log score, where lower is better."""

        return -ProperScoringRules.log_score(forecasts)

    @staticmethod
    def spherical_score(forecasts: Sequence[BinaryForecast]) -> float:
        """Return mean spherical score for binary forecasts."""

        if not forecasts:
            return 0.0

        def _score(forecast: BinaryForecast) -> float:
            probability = ProperScoringRules.clip_probability(forecast.probability)
            realized_prob = probability if forecast.outcome == 1 else 1.0 - probability
            normalizer = math.sqrt(probability**2 + (1.0 - probability) ** 2)
            return realized_prob / normalizer

        return statistics.fmean(_score(forecast) for forecast in forecasts)

    @staticmethod
    def calibration_summary(
        forecasts: Sequence[BinaryForecast],
        num_buckets: int = 10,
    ) -> CalibrationSummary:
        """Return bucketed calibration summary for binary forecasts."""

        if num_buckets <= 0:
            raise ValueError("num_buckets must be positive")
        if not forecasts:
            return CalibrationSummary(
                buckets=(),
                mean_absolute_gap=0.0,
                max_absolute_gap=0.0,
                base_rate=0.0,
            )

        bucket_size = 1.0 / num_buckets
        bucket_map: dict[int, list[BinaryForecast]] = {index: [] for index in range(num_buckets)}
        for forecast in forecasts:
            index = min(int(forecast.probability / bucket_size), num_buckets - 1)
            bucket_map[index].append(forecast)

        buckets: list[CalibrationBucket] = []
        for index in range(num_buckets):
            items = bucket_map[index]
            if not items:
                continue
            lower = index * bucket_size
            upper = (index + 1) * bucket_size
            buckets.append(
                CalibrationBucket(
                    lower=lower,
                    upper=upper,
                    count=len(items),
                    avg_probability=statistics.fmean(item.probability for item in items),
                    realized_rate=statistics.fmean(float(item.outcome) for item in items),
                )
            )

        gaps = [bucket.absolute_gap for bucket in buckets]
        return CalibrationSummary(
            buckets=tuple(buckets),
            mean_absolute_gap=statistics.fmean(gaps) if gaps else 0.0,
            max_absolute_gap=max(gaps) if gaps else 0.0,
            base_rate=statistics.fmean(float(item.outcome) for item in forecasts),
        )

    @staticmethod
    def evaluate_binary_forecasts(
        forecasts: Sequence[BinaryForecast],
        num_buckets: int = 10,
    ) -> ScoringReport:
        """Return the full scoring report for a set of binary forecasts."""

        calibration = ProperScoringRules.calibration_summary(
            forecasts,
            num_buckets=num_buckets,
        )
        return ScoringReport(
            count=len(forecasts),
            brier_score=ProperScoringRules.brier_score(forecasts),
            log_score=ProperScoringRules.log_score(forecasts),
            log_loss=ProperScoringRules.log_loss(forecasts),
            spherical_score=ProperScoringRules.spherical_score(forecasts),
            calibration=calibration,
        )
