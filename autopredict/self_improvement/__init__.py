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
from autopredict.self_improvement.selection import (
    CandidateEvaluation,
    SelectionConfig,
    SelectionOutcome,
    StrategySelector,
)

__all__ = [
    "CandidateEvaluation",
    "ImprovementCycleReport",
    "ImprovementLoopConfig",
    "MutationConfig",
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
