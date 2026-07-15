"""Configuration system for AutoPredict.

Provides type-safe configuration management with YAML support and validation.
"""

from .schema import (
    StrategyConfig,
    RiskConfig,
    VenueConfig,
    ExperimentConfig,
    BacktestConfig,
    LoggingConfig,
)
from .loader import load_config, validate_config, save_config
from .shadow import SHADOW_CONFIG_VERSION, ShadowConfig, load_shadow_config

__all__ = [
    "StrategyConfig",
    "RiskConfig",
    "VenueConfig",
    "ExperimentConfig",
    "BacktestConfig",
    "LoggingConfig",
    "load_config",
    "validate_config",
    "save_config",
    "SHADOW_CONFIG_VERSION",
    "ShadowConfig",
    "load_shadow_config",
]
