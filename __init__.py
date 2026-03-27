"""AutoPredict - minimal framework for self-improving prediction market agents."""

from pathlib import Path
from pkgutil import extend_path

__version__ = "0.1.0"

# Allow this repo to expose both the legacy top-level modules and the packaged
# implementation under ./autopredict/ during the current migration.
__path__ = extend_path(__path__, __name__)
_nested_package = Path(__file__).resolve().parent / "autopredict"
if _nested_package.is_dir():
    __path__.append(str(_nested_package))

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
