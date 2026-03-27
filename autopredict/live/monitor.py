"""Logging and monitoring system for live trading.

Structured logging with multiple output streams:
- trades.jsonl: All trade executions
- decisions.jsonl: All trading decisions (including skips)
- errors.log: Error messages and exceptions
- performance.jsonl: Periodic performance snapshots

All logs use structured JSON format for easy parsing and analysis.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config.schema import LoggingConfig


@dataclass
class TradeLog:
    """Structured trade log entry.

    Attributes:
        timestamp: When trade occurred
        market_id: Market identifier
        side: "buy" or "sell"
        order_type: "market" or "limit"
        size: Position size
        price: Execution price
        commission: Commission paid
        slippage_bps: Slippage in basis points
        execution_mode: "paper" or "live"
        success: Whether trade was successful
        error: Error message if failed
        metadata: Additional trade metadata
    """

    timestamp: str
    market_id: str
    side: str
    order_type: str
    size: float
    price: float | None
    commission: float
    slippage_bps: float
    execution_mode: str
    success: bool
    error: str | None = None
    metadata: dict[str, Any] | None = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self))


@dataclass
class DecisionLog:
    """Structured decision log entry.

    Logs all trading decisions, including skipped opportunities.

    Attributes:
        timestamp: When decision was made
        market_id: Market identifier
        decision: "trade" or "skip"
        reason: Explanation for decision
        edge: Calculated edge
        market_price: Current market price
        fair_price: Agent's fair price estimate
        proposed_size: Size that would be traded (if decision=trade)
        proposed_side: Side that would be traded (if decision=trade)
        metadata: Additional decision context
    """

    timestamp: str
    market_id: str
    decision: str
    reason: str
    edge: float
    market_price: float
    fair_price: float
    proposed_size: float | None = None
    proposed_side: str | None = None
    metadata: dict[str, Any] | None = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self))


@dataclass
class PerformanceSnapshot:
    """Performance metrics snapshot.

    Attributes:
        timestamp: When snapshot was taken
        total_pnl: Total realized + unrealized P&L
        daily_pnl: P&L for current day
        num_trades: Total number of trades
        num_positions: Current open positions
        total_exposure: Current total exposure
        win_rate: Percentage of winning trades
        avg_trade_pnl: Average P&L per trade
        sharpe_ratio: Sharpe ratio (if calculable)
        max_drawdown: Maximum drawdown
        metadata: Additional metrics
    """

    timestamp: str
    total_pnl: float
    daily_pnl: float
    num_trades: int
    num_positions: int
    total_exposure: float
    win_rate: float | None = None
    avg_trade_pnl: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown: float | None = None
    metadata: dict[str, Any] | None = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self))


class Monitor:
    """Logging and monitoring system.

    Manages structured logging to multiple files and provides real-time metrics.

    Example:
        >>> from autopredict.config import LoggingConfig
        >>> config = LoggingConfig(log_dir="./logs", log_level="INFO")
        >>> monitor = Monitor(config)
        >>> monitor.log_trade(TradeLog(...))
        >>> monitor.log_decision(DecisionLog(...))
        >>> metrics = monitor.get_live_metrics()
    """

    def __init__(self, config: LoggingConfig):
        """Initialize monitor with logging configuration.

        Args:
            config: Logging configuration
        """
        self.config = config
        self.log_dir = Path(config.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Initialize loggers
        self.trades_logger = self._setup_file_logger("trades", "trades.jsonl")
        self.decisions_logger = self._setup_file_logger("decisions", "decisions.jsonl")
        self.errors_logger = self._setup_file_logger("errors", "errors.log")
        self.performance_logger = self._setup_file_logger("performance", "performance.jsonl")

        # Main logger for console output
        self.logger = self._setup_main_logger()

        # Metrics tracking
        self.trade_count = 0
        self.decision_count = 0
        self.error_count = 0
        self.last_snapshot_time = datetime.now()

        self.logger.info("Monitor initialized")
        self.logger.info(f"Logs directory: {self.log_dir.absolute()}")

    def _setup_file_logger(self, name: str, filename: str) -> logging.Logger:
        """Set up a file logger for specific log type.

        Args:
            name: Logger name
            filename: Output filename

        Returns:
            Configured logger
        """
        logger = logging.getLogger(f"autopredict.{name}")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        # File handler
        file_path = self.log_dir / filename
        handler = logging.FileHandler(file_path, mode='a')
        handler.setLevel(logging.INFO)

        # No formatting for structured logs (JSON)
        if filename.endswith('.jsonl'):
            handler.setFormatter(logging.Formatter('%(message)s'))
        else:
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))

        logger.addHandler(handler)
        logger.propagate = False

        return logger

    def _setup_main_logger(self) -> logging.Logger:
        """Set up main logger for console and general logging."""
        logger = logging.getLogger("autopredict.monitor")
        logger.setLevel(getattr(logging, self.config.log_level))
        logger.handlers.clear()

        # Console handler
        if self.config.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(getattr(logging, self.config.log_level))
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            logger.addHandler(console_handler)

        # General log file
        file_handler = logging.FileHandler(self.log_dir / "monitor.log", mode='a')
        file_handler.setLevel(getattr(logging, self.config.log_level))
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)

        logger.propagate = False
        return logger

    def log_trade(self, trade: TradeLog) -> None:
        """Log a trade execution.

        Args:
            trade: Trade log entry
        """
        if not self.config.log_trades:
            return

        self.trades_logger.info(trade.to_json())
        self.trade_count += 1

        # Also log to main logger
        status = "SUCCESS" if trade.success else "FAILED"
        self.logger.info(
            f"TRADE [{status}] {trade.side} {trade.market_id} "
            f"size={trade.size:.2f} price={trade.price} mode={trade.execution_mode}"
        )

    def log_decision(self, decision: DecisionLog) -> None:
        """Log a trading decision.

        Args:
            decision: Decision log entry
        """
        if not self.config.log_decisions:
            return

        self.decisions_logger.info(decision.to_json())
        self.decision_count += 1

        # Log to main logger at DEBUG level for skips
        if decision.decision == "skip":
            self.logger.debug(
                f"DECISION [SKIP] {decision.market_id} - {decision.reason} "
                f"(edge={decision.edge:.4f})"
            )
        else:
            self.logger.info(
                f"DECISION [TRADE] {decision.market_id} - {decision.proposed_side} "
                f"size={decision.proposed_size:.2f} (edge={decision.edge:.4f})"
            )

    def log_error(self, error: Exception, context: dict[str, Any] | None = None) -> None:
        """Log an error with context.

        Args:
            error: Exception that occurred
            context: Additional context about the error
        """
        self.error_count += 1

        error_msg = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {},
        }

        self.errors_logger.error(json.dumps(error_msg))
        self.logger.error(f"ERROR: {type(error).__name__}: {error}")

    def log_performance(self, snapshot: PerformanceSnapshot) -> None:
        """Log a performance snapshot.

        Args:
            snapshot: Performance metrics snapshot
        """
        if not self.config.log_performance:
            return

        self.performance_logger.info(snapshot.to_json())
        self.last_snapshot_time = datetime.now()

        # Log summary to main logger
        self.logger.info(
            f"PERFORMANCE: PnL={snapshot.total_pnl:.2f} "
            f"Trades={snapshot.num_trades} Positions={snapshot.num_positions} "
            f"Exposure={snapshot.total_exposure:.2f}"
        )

    def get_live_metrics(self) -> dict[str, Any]:
        """Get current live metrics.

        Returns:
            Dictionary of current metrics
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "trade_count": self.trade_count,
            "decision_count": self.decision_count,
            "error_count": self.error_count,
            "uptime_seconds": (datetime.now() - self.last_snapshot_time).total_seconds(),
        }

    def should_log_performance(self) -> bool:
        """Check if it's time to log performance snapshot.

        Returns:
            True if performance should be logged based on interval
        """
        if not self.config.log_performance:
            return False

        elapsed_minutes = (datetime.now() - self.last_snapshot_time).total_seconds() / 60
        return elapsed_minutes >= self.config.performance_interval_minutes

    def info(self, message: str) -> None:
        """Log info message."""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """Log warning message."""
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """Log error message."""
        self.logger.error(message)

    def debug(self, message: str) -> None:
        """Log debug message."""
        self.logger.debug(message)

    def get_log_files(self) -> dict[str, Path]:
        """Get paths to all log files.

        Returns:
            Dictionary mapping log type to file path
        """
        return {
            "trades": self.log_dir / "trades.jsonl",
            "decisions": self.log_dir / "decisions.jsonl",
            "errors": self.log_dir / "errors.log",
            "performance": self.log_dir / "performance.jsonl",
            "monitor": self.log_dir / "monitor.log",
        }


def create_trade_log(
    market_id: str,
    side: str,
    order_type: str,
    size: float,
    price: float | None,
    commission: float,
    slippage_bps: float,
    execution_mode: str,
    success: bool,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TradeLog:
    """Helper function to create a trade log entry.

    Args:
        market_id: Market identifier
        side: "buy" or "sell"
        order_type: "market" or "limit"
        size: Position size
        price: Execution price
        commission: Commission paid
        slippage_bps: Slippage in basis points
        execution_mode: "paper" or "live"
        success: Whether trade was successful
        error: Error message if failed
        metadata: Additional metadata

    Returns:
        TradeLog entry
    """
    return TradeLog(
        timestamp=datetime.now().isoformat(),
        market_id=market_id,
        side=side,
        order_type=order_type,
        size=size,
        price=price,
        commission=commission,
        slippage_bps=slippage_bps,
        execution_mode=execution_mode,
        success=success,
        error=error,
        metadata=metadata,
    )


def create_decision_log(
    market_id: str,
    decision: str,
    reason: str,
    edge: float,
    market_price: float,
    fair_price: float,
    proposed_size: float | None = None,
    proposed_side: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DecisionLog:
    """Helper function to create a decision log entry.

    Args:
        market_id: Market identifier
        decision: "trade" or "skip"
        reason: Explanation for decision
        edge: Calculated edge
        market_price: Current market price
        fair_price: Agent's fair price
        proposed_size: Size that would be traded
        proposed_side: Side that would be traded
        metadata: Additional metadata

    Returns:
        DecisionLog entry
    """
    return DecisionLog(
        timestamp=datetime.now().isoformat(),
        market_id=market_id,
        decision=decision,
        reason=reason,
        edge=edge,
        market_price=market_price,
        fair_price=fair_price,
        proposed_size=proposed_size,
        proposed_side=proposed_side,
        metadata=metadata,
    )
