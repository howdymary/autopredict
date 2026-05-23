"""Agent-owned forecast ratchet built on the package-native scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the ratchet summary for CLI and experiment logs."""

        return {
            "dataset_path": self.dataset_path,
            "initial_genome": self.initial_genome,
            "final_genome": self.final_genome,
            "promotions": self.promotions,
            "folds": list(self.folds),
            "agent_owns_forecast_generation": self.agent_owns_forecast_generation,
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


def run_forecast_owned_ratchet(
    dataset_path: str | Path,
    *,
    config: ImprovementLoopConfig | None = None,
    base_genome: StrategyGenome | None = None,
) -> ForecastRatchetSummary:
    """Run the package-native walk-forward ratchet on agent-generated forecasts."""

    snapshots = load_resolved_snapshots(dataset_path)
    loop = SelfImprovementLoop(config or ImprovementLoopConfig())
    report = loop.run_walk_forward(base_genome or default_forecast_owned_genome(), snapshots)

    fold_summaries: list[dict[str, Any]] = []
    for fold in report.folds:
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

    return ForecastRatchetSummary(
        dataset_path=str(Path(dataset_path)),
        initial_genome=report.initial_genome.to_dict(),
        final_genome=report.final_genome.to_dict(),
        promotions=report.promotions,
        folds=tuple(fold_summaries),
    )


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
