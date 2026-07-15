"""Statistical evidence contract for offline frontier promotion.

Promotion is based on paired candidate/market Brier-loss differences. Repeated
snapshots from the same event are collapsed into one cluster, so they cannot
inflate the independent sample count. The one-sided confidence threshold is
Bonferroni-corrected for every candidate hypothesis tried by the run.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

PROMOTION_METHOD_VERSION = "paired-event-clustered-brier-student-t-v2"


@dataclass(frozen=True)
class PromotionPolicy:
    """Fail-closed thresholds for one promotion attempt."""

    min_independent_events: int = 30
    familywise_alpha: float = 0.05
    min_brier_improvement: float = 0.0
    correction_method: str = "bonferroni"

    def __post_init__(self) -> None:
        if self.min_independent_events < 2:
            raise ValueError("min_independent_events must be at least 2")
        if not (0.0 < self.familywise_alpha < 0.5):
            raise ValueError("familywise_alpha must be in (0, 0.5)")
        if not math.isfinite(self.min_brier_improvement):
            raise ValueError("min_brier_improvement must be finite")
        if self.correction_method != "bonferroni":
            raise ValueError("only bonferroni multiple-testing correction is supported")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the policy."""

        return {
            "min_independent_events": self.min_independent_events,
            "familywise_alpha": self.familywise_alpha,
            "min_brier_improvement": self.min_brier_improvement,
            "correction_method": self.correction_method,
        }


@dataclass(frozen=True)
class PairedForecastRow:
    """One out-of-fold candidate forecast paired with the contemporaneous market."""

    event_id: str
    market_id: str
    fold_index: int
    snapshot_id: str | None
    provider_version: str
    artifact_id: str
    candidate_probability: float
    market_probability: float
    outcome: int

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be non-empty")
        if not isinstance(self.market_id, str) or not self.market_id.strip():
            raise ValueError("market_id must be non-empty")
        if type(self.fold_index) is not int or self.fold_index < 0:
            raise ValueError("fold_index must be non-negative")
        if self.snapshot_id is not None and (
            not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip()
        ):
            raise ValueError("snapshot_id must be non-empty when supplied")
        if not isinstance(self.provider_version, str) or not self.provider_version.strip():
            raise ValueError("provider_version must be non-empty")
        if not isinstance(self.artifact_id, str) or not self.artifact_id.strip():
            raise ValueError("artifact_id must be non-empty")
        for name, value in (
            ("candidate_probability", self.candidate_probability),
            ("market_probability", self.market_probability),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a number")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if type(self.outcome) is not int or self.outcome not in (0, 1):
            raise ValueError("outcome must be 0 or 1")

    @property
    def identity(self) -> tuple[int, str, str, str | None]:
        """Return the immutable out-of-fold row identity."""

        return (self.fold_index, self.event_id, self.market_id, self.snapshot_id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the paired row."""

        payload = {
            "event_id": self.event_id,
            "market_id": self.market_id,
            "fold_index": self.fold_index,
            "provider_version": self.provider_version,
            "artifact_id": self.artifact_id,
            "candidate_probability": self.candidate_probability,
            "market_probability": self.market_probability,
            "outcome": self.outcome,
        }
        if self.snapshot_id is not None:
            payload["snapshot_id"] = self.snapshot_id
        return payload


@dataclass(frozen=True)
class PromotionDecision:
    """Auditable statistical decision for a promotion attempt."""

    accepted: bool
    rejection_reasons: tuple[str, ...]
    method_version: str
    hypothesis_count: int
    corrected_alpha: float
    row_count: int
    independent_event_count: int
    candidate_brier_score: float | None
    market_brier_score: float | None
    mean_brier_improvement: float | None
    standard_error: float | None
    corrected_lower_bound: float | None
    event_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete evidence summary."""

        return {
            "accepted": self.accepted,
            "rejection_reasons": list(self.rejection_reasons),
            "method_version": self.method_version,
            "hypothesis_count": self.hypothesis_count,
            "corrected_alpha": self.corrected_alpha,
            "row_count": self.row_count,
            "independent_event_count": self.independent_event_count,
            "candidate_brier_score": self.candidate_brier_score,
            "market_brier_score": self.market_brier_score,
            "mean_brier_improvement": self.mean_brier_improvement,
            "standard_error": self.standard_error,
            "corrected_lower_bound": self.corrected_lower_bound,
            "event_ids": list(self.event_ids),
        }


def assess_paired_forecasts(
    rows: Sequence[PairedForecastRow],
    *,
    expected_row_identities: Sequence[tuple[int, str, str, str | None]],
    hypothesis_count: int,
    policy: PromotionPolicy | None = None,
    input_rejection_reasons: Sequence[str] = (),
) -> PromotionDecision:
    """Assess all out-of-fold rows using event-clustered paired differences."""

    active_policy = policy or PromotionPolicy()
    if hypothesis_count <= 0:
        raise ValueError("hypothesis_count must be positive")
    corrected_alpha = active_policy.familywise_alpha / hypothesis_count
    reasons = list(dict.fromkeys(str(reason) for reason in input_rejection_reasons))
    expected_counter = Counter(expected_row_identities)
    observed_counter = Counter(row.identity for row in rows)

    if not rows:
        reasons.append("empty_out_of_fold_evidence")
    if not expected_counter:
        reasons.append("empty_expected_row_identity_set")
    duplicated = sorted(identity for identity, count in observed_counter.items() if count > 1)
    if duplicated:
        reasons.append("duplicate_observed_row_identities:" + _render_identities(duplicated))
    duplicated_expected = sorted(
        identity for identity, count in expected_counter.items() if count > 1
    )
    if duplicated_expected:
        reasons.append(
            "duplicate_expected_row_identities:" + _render_identities(duplicated_expected)
        )
    missing = list((expected_counter - observed_counter).elements())
    unexpected = list((observed_counter - expected_counter).elements())
    if missing:
        reasons.append("missing_expected_rows:" + _render_identities(sorted(missing)))
    if unexpected:
        reasons.append("unexpected_rows:" + _render_identities(sorted(unexpected)))

    clustered: dict[str, list[float]] = {}
    candidate_losses: dict[str, list[float]] = {}
    market_losses: dict[str, list[float]] = {}
    market_outcomes: dict[tuple[str, str], int] = {}
    for row in rows:
        outcome_key = (row.event_id, row.market_id)
        previous_outcome = market_outcomes.setdefault(outcome_key, row.outcome)
        if previous_outcome != row.outcome:
            reasons.append(f"conflicting_outcomes:{row.event_id}|{row.market_id}")
            continue
        candidate_loss = (row.candidate_probability - row.outcome) ** 2
        market_loss = (row.market_probability - row.outcome) ** 2
        clustered.setdefault(row.event_id, []).append(market_loss - candidate_loss)
        candidate_losses.setdefault(row.event_id, []).append(candidate_loss)
        market_losses.setdefault(row.event_id, []).append(market_loss)

    event_ids = tuple(sorted(clustered))
    independent_count = len(event_ids)
    if independent_count < active_policy.min_independent_events:
        reasons.append(
            "insufficient_independent_events:"
            f"{independent_count}<{active_policy.min_independent_events}"
        )

    if not event_ids:
        return PromotionDecision(
            accepted=False,
            rejection_reasons=tuple(dict.fromkeys(reasons)),
            method_version=PROMOTION_METHOD_VERSION,
            hypothesis_count=hypothesis_count,
            corrected_alpha=corrected_alpha,
            row_count=len(rows),
            independent_event_count=0,
            candidate_brier_score=None,
            market_brier_score=None,
            mean_brier_improvement=None,
            standard_error=None,
            corrected_lower_bound=None,
            event_ids=(),
        )

    cluster_differences = [statistics.fmean(clustered[event_id]) for event_id in event_ids]
    candidate_brier = statistics.fmean(
        statistics.fmean(candidate_losses[event_id]) for event_id in event_ids
    )
    market_brier = statistics.fmean(
        statistics.fmean(market_losses[event_id]) for event_id in event_ids
    )
    mean_improvement = statistics.fmean(cluster_differences)
    if independent_count < 2:
        standard_error = None
        lower_bound = None
        reasons.append("clustered_uncertainty_requires_two_events")
    else:
        standard_error = statistics.stdev(cluster_differences) / math.sqrt(independent_count)
        critical_value = _student_t_quantile(1.0 - corrected_alpha, independent_count - 1)
        lower_bound = mean_improvement - critical_value * standard_error
        if lower_bound <= active_policy.min_brier_improvement:
            reasons.append("corrected_lower_bound_not_positive")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return PromotionDecision(
        accepted=not unique_reasons,
        rejection_reasons=unique_reasons,
        method_version=PROMOTION_METHOD_VERSION,
        hypothesis_count=hypothesis_count,
        corrected_alpha=corrected_alpha,
        row_count=len(rows),
        independent_event_count=independent_count,
        candidate_brier_score=candidate_brier,
        market_brier_score=market_brier,
        mean_brier_improvement=mean_improvement,
        standard_error=standard_error,
        corrected_lower_bound=lower_bound,
        event_ids=event_ids,
    )


def parse_paired_rows(values: Any) -> tuple[tuple[PairedForecastRow, ...], tuple[str, ...]]:
    """Parse untrusted archive rows while preserving precise fail-closed reasons."""

    if not isinstance(values, list):
        return (), ("promotion_rows_must_be_a_list",)
    rows: list[PairedForecastRow] = []
    reasons: list[str] = []
    required = {
        "event_id",
        "market_id",
        "fold_index",
        "provider_version",
        "artifact_id",
        "candidate_probability",
        "market_probability",
        "outcome",
    }
    for index, value in enumerate(values):
        if not isinstance(value, Mapping):
            reasons.append(f"invalid_promotion_row:{index}:not_an_object")
            continue
        missing = sorted(required - set(value))
        extra = sorted(set(value) - required - {"snapshot_id"})
        if missing:
            reasons.append(f"invalid_promotion_row:{index}:missing:{','.join(missing)}")
            continue
        if extra:
            reasons.append(f"invalid_promotion_row:{index}:extra:{','.join(extra)}")
            continue
        try:
            rows.append(
                PairedForecastRow(
                    event_id=_strict_string(value["event_id"], "event_id"),
                    market_id=_strict_string(value["market_id"], "market_id"),
                    fold_index=_strict_nonnegative_int(value["fold_index"], "fold_index"),
                    snapshot_id=(
                        _strict_string(value["snapshot_id"], "snapshot_id")
                        if "snapshot_id" in value
                        else None
                    ),
                    provider_version=_strict_string(value["provider_version"], "provider_version"),
                    artifact_id=_strict_string(value["artifact_id"], "artifact_id"),
                    candidate_probability=_strict_number(
                        value["candidate_probability"], "candidate_probability"
                    ),
                    market_probability=_strict_number(
                        value["market_probability"], "market_probability"
                    ),
                    outcome=_strict_binary_int(value["outcome"], "outcome"),
                )
            )
        except (TypeError, ValueError) as exc:
            reasons.append(f"invalid_promotion_row:{index}:{exc}")
    return tuple(rows), tuple(reasons)


def parse_expected_row_identities(
    values: Any,
) -> tuple[tuple[tuple[int, str, str, str | None], ...], tuple[str, ...]]:
    """Strictly parse the expected immutable row identities."""

    if not isinstance(values, list):
        return (), ("expected_row_identities_must_be_a_list",)
    identities: list[tuple[int, str, str, str | None]] = []
    reasons: list[str] = []
    required = {"fold_index", "event_id", "market_id"}
    for index, value in enumerate(values):
        if not isinstance(value, Mapping):
            reasons.append(f"invalid_expected_row_identity:{index}:not_an_object")
            continue
        missing = sorted(required - set(value))
        extra = sorted(set(value) - required - {"snapshot_id"})
        if missing:
            reasons.append(f"invalid_expected_row_identity:{index}:missing:{','.join(missing)}")
            continue
        if extra:
            reasons.append(f"invalid_expected_row_identity:{index}:extra:{','.join(extra)}")
            continue
        try:
            identities.append(
                (
                    _strict_nonnegative_int(value["fold_index"], "fold_index"),
                    _strict_string(value["event_id"], "event_id"),
                    _strict_string(value["market_id"], "market_id"),
                    (
                        _strict_string(value["snapshot_id"], "snapshot_id")
                        if "snapshot_id" in value
                        else None
                    ),
                )
            )
        except (TypeError, ValueError) as exc:
            reasons.append(f"invalid_expected_row_identity:{index}:{exc}")
    return tuple(identities), tuple(reasons)


def _strict_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _strict_nonnegative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _strict_binary_int(value: Any, name: str) -> int:
    if type(value) is not int or value not in (0, 1):
        raise ValueError(f"{name} must be 0 or 1")
    return value


def _strict_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(value)


def _render_identities(values: Sequence[tuple[int, str, str, str | None]]) -> str:
    return ",".join(
        f"{fold_index}|{event_id}|{market_id}|{snapshot_id or '-'}"
        for fold_index, event_id, market_id, snapshot_id in values
    )


def _student_t_quantile(probability: float, degrees_of_freedom: int) -> float:
    """Return a deterministic Student-t quantile without a runtime scipy dependency."""

    if not 0.5 < probability < 1.0:
        raise ValueError("Student-t probability must be in (0.5, 1)")
    if degrees_of_freedom <= 0:
        raise ValueError("Student-t degrees_of_freedom must be positive")
    lower = 0.0
    upper = 1.0
    while _student_t_cdf(upper, degrees_of_freedom) < probability:
        upper *= 2.0
        if upper > 1_000_000.0:
            raise ArithmeticError("Student-t quantile failed to converge")
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if _student_t_cdf(midpoint, degrees_of_freedom) < probability:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _student_t_cdf(value: float, degrees_of_freedom: int) -> float:
    if value == 0.0:
        return 0.5
    x = degrees_of_freedom / (degrees_of_freedom + value * value)
    tail = 0.5 * _regularized_incomplete_beta(x, degrees_of_freedom / 2.0, 0.5)
    return 1.0 - tail if value > 0.0 else tail


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    """Evaluate the regularized incomplete beta via a stable continued fraction."""

    if not 0.0 <= x <= 1.0:
        raise ValueError("incomplete-beta x must be in [0, 1]")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    maximum_iterations = 200
    epsilon = 3.0e-14
    floor = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < floor:
        d = floor
    d = 1.0 / d
    result = d
    for iteration in range(1, maximum_iterations + 1):
        even = 2 * iteration
        coefficient = iteration * (b - iteration) * x / ((qam + even) * (a + even))
        d = 1.0 + coefficient * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + coefficient / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        result *= d * c
        coefficient = -(a + iteration) * (qab + iteration) * x / ((a + even) * (qap + even))
        d = 1.0 + coefficient * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + coefficient / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < epsilon:
            return result
    raise ArithmeticError("incomplete-beta continued fraction failed to converge")
