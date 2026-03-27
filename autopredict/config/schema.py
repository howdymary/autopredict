"""Configuration schemas for AutoPredict.

Type-safe dataclasses for all configuration aspects: strategy, risk, venue, and experiments.
Designed for YAML serialization and runtime validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class StrategyConfig:
    """Strategy configuration for trading decisions.

    Controls how the agent identifies trading opportunities and sizes positions.

    Attributes:
        name: Strategy identifier (e.g., "mispriced_probability", "value_betting")
        min_edge: Minimum probability edge to consider a trade (0-1)
        kelly_fraction: Kelly criterion scaling factor (0-1, typically 0.25 for quarter-Kelly)
        max_position_pct: Maximum position size as percentage of bankroll (0-1)
        aggressive_edge: Edge threshold for aggressive (market) orders vs passive (limit) orders
        min_book_liquidity: Minimum total order book depth required to trade
        max_spread_pct: Maximum bid-ask spread (as % of mid) to trade unless edge is very strong
        max_depth_fraction: Maximum position as fraction of visible order book depth
        split_threshold_fraction: Order size threshold (relative to depth) that triggers order splitting
        limit_price_improvement_ticks: Number of ticks to improve limit price beyond best bid/ask

    Example:
        >>> config = StrategyConfig(
        ...     name="conservative_value",
        ...     min_edge=0.08,
        ...     kelly_fraction=0.20,
        ...     max_position_pct=0.01
        ... )
    """

    name: str = "mispriced_probability"
    min_edge: float = 0.05
    kelly_fraction: float = 0.25
    max_position_pct: float = 0.02
    aggressive_edge: float = 0.12
    min_book_liquidity: float = 60.0
    max_spread_pct: float = 0.04
    max_depth_fraction: float = 0.15
    split_threshold_fraction: float = 0.25
    limit_price_improvement_ticks: float = 1.0

    def validate(self) -> None:
        """Validate strategy configuration parameters.

        Raises:
            ValueError: If any parameter is out of valid range
        """
        if not self.name:
            raise ValueError("Strategy name cannot be empty")
        if not 0 < self.min_edge < 1:
            raise ValueError(f"min_edge must be in (0, 1), got {self.min_edge}")
        if not 0 < self.kelly_fraction <= 1:
            raise ValueError(f"kelly_fraction must be in (0, 1], got {self.kelly_fraction}")
        if not 0 < self.max_position_pct <= 1:
            raise ValueError(f"max_position_pct must be in (0, 1], got {self.max_position_pct}")
        if not 0 < self.aggressive_edge < 1:
            raise ValueError(f"aggressive_edge must be in (0, 1), got {self.aggressive_edge}")
        if self.min_book_liquidity < 0:
            raise ValueError(f"min_book_liquidity must be non-negative, got {self.min_book_liquidity}")
        if not 0 < self.max_spread_pct <= 1:
            raise ValueError(f"max_spread_pct must be in (0, 1], got {self.max_spread_pct}")
        if not 0 < self.max_depth_fraction <= 1:
            raise ValueError(f"max_depth_fraction must be in (0, 1], got {self.max_depth_fraction}")
        if not 0 < self.split_threshold_fraction <= 1:
            raise ValueError(f"split_threshold_fraction must be in (0, 1], got {self.split_threshold_fraction}")
        if self.limit_price_improvement_ticks < 0:
            raise ValueError(f"limit_price_improvement_ticks must be non-negative, got {self.limit_price_improvement_ticks}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class RiskConfig:
    """Risk management configuration.

    Enforces position limits, exposure caps, and circuit breakers to protect capital.
    All limits are enforced pre-trade by the RiskManager.

    Attributes:
        max_position_per_market: Maximum position size per individual market (in currency units)
        max_total_exposure: Maximum total exposure across all positions (in currency units)
        max_daily_loss: Maximum allowed loss in a single day (in currency units, positive value)
        kill_switch_threshold: Loss threshold that triggers immediate trading halt (negative value)
        max_positions: Maximum number of simultaneous open positions
        max_correlation_exposure: Maximum exposure to correlated markets (future use)
        position_timeout_hours: Maximum time to hold a position before forced exit
        enable_kill_switch: Whether to enable the kill switch (should always be True in production)

    Example:
        >>> config = RiskConfig(
        ...     max_position_per_market=100.0,
        ...     max_total_exposure=500.0,
        ...     max_daily_loss=50.0,
        ...     kill_switch_threshold=-100.0
        ... )
    """

    max_position_per_market: float = 100.0
    max_total_exposure: float = 500.0
    max_daily_loss: float = 50.0
    kill_switch_threshold: float = -100.0
    max_positions: int = 20
    max_correlation_exposure: float = 0.3
    position_timeout_hours: float = 168.0  # 1 week
    enable_kill_switch: bool = True

    def validate(self) -> None:
        """Validate risk configuration parameters.

        Raises:
            ValueError: If any parameter is invalid or inconsistent
        """
        if self.max_position_per_market <= 0:
            raise ValueError(f"max_position_per_market must be positive, got {self.max_position_per_market}")
        if self.max_total_exposure <= 0:
            raise ValueError(f"max_total_exposure must be positive, got {self.max_total_exposure}")
        if self.max_daily_loss <= 0:
            raise ValueError(f"max_daily_loss must be positive, got {self.max_daily_loss}")
        if self.kill_switch_threshold >= 0:
            raise ValueError(f"kill_switch_threshold must be negative, got {self.kill_switch_threshold}")
        if abs(self.kill_switch_threshold) < self.max_daily_loss:
            raise ValueError(
                f"kill_switch_threshold ({self.kill_switch_threshold}) should be more severe than "
                f"max_daily_loss ({self.max_daily_loss})"
            )
        if self.max_positions <= 0:
            raise ValueError(f"max_positions must be positive, got {self.max_positions}")
        if not 0 <= self.max_correlation_exposure <= 1:
            raise ValueError(f"max_correlation_exposure must be in [0, 1], got {self.max_correlation_exposure}")
        if self.position_timeout_hours <= 0:
            raise ValueError(f"position_timeout_hours must be positive, got {self.position_timeout_hours}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class VenueConfig:
    """Trading venue configuration.

    Specifies which prediction market to trade on and how to connect.

    Attributes:
        name: Venue identifier ("polymarket", "manifold", "kalshi", etc.)
        mode: Trading mode - "paper" (simulated) or "live" (real money)
        api_key: API key for authentication (can use environment variable reference)
        api_secret: API secret for authentication (can use environment variable reference)
        base_url: Base URL for API endpoints (optional, uses default if not specified)
        max_requests_per_minute: Rate limiting for API calls
        timeout_seconds: Request timeout in seconds
        enable_websocket: Whether to use WebSocket for real-time data
        testnet: Whether to use testnet/sandbox mode (if available)

    Example:
        >>> config = VenueConfig(
        ...     name="polymarket",
        ...     mode="paper",
        ...     api_key="${POLYMARKET_API_KEY}"
        ... )
    """

    name: str = "polymarket"
    mode: str = "paper"
    api_key: str | None = None
    api_secret: str | None = None
    base_url: str | None = None
    max_requests_per_minute: int = 60
    timeout_seconds: float = 30.0
    enable_websocket: bool = False
    testnet: bool = True

    def validate(self) -> None:
        """Validate venue configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        if not self.name:
            raise ValueError("Venue name cannot be empty")
        if self.mode not in ("paper", "live"):
            raise ValueError(f"mode must be 'paper' or 'live', got '{self.mode}'")
        if self.mode == "live" and not self.api_key:
            raise ValueError("api_key is required for live trading mode")
        if self.max_requests_per_minute <= 0:
            raise ValueError(f"max_requests_per_minute must be positive, got {self.max_requests_per_minute}")
        if self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {self.timeout_seconds}")

    def is_live(self) -> bool:
        """Check if venue is configured for live trading."""
        return self.mode == "live"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class BacktestConfig:
    """Backtesting configuration.

    Attributes:
        initial_bankroll: Starting capital for backtest
        commission_rate: Trading commission as decimal (e.g., 0.01 for 1%)
        slippage_model: Slippage model to use ("fixed", "proportional", "market_impact")
        slippage_bps: Base slippage in basis points
        start_date: Backtest start date (YYYY-MM-DD format)
        end_date: Backtest end date (YYYY-MM-DD format)
        data_source: Data source for historical prices
    """

    initial_bankroll: float = 1000.0
    commission_rate: float = 0.01
    slippage_model: str = "proportional"
    slippage_bps: float = 5.0
    start_date: str | None = None
    end_date: str | None = None
    data_source: str = "simulation"

    def validate(self) -> None:
        """Validate backtest configuration."""
        if self.initial_bankroll <= 0:
            raise ValueError(f"initial_bankroll must be positive, got {self.initial_bankroll}")
        if not 0 <= self.commission_rate < 1:
            raise ValueError(f"commission_rate must be in [0, 1), got {self.commission_rate}")
        if self.slippage_model not in ("fixed", "proportional", "market_impact"):
            raise ValueError(f"Invalid slippage_model: {self.slippage_model}")
        if self.slippage_bps < 0:
            raise ValueError(f"slippage_bps must be non-negative, got {self.slippage_bps}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class LoggingConfig:
    """Logging configuration.

    Attributes:
        log_dir: Directory for log files
        log_level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR")
        log_trades: Whether to log individual trades
        log_decisions: Whether to log all trading decisions (including skips)
        log_performance: Whether to log periodic performance snapshots
        performance_interval_minutes: How often to log performance snapshots
        structured_format: Whether to use JSON format for structured logs
        console_output: Whether to output logs to console in addition to files
    """

    log_dir: str = "./logs"
    log_level: str = "INFO"
    log_trades: bool = True
    log_decisions: bool = True
    log_performance: bool = True
    performance_interval_minutes: float = 60.0
    structured_format: bool = True
    console_output: bool = True

    def validate(self) -> None:
        """Validate logging configuration."""
        valid_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        if self.log_level not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got '{self.log_level}'")
        if self.performance_interval_minutes <= 0:
            raise ValueError(f"performance_interval_minutes must be positive, got {self.performance_interval_minutes}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class ExperimentConfig:
    """Complete experiment configuration.

    Top-level configuration that combines all aspects of a trading experiment.
    This is the main configuration object loaded from YAML files.

    Attributes:
        name: Experiment name/identifier
        description: Human-readable experiment description
        strategy: Strategy configuration
        risk: Risk management configuration
        venue: Trading venue configuration
        backtest: Backtesting configuration
        logging: Logging configuration
        metadata: Additional metadata (tags, notes, etc.)

    Example:
        >>> config = ExperimentConfig(
        ...     name="conservative_paper_trading",
        ...     strategy=StrategyConfig(min_edge=0.08),
        ...     risk=RiskConfig(max_daily_loss=25.0),
        ...     venue=VenueConfig(mode="paper")
        ... )
        >>> config.validate()
    """

    name: str = "default_experiment"
    description: str = ""
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    venue: VenueConfig = field(default_factory=VenueConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate entire experiment configuration.

        Validates all sub-configurations and checks for consistency.

        Raises:
            ValueError: If any configuration is invalid
        """
        if not self.name:
            raise ValueError("Experiment name cannot be empty")

        # Validate all sub-configurations
        self.strategy.validate()
        self.risk.validate()
        self.venue.validate()
        self.backtest.validate()
        self.logging.validate()

        # Cross-validation: live mode should have stricter settings
        if self.venue.is_live():
            if not self.risk.enable_kill_switch:
                raise ValueError("Kill switch must be enabled for live trading")
            if self.risk.max_daily_loss > 1000.0:
                # Warning: this is a soft limit, not a hard error
                import warnings
                warnings.warn(f"max_daily_loss is very high for live trading: {self.risk.max_daily_loss}")

    def to_dict(self) -> dict[str, Any]:
        """Convert entire configuration to dictionary.

        Returns:
            Nested dictionary suitable for JSON/YAML serialization
        """
        return {
            "name": self.name,
            "description": self.description,
            "strategy": self.strategy.to_dict(),
            "risk": self.risk.to_dict(),
            "venue": self.venue.to_dict(),
            "backtest": self.backtest.to_dict(),
            "logging": self.logging.to_dict(),
            "metadata": self.metadata,
        }

    def is_live(self) -> bool:
        """Check if this experiment is configured for live trading."""
        return self.venue.is_live()

    def is_paper(self) -> bool:
        """Check if this experiment is configured for paper trading."""
        return self.venue.mode == "paper"
