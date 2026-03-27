"""Self-improvement and learning module for AutoPredict.

This module provides tools for logging trading decisions, analyzing performance,
and automatically tuning strategy parameters through backtesting.
"""

from .logger import TradeLog, TradeLogger
from .analyzer import PerformanceAnalyzer, PerformanceReport
from .tuner import GridSearchTuner, ParameterGrid

__all__ = [
    "TradeLog",
    "TradeLogger",
    "PerformanceAnalyzer",
    "PerformanceReport",
    "GridSearchTuner",
    "ParameterGrid",
]
