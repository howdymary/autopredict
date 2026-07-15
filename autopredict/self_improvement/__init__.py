"""Self-improvement loop prototype for prediction-market strategy evolution."""

from autopredict.self_improvement.archive import (
    build_run_archive,
    dataset_sha256,
    load_run_archive,
    rebuild_promotion_attempt,
    write_run_archive,
)
from autopredict.self_improvement.frontier import (
    FrontierPromotion,
    FrontierStore,
    frontier_key,
    promote_archive,
)
from autopredict.self_improvement.loop import (
    ImprovementCycleReport,
    ImprovementLoopConfig,
    SelfImprovementLoop,
    WalkForwardConfig,
    WalkForwardFoldReport,
    WalkForwardReport,
    WalkForwardSplit,
)
from autopredict.self_improvement.mutation import (
    MutationConfig,
    StrategyGenome,
    StrategyMutator,
)
from autopredict.self_improvement.ratchet import (
    ForecastRatchetSummary,
    default_forecast_owned_genome,
    default_recalibrated_genome,
    fit_recalibrated_genome,
    improvement_config_with_population,
    run_forecast_owned_ratchet,
    run_market_recalibration_ratchet,
)
from autopredict.self_improvement.promotion import (
    PROMOTION_METHOD_VERSION,
    PairedForecastRow,
    PromotionDecision,
    PromotionPolicy,
    assess_paired_forecasts,
    parse_paired_rows,
)
from autopredict.self_improvement.selection import (
    CandidateEvaluation,
    SelectionConfig,
    SelectionOutcome,
    StrategySelector,
)

__all__ = [
    "build_run_archive",
    "CandidateEvaluation",
    "dataset_sha256",
    "default_forecast_owned_genome",
    "default_recalibrated_genome",
    "fit_recalibrated_genome",
    "run_market_recalibration_ratchet",
    "ForecastRatchetSummary",
    "FrontierPromotion",
    "FrontierStore",
    "frontier_key",
    "ImprovementCycleReport",
    "ImprovementLoopConfig",
    "improvement_config_with_population",
    "load_run_archive",
    "rebuild_promotion_attempt",
    "MutationConfig",
    "PROMOTION_METHOD_VERSION",
    "PairedForecastRow",
    "PromotionDecision",
    "PromotionPolicy",
    "promote_archive",
    "assess_paired_forecasts",
    "parse_paired_rows",
    "run_forecast_owned_ratchet",
    "SelectionConfig",
    "SelectionOutcome",
    "SelfImprovementLoop",
    "StrategyGenome",
    "StrategyMutator",
    "StrategySelector",
    "WalkForwardConfig",
    "WalkForwardFoldReport",
    "WalkForwardReport",
    "WalkForwardSplit",
    "write_run_archive",
]
