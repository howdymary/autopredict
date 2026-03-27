"""AutoPredict - minimal framework for self-improving prediction market agents."""

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
