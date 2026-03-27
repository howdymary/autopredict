"""Prediction-market scaffold for venue-aware agent development."""

from autopredict.prediction_market.agent import (
    AgentConfig,
    AgentRunConfig,
    AutoPredictAgent,
    ExecutionStrategy,
    LegacyMarketState,
    MarketState,
    PredictionMarketAgent,
    ProposedOrder,
)
from autopredict.prediction_market.builtin import (
    LegacyMispricedStrategyAdapter,
    create_default_registry,
)
from autopredict.prediction_market.registry import (
    StrategyRegistration,
    StrategyRegistry,
)
from autopredict.prediction_market.strategy import (
    DirectProbabilityStrategy,
    PredictionMarketStrategy,
)
from autopredict.prediction_market.types import (
    AgentDecision,
    DecisionStatus,
    MarketSignal,
    MarketSnapshot,
    StrategyContext,
    VenueConfig,
    VenueName,
)

# Helpful aliases while the scaffold settles.
PredictionSignal = MarketSignal
Venue = VenueName

__all__ = [
    "AgentConfig",
    "AgentDecision",
    "AgentRunConfig",
    "AutoPredictAgent",
    "DecisionStatus",
    "DirectProbabilityStrategy",
    "ExecutionStrategy",
    "LegacyMarketState",
    "LegacyMispricedStrategyAdapter",
    "MarketState",
    "MarketSignal",
    "MarketSnapshot",
    "PredictionMarketAgent",
    "PredictionMarketStrategy",
    "PredictionSignal",
    "ProposedOrder",
    "StrategyContext",
    "StrategyRegistration",
    "StrategyRegistry",
    "Venue",
    "VenueConfig",
    "VenueName",
    "create_default_registry",
]
