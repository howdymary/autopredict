"""Trade logging for decision tracking and performance analysis.

This module provides structured logging of all trading decisions with full context,
enabling post-hoc analysis and learning from outcomes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TradeLog:
    """Structured log entry for a single trading decision.

    Captures all context needed to understand why a trade was made and how it performed.
    Designed for easy serialization to JSONL and streaming analysis.

    Attributes:
        timestamp: When the decision was made (UTC)
        market_id: Unique identifier for the market
        market_prob: Market's implied probability at decision time
        model_prob: Our model's forecasted probability
        edge: Absolute edge (model_prob - market_prob or market_prob - model_prob)
        decision: Action taken: "buy", "sell", or "pass"
        size: Position size in currency units (0 for "pass")
        execution_price: Actual fill price (None if pass or unfilled)
        outcome: Final market outcome: 1 (resolved YES), 0 (resolved NO), None (pending)
        pnl: Realized profit/loss for this trade (None until outcome known)
        rationale: Dictionary of feature values and decision factors
            Example: {
                "order_type": "limit",
                "spread_pct": 0.03,
                "liquidity_depth": 150.0,
                "time_to_expiry_hours": 24.0,
                "category": "politics",
                "min_edge_threshold": 0.05,
                "passed_reason": None or "edge_too_small" or "spread_too_wide"
            }

    Example:
        >>> log = TradeLog(
        ...     timestamp=datetime.now(timezone.utc),
        ...     market_id="politics-2025-03",
        ...     market_prob=0.45,
        ...     model_prob=0.65,
        ...     edge=0.20,
        ...     decision="buy",
        ...     size=20.0,
        ...     execution_price=0.46,
        ...     outcome=None,  # Filled in later when market resolves
        ...     pnl=None,  # Filled in later
        ...     rationale={
        ...         "order_type": "limit",
        ...         "spread_pct": 0.02,
        ...         "liquidity_depth": 200.0,
        ...         "time_to_expiry_hours": 48.0,
        ...         "category": "politics"
        ...     }
        ... )
    """

    timestamp: datetime
    market_id: str
    market_prob: float
    model_prob: float
    edge: float
    decision: str  # "buy", "sell", "pass"
    size: float
    execution_price: float | None
    outcome: int | None  # 1 for YES, 0 for NO, None for pending
    pnl: float | None
    rationale: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        data = asdict(self)
        # Convert datetime to ISO format string
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradeLog:
        """Reconstruct from dictionary."""
        # Parse timestamp string back to datetime
        if isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

    def to_jsonl(self) -> str:
        """Serialize to JSONL format (single line JSON)."""
        return json.dumps(self.to_dict(), separators=(',', ':'))

    @classmethod
    def from_jsonl(cls, line: str) -> TradeLog:
        """Deserialize from JSONL format."""
        return cls.from_dict(json.loads(line))


class TradeLogger:
    """Manages trade log persistence to JSONL files.

    Provides thread-safe appending to log files and batch loading for analysis.
    Uses JSONL format (one JSON object per line) for easy streaming and incremental
    processing of large log files.

    Example:
        >>> logger = TradeLogger(Path("state/trades"))
        >>> log = TradeLog(...)
        >>> logger.append(log)
        >>>
        >>> # Later: load all logs for analysis
        >>> all_logs = logger.load_all()
        >>> recent_logs = logger.load_recent(days=7)
    """

    def __init__(self, log_dir: Path):
        """Initialize logger with target directory.

        Args:
            log_dir: Directory to store JSONL log files
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self, date: datetime | None = None) -> Path:
        """Get log file path for a given date (defaults to today).

        Uses daily log rotation: trades_YYYYMMDD.jsonl
        """
        if date is None:
            date = datetime.now(timezone.utc)
        filename = f"trades_{date.strftime('%Y%m%d')}.jsonl"
        return self.log_dir / filename

    def append(self, log: TradeLog) -> None:
        """Append a trade log entry to the appropriate daily log file.

        Args:
            log: TradeLog entry to append
        """
        log_file = self._get_log_file(log.timestamp)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(log.to_jsonl() + "\n")

    def append_batch(self, logs: list[TradeLog]) -> None:
        """Append multiple log entries efficiently.

        Groups logs by date and writes to appropriate files.

        Args:
            logs: List of TradeLog entries to append
        """
        # Group logs by date
        logs_by_date: dict[str, list[TradeLog]] = {}
        for log in logs:
            date_key = log.timestamp.strftime('%Y%m%d')
            if date_key not in logs_by_date:
                logs_by_date[date_key] = []
            logs_by_date[date_key].append(log)

        # Write each group to appropriate file
        for date_key, date_logs in logs_by_date.items():
            log_file = self.log_dir / f"trades_{date_key}.jsonl"
            with log_file.open("a", encoding="utf-8") as f:
                for log in date_logs:
                    f.write(log.to_jsonl() + "\n")

    def load_file(self, log_file: Path) -> list[TradeLog]:
        """Load all entries from a specific log file.

        Args:
            log_file: Path to JSONL log file

        Returns:
            List of TradeLog entries
        """
        if not log_file.exists():
            return []

        logs = []
        with log_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:  # Skip empty lines
                    logs.append(TradeLog.from_jsonl(line))
        return logs

    def load_all(self) -> list[TradeLog]:
        """Load all trade logs from all log files.

        Returns:
            List of all TradeLog entries, sorted by timestamp
        """
        all_logs = []
        for log_file in sorted(self.log_dir.glob("trades_*.jsonl")):
            all_logs.extend(self.load_file(log_file))

        # Sort by timestamp
        all_logs.sort(key=lambda x: x.timestamp)
        return all_logs

    def load_recent(self, days: int = 7) -> list[TradeLog]:
        """Load trade logs from the last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of TradeLog entries from last N days
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        all_logs = self.load_all()
        return [log for log in all_logs if log.timestamp.timestamp() >= cutoff]

    def load_by_market(self, market_id: str) -> list[TradeLog]:
        """Load all logs for a specific market.

        Args:
            market_id: Market identifier

        Returns:
            List of TradeLog entries for the specified market
        """
        all_logs = self.load_all()
        return [log for log in all_logs if log.market_id == market_id]

    def update_outcomes(self, market_outcomes: dict[str, int]) -> int:
        """Update outcome and PnL fields for resolved markets.

        Rewrites log files with updated outcome and PnL information.

        Args:
            market_outcomes: Map of market_id -> outcome (1 for YES, 0 for NO)

        Returns:
            Number of log entries updated
        """
        updated_count = 0

        # Process each log file
        for log_file in self.log_dir.glob("trades_*.jsonl"):
            logs = self.load_file(log_file)
            modified = False

            for log in logs:
                if log.market_id in market_outcomes and log.outcome is None:
                    log.outcome = market_outcomes[log.market_id]

                    # Calculate PnL if we have execution price
                    if log.execution_price is not None and log.decision != "pass":
                        if log.decision == "buy":
                            # Bought at execution_price, resolves to outcome
                            log.pnl = log.size * (log.outcome - log.execution_price)
                        elif log.decision == "sell":
                            # Sold at execution_price, resolves to outcome
                            log.pnl = log.size * (log.execution_price - log.outcome)

                    modified = True
                    updated_count += 1

            # Rewrite file if any logs were modified
            if modified:
                with log_file.open("w", encoding="utf-8") as f:
                    for log in logs:
                        f.write(log.to_jsonl() + "\n")

        return updated_count
