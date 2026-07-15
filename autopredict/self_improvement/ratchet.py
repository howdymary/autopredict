"""Agent-owned forecast ratchet built on the package-native scaffold."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Sequence

from autopredict.domains.recalibration import MarketRecalibrationModel
from autopredict.evaluation.backtest import ResolvedMarketSnapshot
from autopredict.evaluation.datasets import load_resolved_snapshots
from autopredict.self_improvement.loop import ImprovementLoopConfig, SelfImprovementLoop
from autopredict.self_improvement.mutation import MutationConfig, StrategyGenome


@dataclass(frozen=True)
class ForecastRatchetSummary:
    """Serializable summary of one forecast-owned ratchet run."""

    dataset_path: str
    initial_genome: dict[str, Any]
    final_genome: dict[str, Any]
    promotions: int
    folds: tuple[dict[str, Any], ...]
    agent_owns_forecast_generation: bool = True
    promotion_evaluation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the ratchet summary for CLI and experiment logs."""

        return {
            "dataset_path": self.dataset_path,
            "initial_genome": self.initial_genome,
            "final_genome": self.final_genome,
            "promotions": self.promotions,
            "folds": list(self.folds),
            "agent_owns_forecast_generation": self.agent_owns_forecast_generation,
            "promotion_evaluation": self.promotion_evaluation,
        }


def default_forecast_owned_genome() -> StrategyGenome:
    """Return the baseline genome for the forecast-owned ratchet path."""

    return StrategyGenome(
        name="routed_question_model_baseline",
        strategy_kind="routed_question_model",
        kelly_fraction=0.25,
        aggressive_edge_threshold=0.08,
        min_spread_capture=0.0,
        max_position_size=250.0,
        max_total_exposure=2000.0,
        max_daily_loss=500.0,
        max_leverage=1.5,
        min_edge_threshold=0.03,
        min_confidence=0.55,
        max_bankroll_fraction=0.05,
        metadata={"forecast_source": "agent_model"},
    )


def default_recalibrated_genome() -> StrategyGenome:
    """Return the identity (no-edge) baseline for the recalibration ratchet.

    ``scale = 1.0``/``shift = 0.0`` reproduces the market price exactly, so the
    baseline fabricates no edge. Fitting on real resolved data is what lets the
    forecast depart from the market.
    """

    return StrategyGenome(
        name="market_recalibrated_baseline",
        strategy_kind="market_recalibrated",
        kelly_fraction=0.25,
        aggressive_edge_threshold=0.08,
        min_spread_capture=0.0,
        max_position_size=250.0,
        max_total_exposure=2000.0,
        max_daily_loss=500.0,
        max_leverage=1.5,
        min_edge_threshold=0.02,
        min_confidence=0.55,
        max_bankroll_fraction=0.05,
        calibration_logit_scale=1.0,
        calibration_logit_shift=0.0,
        metadata={"forecast_source": "market_recalibration"},
    )


def fit_recalibrated_genome(
    snapshots: Sequence[ResolvedMarketSnapshot],
    *,
    base_genome: StrategyGenome | None = None,
    identity_regularization: float = 0.05,
) -> StrategyGenome:
    """Fit recalibration genes from resolved snapshots without look-ahead.

    Only the ``(market_prob, outcome)`` pairs of the supplied snapshots feed the
    fit, so callers must pass a strictly-past window when seeding a walk-forward
    run. With no snapshots the identity baseline is returned unchanged.
    """

    genome = base_genome or default_recalibrated_genome()
    pairs = [(snapshot.market.market_prob, snapshot.outcome) for snapshot in snapshots]
    model = MarketRecalibrationModel.fit(pairs, identity_regularization=identity_regularization)
    return replace(
        genome,
        strategy_kind="market_recalibrated",
        calibration_logit_scale=model.scale,
        calibration_logit_shift=model.shift,
        metadata={
            **genome.metadata,
            "forecast_source": "market_recalibration",
            "fit_sample_size": model.fit_sample_size,
        },
    )


def run_market_recalibration_ratchet(
    dataset_path: str | Path,
    *,
    config: ImprovementLoopConfig | None = None,
    warmup_fraction: float = 0.4,
    identity_regularization: float = 0.05,
    min_warmup_samples: int = 20,
) -> ForecastRatchetSummary:
    """Fit a recalibration seed on a past window, then ratchet out-of-sample.

    The earliest ``warmup_fraction`` of the (chronologically ordered) dataset is
    used only to fit the recalibration seed. The remaining, strictly-later
    snapshots drive the walk-forward loop, so every promotion is validated on
    data the seed never saw.

    When the warmup window holds fewer than ``min_warmup_samples`` resolved
    markets the seed is untrustworthy, so the run falls back to the no-edge
    identity genome rather than seeding a boundary recalibration from noise.
    """

    if not (0.0 < warmup_fraction < 1.0):
        raise ValueError("warmup_fraction must be in (0, 1)")

    snapshots = load_resolved_snapshots(dataset_path)
    ordered = sorted(snapshots, key=lambda snapshot: snapshot.observed_at)
    if len(ordered) < 3:
        raise ValueError("recalibration ratchet requires at least 3 resolved snapshots")

    warmup_count = max(1, min(len(ordered) - 2, int(len(ordered) * warmup_fraction)))
    warmup_snapshots = ordered[:warmup_count]
    evaluation_snapshots = ordered[warmup_count:]

    if len(warmup_snapshots) < min_warmup_samples:
        seed_genome = replace(
            default_recalibrated_genome(),
            metadata={
                **default_recalibrated_genome().metadata,
                "forecast_source": "market_recalibration",
                "fit_sample_size": 0,
                "seed_fallback": "insufficient_warmup_samples",
            },
        )
    else:
        seed_genome = fit_recalibrated_genome(
            warmup_snapshots,
            identity_regularization=identity_regularization,
        )
    return run_forecast_owned_ratchet(
        dataset_path,
        config=config,
        base_genome=seed_genome,
        snapshots=evaluation_snapshots,
    )


def run_forecast_owned_ratchet(
    dataset_path: str | Path,
    *,
    config: ImprovementLoopConfig | None = None,
    base_genome: StrategyGenome | None = None,
    snapshots: Sequence[ResolvedMarketSnapshot] | None = None,
) -> ForecastRatchetSummary:
    """Run the package-native walk-forward ratchet on agent-generated forecasts."""

    if snapshots is None:
        snapshots = load_resolved_snapshots(dataset_path)
    loop = SelfImprovementLoop(config or ImprovementLoopConfig())
    report = loop.run_walk_forward(base_genome or default_forecast_owned_genome(), snapshots)

    fold_summaries: list[dict[str, Any]] = []
    promotion_rows: list[dict[str, Any]] = []
    expected_row_identities: list[dict[str, Any]] = []
    attempted_artifacts: list[dict[str, Any]] = []
    evaluated_trajectory: list[dict[str, Any]] = []
    hypothesis_count = 0
    for fold in report.folds:
        genome_payload = fold.winner.genome.to_dict()
        artifact_id = _artifact_id(genome_payload)
        provider_version = "provider-config-sha256:" + _canonical_sha256(
            {
                "artifact_id": artifact_id,
                "agent_run": asdict(loop.config.agent_run),
            }
        )
        population_artifacts = [
            _artifact_id(candidate.genome.to_dict()) for candidate in fold.train_report.population
        ]
        attempted_artifacts.append(
            {
                "fold_index": fold.fold_index,
                "baseline_artifact_id": population_artifacts[0],
                "artifact_ids": population_artifacts,
            }
        )
        evaluated_trajectory.append(
            {
                "fold_index": fold.fold_index,
                "provider_version": provider_version,
                "artifact_id": artifact_id,
            }
        )
        winner_report_card = fold.winner.primary_report_card()
        validation_metrics = fold.winner.result.metrics
        fold_summaries.append(
            {
                "fold_index": fold.fold_index,
                "promoted": fold.promoted,
                "train_market_ids": list(fold.train_market_ids),
                "validation_market_ids": list(fold.validation_market_ids),
                "train_split_labels": list(fold.train_split_labels),
                "validation_split_labels": list(fold.validation_split_labels),
                "baseline_genome": fold.baseline_genome.to_dict(),
                "winner_genome": fold.winner.genome.to_dict(),
                "winner_metrics": {
                    "log_score": fold.winner.result.scoring.log_score,
                    "brier_score": fold.winner.result.scoring.brier_score,
                    "total_pnl": validation_metrics["total_pnl"],
                    "avg_slippage_bps": validation_metrics["avg_slippage_bps"],
                    "num_filled_trades": validation_metrics["num_filled_trades"],
                },
                "winner_report_card": winner_report_card,
            }
        )
        hypothesis_count += max(len(fold.train_report.population) - 1, 0)
        for forecast in fold.winner.result.forecasts:
            metadata = forecast.metadata
            if metadata.get("artifact_id") not in (None, artifact_id):
                raise ValueError("forecast artifact metadata conflicts with the canonical winner")
            if metadata.get("provider_version") not in (None, provider_version):
                raise ValueError("forecast provider metadata conflicts with the canonical config")
            if forecast.market_probability is None:
                raise ValueError("forecast is missing typed contemporaneous market_probability")
            row = {
                "event_id": str(metadata.get("event_id", forecast.market_id)),
                "market_id": forecast.market_id,
                "fold_index": fold.fold_index,
                "provider_version": provider_version,
                "artifact_id": artifact_id,
                "candidate_probability": forecast.probability,
                "market_probability": forecast.market_probability,
                "outcome": forecast.outcome,
            }
            if metadata.get("snapshot_id") is not None:
                row["snapshot_id"] = str(metadata["snapshot_id"])
            promotion_rows.append(row)
        for event_id, market_id, snapshot_id in zip(
            fold.validation_event_ids or fold.validation_market_ids,
            fold.validation_market_ids,
            fold.validation_snapshot_ids or tuple(None for _ in fold.validation_market_ids),
        ):
            identity = {
                "event_id": event_id,
                "market_id": market_id,
                "fold_index": fold.fold_index,
            }
            if snapshot_id is not None:
                identity["snapshot_id"] = snapshot_id
            expected_row_identities.append(identity)

    return ForecastRatchetSummary(
        dataset_path=str(Path(dataset_path)),
        initial_genome=report.initial_genome.to_dict(),
        final_genome=report.final_genome.to_dict(),
        promotions=report.promotions,
        folds=tuple(fold_summaries),
        promotion_evaluation={
            "rows": promotion_rows,
            "expected_row_identities": expected_row_identities,
            "attempted_artifacts": attempted_artifacts,
            "evaluated_trajectory": evaluated_trajectory,
            "hypothesis_count": hypothesis_count,
        },
    )


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _artifact_id(genome: dict[str, Any]) -> str:
    return "genome-sha256:" + _canonical_sha256(genome)


def improvement_config_with_population(
    *,
    population_size: int = 5,
    train_size: int = 3,
    validation_size: int = 1,
) -> ImprovementLoopConfig:
    """Build a small deterministic improvement config for CLI entrypoints."""

    config = ImprovementLoopConfig()
    return ImprovementLoopConfig(
        mutation=MutationConfig(
            seed=config.mutation.seed,
            population_size=population_size,
            relative_step=config.mutation.relative_step,
        ),
        selection=config.selection,
        agent_run=config.agent_run,
        walk_forward=config.walk_forward.__class__(
            train_size=train_size,
            validation_size=validation_size,
            step_size=config.walk_forward.step_size,
            split_mode=config.walk_forward.split_mode,
            family_key=config.walk_forward.family_key,
            regime_key=config.walk_forward.regime_key,
            regime_features=config.walk_forward.regime_features,
        ),
        starting_cash=config.starting_cash,
    )
