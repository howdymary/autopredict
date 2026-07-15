"""Live trading infrastructure for AutoPredict.

Provides paper trading simulation and live trading execution with safety controls.
"""

from autopredict.core.types import ExecutionReport, Order
from .risk import RiskManager, RiskCheckResult
from .monitor import Monitor, TradeLog, DecisionLog
from .safety_audit import SafetyAuditResult, run_safety_audit

__all__ = [
    "PaperTrader",
    "LiveTrader",
    "ExecutionReport",
    "Order",
    "RiskManager",
    "RiskCheckResult",
    "Monitor",
    "TradeLog",
    "DecisionLog",
    "SafetyAuditResult",
    "run_safety_audit",
]


def __getattr__(name: str):
    """Keep legacy trader imports lazy so shadow imports have no live capability."""

    if name in {"PaperTrader", "LiveTrader"}:
        from .trader import LiveTrader, PaperTrader

        return {"PaperTrader": PaperTrader, "LiveTrader": LiveTrader}[name]
    raise AttributeError(name)
