"""Self-improvement loop prototype for prediction-market strategy evolution."""

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
    improvement_config_with_population,
    run_forecast_owned_ratchet,
)
from autopredict.self_improvement.selection import (
    CandidateEvaluation,
    SelectionConfig,
    SelectionOutcome,
    StrategySelector,
)

__all__ = [
    "CandidateEvaluation",
    "default_forecast_owned_genome",
    "ForecastRatchetSummary",
    "ImprovementCycleReport",
    "ImprovementLoopConfig",
    "improvement_config_with_population",
    "MutationConfig",
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
]
