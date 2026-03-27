"""AutoPredict - minimal framework for self-improving prediction market agents."""

__version__ = "0.1.0"

from .agent import AgentConfig, AutoPredictAgent, ExecutionStrategy, MarketState, ProposedOrder
from .market_env import ExecutionEngine, ExecutionMetrics, OrderBook, evaluate_all

__all__ = [
    "AgentConfig",
    "AutoPredictAgent",
    "ExecutionEngine",
    "ExecutionMetrics",
    "ExecutionStrategy",
    "MarketState",
    "OrderBook",
    "ProposedOrder",
    "evaluate_all",
]
