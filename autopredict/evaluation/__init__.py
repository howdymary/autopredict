"""Evaluation primitives for scaffold-native prediction-market workflows."""

from autopredict.evaluation.backtest import (
    BacktestResult,
    BacktestTrade,
    ExecutionAssumptions,
    PredictionMarketBacktester,
    ResolvedMarketSnapshot,
)
from autopredict.evaluation.datasets import (
    load_legacy_resolved_snapshots,
    load_resolved_snapshots,
    snapshot_questions,
)
from autopredict.evaluation.contracts import (
    DATASET_SCHEMA_VERSION,
    DatasetManifestV1,
    DatasetValidationError,
    MarketObservationV1,
    ResolvedDatasetV1,
    ResolvedEvaluationRowV1,
    ResolutionV1,
    load_dataset_v1,
)
from autopredict.evaluation.reporting import (
    EVALUATION_REPORT_VERSION,
    evaluate_market_baseline,
    evaluate_provider,
    report_json,
)
from autopredict.evaluation.domain_slices import (
    DomainSliceSummary,
    summarize_backtest_slices,
    summarize_domain_slices,
)
from autopredict.evaluation.scoring import (
    BinaryForecast,
    CalibrationBucket,
    CalibrationSummary,
    ProperScoringRules,
    ScoringReport,
)

__all__ = [
    "BacktestResult",
    "BacktestTrade",
    "BinaryForecast",
    "CalibrationBucket",
    "CalibrationSummary",
    "DomainSliceSummary",
    "ExecutionAssumptions",
    "DATASET_SCHEMA_VERSION",
    "DatasetManifestV1",
    "DatasetValidationError",
    "EVALUATION_REPORT_VERSION",
    "MarketObservationV1",
    "ResolvedDatasetV1",
    "ResolvedEvaluationRowV1",
    "ResolutionV1",
    "evaluate_market_baseline",
    "evaluate_provider",
    "load_dataset_v1",
    "load_legacy_resolved_snapshots",
    "load_resolved_snapshots",
    "PredictionMarketBacktester",
    "ProperScoringRules",
    "ResolvedMarketSnapshot",
    "ScoringReport",
    "snapshot_questions",
    "report_json",
    "summarize_backtest_slices",
    "summarize_domain_slices",
]
