"""Selection policy for self-improving prediction-market agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from autopredict.evaluation import BacktestResult
from autopredict.self_improvement.mutation import StrategyGenome


@dataclass(frozen=True)
class CandidateEvaluation:
    """Backtest result for one strategy genome."""

    genome: StrategyGenome
    result: BacktestResult

    def primary_report_card(self) -> dict[str, Any] | None:
        """Return the first non-empty model report card found in the result."""

        for forecast in self.result.forecasts:
            report_card = forecast.metadata.get("report_card")
            if isinstance(report_card, dict) and report_card:
                return dict(report_card)
        for trade in self.result.trades:
            report_card = trade.metadata.get("report_card")
            if isinstance(report_card, dict) and report_card:
                return dict(report_card)
        return None

    def dataset_coverage_score(self) -> float:
        """Return the dataset coverage score for this candidate, if any."""

        report_card = self.primary_report_card()
        if report_card is None:
            return 0.0
        value = report_card.get("coverage_score", 0.0)
        return float(value) if isinstance(value, (int, float)) else 0.0

    def held_out_calibration_stability(self) -> float | None:
        """Return held-out calibration stability if the result carries one."""

        report_card = self.primary_report_card()
        if report_card is None:
            return None
        value = report_card.get("held_out_calibration_stability")
        return float(value) if isinstance(value, (int, float)) else None

    def rank_key(self) -> tuple[float, float, float, float, float, float]:
        """Return the ranking key used by the selection policy."""

        stability = self.held_out_calibration_stability()
        return (
            self.result.scoring.log_score,
            -self.result.scoring.brier_score,
            self.dataset_coverage_score(),
            -stability if stability is not None else float("-inf"),
            self.result.metrics["total_pnl"],
            -self.result.metrics["avg_slippage_bps"],
        )


@dataclass(frozen=True)
class SelectionConfig:
    """Guardrails used when promoting mutated variants."""

    min_filled_trades: int = 1
    max_brier_regression: float = 0.02
    max_calibration_gap_regression: float = 0.02
    max_held_out_calibration_stability_regression: float = 0.05

    def __post_init__(self) -> None:
        if self.min_filled_trades < 0:
            raise ValueError("min_filled_trades must be non-negative")
        if self.max_brier_regression < 0:
            raise ValueError("max_brier_regression must be non-negative")
        if self.max_calibration_gap_regression < 0:
            raise ValueError("max_calibration_gap_regression must be non-negative")
        if self.max_held_out_calibration_stability_regression < 0:
            raise ValueError(
                "max_held_out_calibration_stability_regression must be non-negative"
            )


@dataclass(frozen=True)
class SelectionOutcome:
    """Result of promoting one candidate from a population."""

    baseline: CandidateEvaluation
    winner: CandidateEvaluation
    accepted: tuple[CandidateEvaluation, ...]
    rejected: tuple[CandidateEvaluation, ...]
    rejection_reasons: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the outcome for reporting."""

        return {
            "baseline": self.baseline.genome.to_dict(),
            "winner": self.winner.genome.to_dict(),
            "accepted": [item.genome.to_dict() for item in self.accepted],
            "rejected": [item.genome.to_dict() for item in self.rejected],
            "rejection_reasons": {
                key: list(value) for key, value in self.rejection_reasons.items()
            },
        }


class StrategySelector:
    """Promote the best candidate that clears score and calibration guardrails."""

    def __init__(self, config: SelectionConfig | None = None) -> None:
        self.config = config or SelectionConfig()

    def select(self, candidates: Sequence[CandidateEvaluation]) -> SelectionOutcome:
        """Select a winner from baseline plus mutated candidates."""

        if not candidates:
            raise ValueError("at least one candidate is required")

        baseline = candidates[0]
        accepted: list[CandidateEvaluation] = []
        rejected: list[CandidateEvaluation] = []
        rejection_reasons: dict[str, tuple[str, ...]] = {}

        for candidate in candidates:
            reasons = self._guardrail_failures(candidate, baseline)
            if reasons:
                rejected.append(candidate)
                rejection_reasons[candidate.genome.name] = tuple(reasons)
            else:
                accepted.append(candidate)

        if not accepted:
            accepted = [baseline]

        winner = max(accepted, key=lambda candidate: candidate.rank_key())
        return SelectionOutcome(
            baseline=baseline,
            winner=winner,
            accepted=tuple(accepted),
            rejected=tuple(rejected),
            rejection_reasons=rejection_reasons,
        )

    def _guardrail_failures(
        self,
        candidate: CandidateEvaluation,
        baseline: CandidateEvaluation,
    ) -> list[str]:
        reasons: list[str] = []
        if candidate.result.metrics["num_filled_trades"] < self.config.min_filled_trades:
            reasons.append("insufficient_filled_trades")
        if (
            candidate.result.scoring.brier_score
            > baseline.result.scoring.brier_score + self.config.max_brier_regression
        ):
            reasons.append("brier_regression")
        if (
            candidate.result.scoring.calibration.mean_absolute_gap
            > baseline.result.scoring.calibration.mean_absolute_gap
            + self.config.max_calibration_gap_regression
        ):
            reasons.append("calibration_regression")
        baseline_stability = baseline.held_out_calibration_stability()
        candidate_stability = candidate.held_out_calibration_stability()
        if (
            baseline_stability is not None
            and candidate_stability is not None
            and candidate_stability
            > baseline_stability
            + self.config.max_held_out_calibration_stability_regression
        ):
            reasons.append("held_out_calibration_stability_regression")
        return reasons
