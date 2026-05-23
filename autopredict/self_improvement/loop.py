"""Orchestration loops for self-improving strategy populations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil, floor
from typing import Sequence

from autopredict.evaluation import PredictionMarketBacktester, ResolvedMarketSnapshot
from autopredict.prediction_market import AgentRunConfig
from autopredict.self_improvement.mutation import (
    MutationConfig,
    StrategyGenome,
    StrategyMutator,
)
from autopredict.self_improvement.selection import (
    CandidateEvaluation,
    SelectionConfig,
    SelectionOutcome,
    StrategySelector,
)


class WalkForwardSplit(str, Enum):
    """Validation split strategy for held-out promotion checks."""

    CHRONOLOGICAL = "chronological"
    REGIME = "regime"
    MARKET_FAMILY = "market_family"


@dataclass(frozen=True)
class SnapshotFold:
    """Prepared train/validation split for one held-out fold."""

    fold_index: int
    train_snapshots: tuple[ResolvedMarketSnapshot, ...]
    validation_snapshots: tuple[ResolvedMarketSnapshot, ...]
    train_labels: tuple[str, ...] = ()
    validation_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class WalkForwardConfig:
    """Expanding-window walk-forward evaluation settings."""

    train_size: int = 3
    validation_size: int = 1
    step_size: int = 1
    split_mode: WalkForwardSplit | str = WalkForwardSplit.CHRONOLOGICAL
    family_key: str = "category"
    regime_key: str = "auto"
    regime_features: tuple[str, ...] = ("spread_bps", "total_liquidity")

    def __post_init__(self) -> None:
        if self.train_size <= 0:
            raise ValueError("train_size must be positive")
        if self.validation_size <= 0:
            raise ValueError("validation_size must be positive")
        if self.step_size <= 0:
            raise ValueError("step_size must be positive")
        WalkForwardSplit(self.split_mode)
        if not self.family_key:
            raise ValueError("family_key must be non-empty")
        if not self.regime_key:
            raise ValueError("regime_key must be non-empty")
        if not self.regime_features:
            raise ValueError("regime_features must be non-empty")


@dataclass(frozen=True)
class ImprovementLoopConfig:
    """Config for one self-improvement cycle."""

    mutation: MutationConfig = field(default_factory=MutationConfig)
    selection: SelectionConfig = field(default_factory=SelectionConfig)
    agent_run: AgentRunConfig = field(default_factory=AgentRunConfig)
    walk_forward: WalkForwardConfig = field(default_factory=WalkForwardConfig)
    starting_cash: float = 1000.0

    def __post_init__(self) -> None:
        if self.starting_cash <= 0:
            raise ValueError("starting_cash must be positive")


@dataclass(frozen=True)
class ImprovementCycleReport:
    """Full output of one strategy mutation/evaluation/selection cycle."""

    population: tuple[CandidateEvaluation, ...]
    selection: SelectionOutcome

    @property
    def winner(self) -> CandidateEvaluation:
        """Return the selected winner for the cycle."""

        return self.selection.winner


@dataclass(frozen=True)
class WalkForwardFoldReport:
    """Train/validation report for one walk-forward fold."""

    fold_index: int
    baseline_genome: StrategyGenome
    train_market_ids: tuple[str, ...]
    validation_market_ids: tuple[str, ...]
    train_report: ImprovementCycleReport
    validation_baseline: CandidateEvaluation
    validation_candidate: CandidateEvaluation | None
    validation_selection: SelectionOutcome
    promoted: bool
    train_split_labels: tuple[str, ...] = ()
    validation_split_labels: tuple[str, ...] = ()

    @property
    def candidate_genome(self) -> StrategyGenome:
        """Return the candidate selected on the training fold."""

        return self.train_report.winner.genome

    @property
    def winner(self) -> CandidateEvaluation:
        """Return the candidate that survived held-out validation."""

        return self.validation_selection.winner


@dataclass(frozen=True)
class WalkForwardReport:
    """Outcome of promoting genomes over expanding train/validation windows."""

    initial_genome: StrategyGenome
    final_genome: StrategyGenome
    folds: tuple[WalkForwardFoldReport, ...]

    @property
    def promotions(self) -> int:
        """Return how many held-out promotions were accepted."""

        return sum(1 for fold in self.folds if fold.promoted)


class SelfImprovementLoop:
    """Evaluate mutated strategy variants and select a winner."""

    def __init__(self, config: ImprovementLoopConfig | None = None) -> None:
        self.config = config or ImprovementLoopConfig()
        self.mutator = StrategyMutator(self.config.mutation)
        self.selector = StrategySelector(self.config.selection)
        self.backtester = PredictionMarketBacktester()

    def run(
        self,
        base_genome: StrategyGenome,
        snapshots: Sequence[ResolvedMarketSnapshot],
    ) -> ImprovementCycleReport:
        """Run one full improvement cycle over a population of variants."""

        population = self.mutator.generate_population(base_genome)
        evaluations: list[CandidateEvaluation] = []

        for genome in population:
            agent = genome.build_agent(self.config.agent_run)
            result = self.backtester.run(
                agent,
                snapshots,
                starting_cash=self.config.starting_cash,
            )
            evaluations.append(CandidateEvaluation(genome=genome, result=result))

        selection = self.selector.select(evaluations)
        return ImprovementCycleReport(
            population=tuple(evaluations),
            selection=selection,
        )

    def run_walk_forward(
        self,
        base_genome: StrategyGenome,
        snapshots: Sequence[ResolvedMarketSnapshot],
    ) -> WalkForwardReport:
        """Promote genomes only after they clear held-out generalization checks."""

        active_genome = base_genome
        folds: list[WalkForwardFoldReport] = []

        for split in self._build_validation_folds(snapshots):
            train_report = self.run(active_genome, split.train_snapshots)

            validation_baseline = CandidateEvaluation(
                genome=active_genome,
                result=self.backtester.run(
                    active_genome.build_agent(self.config.agent_run),
                    split.validation_snapshots,
                    starting_cash=self.config.starting_cash,
                ),
            )

            candidate_genome = train_report.winner.genome
            if candidate_genome == active_genome:
                validation_candidate = None
                validation_selection = self.selector.select([validation_baseline])
                promoted = False
            else:
                validation_candidate = CandidateEvaluation(
                    genome=candidate_genome,
                    result=self.backtester.run(
                        candidate_genome.build_agent(self.config.agent_run),
                        split.validation_snapshots,
                        starting_cash=self.config.starting_cash,
                    ),
                )
                validation_selection = self.selector.select(
                    [validation_baseline, validation_candidate]
                )
                promoted = validation_selection.winner.genome == candidate_genome
                if promoted:
                    active_genome = candidate_genome

            folds.append(
                WalkForwardFoldReport(
                    fold_index=split.fold_index,
                    baseline_genome=validation_baseline.genome,
                    train_market_ids=tuple(
                        snapshot.market.market_id for snapshot in split.train_snapshots
                    ),
                    validation_market_ids=tuple(
                        snapshot.market.market_id for snapshot in split.validation_snapshots
                    ),
                    train_split_labels=split.train_labels,
                    validation_split_labels=split.validation_labels,
                    train_report=train_report,
                    validation_baseline=validation_baseline,
                    validation_candidate=validation_candidate,
                    validation_selection=validation_selection,
                    promoted=promoted,
                )
            )

        return WalkForwardReport(
            initial_genome=base_genome,
            final_genome=active_genome,
            folds=tuple(folds),
        )

    def _build_validation_folds(
        self,
        snapshots: Sequence[ResolvedMarketSnapshot],
    ) -> tuple[SnapshotFold, ...]:
        ordered_snapshots = tuple(sorted(snapshots, key=lambda snapshot: snapshot.observed_at))
        split_mode = WalkForwardSplit(self.config.walk_forward.split_mode)

        if split_mode == WalkForwardSplit.CHRONOLOGICAL:
            return self._build_chronological_folds(ordered_snapshots)
        if split_mode == WalkForwardSplit.REGIME:
            return self._build_regime_folds(ordered_snapshots)
        return self._build_market_family_folds(ordered_snapshots)

    def _build_chronological_folds(
        self,
        ordered_snapshots: Sequence[ResolvedMarketSnapshot],
    ) -> tuple[SnapshotFold, ...]:
        walk_forward = self.config.walk_forward
        minimum_snapshots = walk_forward.train_size + walk_forward.validation_size
        if len(ordered_snapshots) < minimum_snapshots:
            raise ValueError(
                "chronological walk-forward requires at least "
                f"{minimum_snapshots} snapshots, got {len(ordered_snapshots)}"
            )

        train_end = walk_forward.train_size
        fold_index = 0
        folds: list[SnapshotFold] = []
        while train_end + walk_forward.validation_size <= len(ordered_snapshots):
            folds.append(
                SnapshotFold(
                    fold_index=fold_index,
                    train_snapshots=tuple(ordered_snapshots[:train_end]),
                    validation_snapshots=tuple(
                        ordered_snapshots[train_end : train_end + walk_forward.validation_size]
                    ),
                )
            )
            fold_index += 1
            train_end += walk_forward.step_size
        return tuple(folds)

    def _build_regime_folds(
        self,
        ordered_snapshots: Sequence[ResolvedMarketSnapshot],
    ) -> tuple[SnapshotFold, ...]:
        walk_forward = self.config.walk_forward
        regime_labels = self._resolve_regime_labels(ordered_snapshots)
        blocks: list[tuple[str, tuple[ResolvedMarketSnapshot, ...]]] = []

        current_label = ""
        current_snapshots: list[ResolvedMarketSnapshot] = []
        for snapshot, label in zip(ordered_snapshots, regime_labels):
            if not current_snapshots:
                current_label = label
                current_snapshots = [snapshot]
                continue
            if label == current_label:
                current_snapshots.append(snapshot)
                continue
            blocks.append((current_label, tuple(current_snapshots)))
            current_label = label
            current_snapshots = [snapshot]

        if current_snapshots:
            blocks.append((current_label, tuple(current_snapshots)))

        minimum_blocks = walk_forward.train_size + walk_forward.validation_size
        if len(blocks) < minimum_blocks:
            raise ValueError(
                "regime walk-forward requires at least "
                f"{minimum_blocks} contiguous regime blocks, got {len(blocks)}"
            )

        folds: list[SnapshotFold] = []
        train_end = walk_forward.train_size
        fold_index = 0
        while train_end + walk_forward.validation_size <= len(blocks):
            train_blocks = blocks[:train_end]
            validation_blocks = blocks[train_end : train_end + walk_forward.validation_size]
            folds.append(
                SnapshotFold(
                    fold_index=fold_index,
                    train_snapshots=self._flatten_block_snapshots(train_blocks),
                    validation_snapshots=self._flatten_block_snapshots(validation_blocks),
                    train_labels=tuple(label for label, _ in train_blocks),
                    validation_labels=tuple(label for label, _ in validation_blocks),
                )
            )
            fold_index += 1
            train_end += walk_forward.step_size
        return tuple(folds)

    def _build_market_family_folds(
        self,
        ordered_snapshots: Sequence[ResolvedMarketSnapshot],
    ) -> tuple[SnapshotFold, ...]:
        walk_forward = self.config.walk_forward
        grouped: dict[str, list[ResolvedMarketSnapshot]] = {}
        ordered_labels: list[str] = []

        for snapshot in ordered_snapshots:
            label = self._resolve_group_label(snapshot, walk_forward.family_key)
            if label not in grouped:
                grouped[label] = []
                ordered_labels.append(label)
            grouped[label].append(snapshot)

        minimum_groups = walk_forward.train_size + walk_forward.validation_size
        if len(ordered_labels) < minimum_groups:
            raise ValueError(
                "market-family validation requires at least "
                f"{minimum_groups} families, got {len(ordered_labels)}"
            )

        folds: list[SnapshotFold] = []
        validation_start = 0
        fold_index = 0
        while validation_start + walk_forward.validation_size <= len(ordered_labels):
            validation_labels = tuple(
                ordered_labels[validation_start : validation_start + walk_forward.validation_size]
            )
            train_labels = tuple(
                label for label in ordered_labels if label not in validation_labels
            )
            if len(train_labels) >= walk_forward.train_size:
                folds.append(
                    SnapshotFold(
                        fold_index=fold_index,
                        train_snapshots=self._collect_group_snapshots(grouped, train_labels),
                        validation_snapshots=self._collect_group_snapshots(
                            grouped, validation_labels
                        ),
                        train_labels=train_labels,
                        validation_labels=validation_labels,
                    )
                )
                fold_index += 1
            validation_start += walk_forward.step_size

        if not folds:
            raise ValueError(
                "market-family validation did not produce any folds with enough train groups"
            )
        return tuple(folds)

    @staticmethod
    def _flatten_block_snapshots(
        blocks: Sequence[tuple[str, tuple[ResolvedMarketSnapshot, ...]]],
    ) -> tuple[ResolvedMarketSnapshot, ...]:
        flattened: list[ResolvedMarketSnapshot] = []
        for _, snapshots in blocks:
            flattened.extend(snapshots)
        return tuple(flattened)

    @staticmethod
    def _collect_group_snapshots(
        grouped: dict[str, list[ResolvedMarketSnapshot]],
        labels: Sequence[str],
    ) -> tuple[ResolvedMarketSnapshot, ...]:
        collected: list[ResolvedMarketSnapshot] = []
        for label in labels:
            collected.extend(grouped[label])
        return tuple(sorted(collected, key=lambda snapshot: snapshot.observed_at))

    def _resolve_regime_labels(
        self,
        ordered_snapshots: Sequence[ResolvedMarketSnapshot],
    ) -> tuple[str, ...]:
        walk_forward = self.config.walk_forward
        if walk_forward.regime_key != "auto":
            return tuple(
                self._resolve_group_label(snapshot, walk_forward.regime_key)
                for snapshot in ordered_snapshots
            )

        thresholds = {
            feature: self._tertile_thresholds(
                [self._resolve_numeric_feature(snapshot, feature) for snapshot in ordered_snapshots]
            )
            for feature in walk_forward.regime_features
        }
        return tuple(
            self._auto_regime_label(snapshot, thresholds)
            for snapshot in ordered_snapshots
        )

    def _auto_regime_label(
        self,
        snapshot: ResolvedMarketSnapshot,
        thresholds: dict[str, tuple[float, float]],
    ) -> str:
        labels = []
        for feature, bounds in thresholds.items():
            value = self._resolve_numeric_feature(snapshot, feature)
            labels.append(f"{feature}:{self._bucket_label(feature, value, bounds)}")
        return "|".join(labels)

    def _resolve_group_label(
        self,
        snapshot: ResolvedMarketSnapshot,
        key: str,
    ) -> str:
        if key == "category":
            if "category" in snapshot.metadata:
                return str(snapshot.metadata["category"])
            if "category" in snapshot.market.metadata:
                return str(snapshot.market.metadata["category"])
            return snapshot.market.category.value
        if key == "market.category":
            return snapshot.market.category.value
        if key in {"venue", "venue.name"}:
            return snapshot.venue.name.value
        if key in {"market_id", "market.market_id"}:
            return snapshot.market.market_id

        if key.startswith("metadata."):
            return self._lookup_nested_value(
                snapshot.merged_metadata(),
                key.removeprefix("metadata."),
                key,
            )
        if key.startswith("market.metadata."):
            return self._lookup_nested_value(
                snapshot.market.metadata,
                key.removeprefix("market.metadata."),
                key,
            )
        if key.startswith("features."):
            return self._lookup_nested_value(
                snapshot.merged_snapshot_features(),
                key.removeprefix("features."),
                key,
            )
        if key.startswith("context."):
            return self._lookup_nested_value(
                snapshot.merged_context_metadata(),
                key.removeprefix("context."),
                key,
            )
        if key.startswith("venue.metadata."):
            return self._lookup_nested_value(
                snapshot.venue.metadata,
                key.removeprefix("venue.metadata."),
                key,
            )

        for mapping in (
            snapshot.merged_metadata(),
            snapshot.market.metadata,
            snapshot.merged_snapshot_features(),
            snapshot.merged_context_metadata(),
            snapshot.venue.metadata,
        ):
            if key in mapping:
                return str(mapping[key])

        raise ValueError(f"unsupported split key: {key}")

    def _resolve_numeric_feature(
        self,
        snapshot: ResolvedMarketSnapshot,
        feature: str,
    ) -> float:
        if feature == "spread_bps":
            return snapshot.market.spread_bps
        if feature == "total_liquidity":
            return snapshot.market.total_liquidity
        if feature == "time_to_expiry_hours":
            return max(
                0.0,
                (snapshot.market.expiry - snapshot.observed_at).total_seconds() / 3600.0,
            )
        if feature == "volume_24h":
            return snapshot.market.volume_24h
        if feature == "num_traders":
            return float(snapshot.market.num_traders)
        if feature == "market_prob":
            return snapshot.market.market_prob
        for mapping in (
            snapshot.merged_snapshot_features(),
            snapshot.merged_metadata(),
            snapshot.market.metadata,
            snapshot.merged_context_metadata(),
        ):
            if feature in mapping:
                value = mapping[feature]
                try:
                    return float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"unsupported regime feature: {feature}") from exc
        raise ValueError(f"unsupported regime feature: {feature}")

    @staticmethod
    def _lookup_nested_value(
        mapping: dict[str, object],
        path: str,
        raw_key: str,
    ) -> str:
        current: object = mapping
        for segment in path.split("."):
            if not isinstance(current, dict) or segment not in current:
                raise ValueError(f"missing split key: {raw_key}")
            current = current[segment]
        return str(current)

    @staticmethod
    def _tertile_thresholds(values: Sequence[float]) -> tuple[float, float]:
        ordered = sorted(values)
        if not ordered:
            raise ValueError("cannot build regime thresholds without values")
        return (
            SelfImprovementLoop._quantile(ordered, 1 / 3),
            SelfImprovementLoop._quantile(ordered, 2 / 3),
        )

    @staticmethod
    def _quantile(values: Sequence[float], fraction: float) -> float:
        if len(values) == 1:
            return values[0]
        index = (len(values) - 1) * fraction
        lower_index = floor(index)
        upper_index = ceil(index)
        if lower_index == upper_index:
            return values[lower_index]
        weight = index - lower_index
        return values[lower_index] * (1.0 - weight) + values[upper_index] * weight

    @staticmethod
    def _bucket_label(feature: str, value: float, bounds: tuple[float, float]) -> str:
        lower_bound, upper_bound = bounds
        if value <= lower_bound:
            index = 0
        elif value >= upper_bound:
            index = 2
        else:
            index = 1

        if feature == "spread_bps":
            labels = ("tight", "normal", "wide")
        elif feature == "total_liquidity":
            labels = ("thin", "normal", "deep")
        elif feature == "time_to_expiry_hours":
            labels = ("near", "mid", "far")
        elif feature == "volume_24h":
            labels = ("cold", "normal", "hot")
        elif feature == "num_traders":
            labels = ("niche", "normal", "crowded")
        else:
            labels = ("low", "mid", "high")
        return labels[index]
