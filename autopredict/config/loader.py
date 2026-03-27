"""Configuration loader with YAML support and environment variable substitution.

Handles loading configurations from YAML files, substituting environment variables,
and constructing type-safe configuration objects.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    raise ImportError(
        "PyYAML is required for configuration loading. "
        "Install it with: pip install pyyaml"
    )

from .schema import (
    ExperimentConfig,
    StrategyConfig,
    RiskConfig,
    VenueConfig,
    BacktestConfig,
    LoggingConfig,
)


# Pattern for environment variable substitution: ${VAR_NAME} or ${VAR_NAME:default}
ENV_VAR_PATTERN = re.compile(r'\$\{([^}:]+)(?::([^}]*))?\}')


def substitute_env_vars(value: Any) -> Any:
    """Recursively substitute environment variables in configuration values.

    Supports ${VAR_NAME} and ${VAR_NAME:default_value} syntax.

    Args:
        value: Configuration value (can be str, dict, list, or primitive)

    Returns:
        Value with environment variables substituted

    Example:
        >>> os.environ['API_KEY'] = 'secret123'
        >>> substitute_env_vars('${API_KEY}')
        'secret123'
        >>> substitute_env_vars('${MISSING:default}')
        'default'
        >>> substitute_env_vars({'key': '${API_KEY}'})
        {'key': 'secret123'}
    """
    if isinstance(value, str):
        def replace_var(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_value = os.environ.get(var_name)

            if env_value is not None:
                return env_value
            elif default is not None:
                return default
            else:
                raise ValueError(
                    f"Environment variable '{var_name}' not found and no default provided. "
                    f"Set it with: export {var_name}=<value>"
                )

        return ENV_VAR_PATTERN.sub(replace_var, value)

    elif isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}

    elif isinstance(value, list):
        return [substitute_env_vars(item) for item in value]

    else:
        return value


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load YAML file with environment variable substitution.

    Args:
        path: Path to YAML configuration file

    Returns:
        Configuration dictionary with env vars substituted

    Raises:
        FileNotFoundError: If configuration file doesn't exist
        yaml.YAMLError: If YAML is malformed
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, 'r') as f:
        raw_config = yaml.safe_load(f)

    if not isinstance(raw_config, dict):
        raise ValueError(f"Configuration file must contain a YAML mapping/dict, got {type(raw_config)}")

    # Substitute environment variables
    config = substitute_env_vars(raw_config)

    return config


def dict_to_strategy_config(data: dict[str, Any]) -> StrategyConfig:
    """Convert dictionary to StrategyConfig with validation."""
    return StrategyConfig(
        name=data.get("name", StrategyConfig.name),
        min_edge=float(data.get("min_edge", StrategyConfig.min_edge)),
        kelly_fraction=float(data.get("kelly_fraction", StrategyConfig.kelly_fraction)),
        max_position_pct=float(data.get("max_position_pct", StrategyConfig.max_position_pct)),
        aggressive_edge=float(data.get("aggressive_edge", StrategyConfig.aggressive_edge)),
        min_book_liquidity=float(data.get("min_book_liquidity", StrategyConfig.min_book_liquidity)),
        max_spread_pct=float(data.get("max_spread_pct", StrategyConfig.max_spread_pct)),
        max_depth_fraction=float(data.get("max_depth_fraction", StrategyConfig.max_depth_fraction)),
        split_threshold_fraction=float(data.get("split_threshold_fraction", StrategyConfig.split_threshold_fraction)),
        limit_price_improvement_ticks=float(data.get("limit_price_improvement_ticks", StrategyConfig.limit_price_improvement_ticks)),
    )


def dict_to_risk_config(data: dict[str, Any]) -> RiskConfig:
    """Convert dictionary to RiskConfig with validation."""
    return RiskConfig(
        max_position_per_market=float(data.get("max_position_per_market", RiskConfig.max_position_per_market)),
        max_total_exposure=float(data.get("max_total_exposure", RiskConfig.max_total_exposure)),
        max_daily_loss=float(data.get("max_daily_loss", RiskConfig.max_daily_loss)),
        kill_switch_threshold=float(data.get("kill_switch_threshold", RiskConfig.kill_switch_threshold)),
        max_positions=int(data.get("max_positions", RiskConfig.max_positions)),
        max_correlation_exposure=float(data.get("max_correlation_exposure", RiskConfig.max_correlation_exposure)),
        position_timeout_hours=float(data.get("position_timeout_hours", RiskConfig.position_timeout_hours)),
        enable_kill_switch=bool(data.get("enable_kill_switch", RiskConfig.enable_kill_switch)),
    )


def dict_to_venue_config(data: dict[str, Any]) -> VenueConfig:
    """Convert dictionary to VenueConfig with validation."""
    return VenueConfig(
        name=data.get("name", VenueConfig.name),
        mode=data.get("mode", VenueConfig.mode),
        api_key=data.get("api_key"),
        api_secret=data.get("api_secret"),
        base_url=data.get("base_url"),
        max_requests_per_minute=int(data.get("max_requests_per_minute", VenueConfig.max_requests_per_minute)),
        timeout_seconds=float(data.get("timeout_seconds", VenueConfig.timeout_seconds)),
        enable_websocket=bool(data.get("enable_websocket", VenueConfig.enable_websocket)),
        testnet=bool(data.get("testnet", VenueConfig.testnet)),
    )


def dict_to_backtest_config(data: dict[str, Any]) -> BacktestConfig:
    """Convert dictionary to BacktestConfig with validation."""
    return BacktestConfig(
        initial_bankroll=float(data.get("initial_bankroll", BacktestConfig.initial_bankroll)),
        commission_rate=float(data.get("commission_rate", BacktestConfig.commission_rate)),
        slippage_model=data.get("slippage_model", BacktestConfig.slippage_model),
        slippage_bps=float(data.get("slippage_bps", BacktestConfig.slippage_bps)),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        data_source=data.get("data_source", BacktestConfig.data_source),
    )


def dict_to_logging_config(data: dict[str, Any]) -> LoggingConfig:
    """Convert dictionary to LoggingConfig with validation."""
    return LoggingConfig(
        log_dir=data.get("log_dir", LoggingConfig.log_dir),
        log_level=data.get("log_level", LoggingConfig.log_level),
        log_trades=bool(data.get("log_trades", LoggingConfig.log_trades)),
        log_decisions=bool(data.get("log_decisions", LoggingConfig.log_decisions)),
        log_performance=bool(data.get("log_performance", LoggingConfig.log_performance)),
        performance_interval_minutes=float(data.get("performance_interval_minutes", LoggingConfig.performance_interval_minutes)),
        structured_format=bool(data.get("structured_format", LoggingConfig.structured_format)),
        console_output=bool(data.get("console_output", LoggingConfig.console_output)),
    )


def load_config(path: str | Path) -> ExperimentConfig:
    """Load complete experiment configuration from YAML file.

    This is the main entry point for loading configurations. It handles:
    - YAML parsing
    - Environment variable substitution
    - Type conversion and validation
    - Cross-configuration consistency checks

    Args:
        path: Path to YAML configuration file

    Returns:
        Validated ExperimentConfig object

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If configuration is invalid
        yaml.YAMLError: If YAML is malformed

    Example:
        >>> config = load_config("configs/paper_trading.yaml")
        >>> config.validate()
        >>> print(f"Loaded {config.name} in {config.venue.mode} mode")
    """
    data = load_yaml(path)

    # Extract sub-configurations
    strategy_data = data.get("strategy", {})
    risk_data = data.get("risk", {})
    venue_data = data.get("venue", {})
    backtest_data = data.get("backtest", {})
    logging_data = data.get("logging", {})

    # Build configuration object
    config = ExperimentConfig(
        name=data.get("name", "default_experiment"),
        description=data.get("description", ""),
        strategy=dict_to_strategy_config(strategy_data),
        risk=dict_to_risk_config(risk_data),
        venue=dict_to_venue_config(venue_data),
        backtest=dict_to_backtest_config(backtest_data),
        logging=dict_to_logging_config(logging_data),
        metadata=data.get("metadata", {}),
    )

    # Validate entire configuration
    config.validate()

    return config


def validate_config(config: ExperimentConfig) -> list[str]:
    """Validate configuration and return list of warnings.

    Performs deep validation and returns non-fatal warnings.
    Fatal errors will raise exceptions.

    Args:
        config: Configuration to validate

    Returns:
        List of warning messages (empty if no warnings)

    Example:
        >>> config = load_config("configs/my_config.yaml")
        >>> warnings = validate_config(config)
        >>> for warning in warnings:
        ...     print(f"WARNING: {warning}")
    """
    warnings = []

    # Live trading warnings
    if config.is_live():
        if config.risk.max_daily_loss > 1000:
            warnings.append(f"max_daily_loss is very high for live trading: ${config.risk.max_daily_loss}")

        if config.risk.max_total_exposure > 10000:
            warnings.append(f"max_total_exposure is very high for live trading: ${config.risk.max_total_exposure}")

        if not config.risk.enable_kill_switch:
            warnings.append("Kill switch is disabled for live trading - this is dangerous!")

        if config.venue.testnet:
            warnings.append("Using testnet for live trading - verify this is intentional")

    # Strategy sanity checks
    if config.strategy.min_edge > 0.2:
        warnings.append(f"min_edge is very high ({config.strategy.min_edge}) - you may get very few trades")

    if config.strategy.kelly_fraction > 0.5:
        warnings.append(f"kelly_fraction is aggressive ({config.strategy.kelly_fraction}) - consider reducing to 0.25")

    # Risk consistency checks
    if config.risk.max_position_per_market > config.risk.max_total_exposure:
        warnings.append(
            f"max_position_per_market ({config.risk.max_position_per_market}) > "
            f"max_total_exposure ({config.risk.max_total_exposure}) - single position could exceed total limit"
        )

    # Backtest checks
    if config.backtest.commission_rate > 0.05:
        warnings.append(f"commission_rate is very high ({config.backtest.commission_rate * 100}%)")

    return warnings


def save_config(config: ExperimentConfig, path: str | Path) -> None:
    """Save configuration to YAML file.

    Args:
        config: Configuration to save
        path: Output path for YAML file

    Example:
        >>> config = ExperimentConfig(name="my_experiment")
        >>> save_config(config, "configs/my_config.yaml")
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w') as f:
        yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)
