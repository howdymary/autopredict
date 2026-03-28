"""Evaluation primitives for scaffold-native prediction-market workflows."""

from autopredict.evaluation.backtest import (
    BacktestResult,
    BacktestTrade,
    ExecutionAssumptions,
    PredictionMarketBacktester,
    ResolvedMarketSnapshot,
)
from autopredict.evaluation.datasets import (
    load_resolved_snapshots,
    snapshot_questions,
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
    "load_resolved_snapshots",
    "PredictionMarketBacktester",
    "ProperScoringRules",
    "ResolvedMarketSnapshot",
    "ScoringReport",
    "snapshot_questions",
    "summarize_backtest_slices",
    "summarize_domain_slices",
]
