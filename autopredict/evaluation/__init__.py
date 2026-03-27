"""Evaluation primitives for scaffold-native prediction-market workflows."""

from autopredict.evaluation.backtest import (
    BacktestResult,
    BacktestTrade,
    ExecutionAssumptions,
    PredictionMarketBacktester,
    ResolvedMarketSnapshot,
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
    "PredictionMarketBacktester",
    "ProperScoringRules",
    "ResolvedMarketSnapshot",
    "ScoringReport",
    "summarize_backtest_slices",
    "summarize_domain_slices",
]
