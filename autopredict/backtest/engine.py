"""Backtest engine for prediction market strategies.

This module provides the core backtesting infrastructure for evaluating
trading strategies on historical prediction market data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import sys
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from agent import AutoPredictAgent, MarketState, ProposedOrder
from market_env import (
    BookLevel,
    ExecutionEngine,
    ExecutionReport,
    ForecastRecord,
    OrderBook,
    TradeRecord,
    evaluate_all,
)


@dataclass
class BacktestConfig:
    """Configuration for backtest execution.

    Attributes:
        starting_bankroll: Initial capital for the backtest
        maker_fee_bps: Maker fee in basis points (default 0.0)
        taker_fee_bps: Taker fee in basis points (default 0.0)
        enable_walk_forward: Enable walk-forward testing (default False)
        walk_forward_window: Size of walk-forward window in number of markets
        monte_carlo_runs: Number of Monte Carlo simulations (0 = disabled)
        random_seed: Random seed for reproducibility (None = no seeding)
        enable_position_tracking: Track position limits and exposure
        max_concurrent_positions: Maximum number of concurrent positions (0 = unlimited)
        enable_detailed_logging: Log every decision for debugging
    """

    starting_bankroll: float = 1000.0
    maker_fee_bps: float = 0.0
    taker_fee_bps: float = 0.0
    enable_walk_forward: bool = False
    walk_forward_window: int = 100
    monte_carlo_runs: int = 0
    random_seed: int | None = None
    enable_position_tracking: bool = True
    max_concurrent_positions: int = 0
    enable_detailed_logging: bool = False


class StrategyProtocol(Protocol):
    """Protocol for strategy objects that can be backtested.

    A strategy must implement evaluate_market() which takes a market state
    and bankroll, and returns an optional order proposal.
    """

    def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
        """Evaluate a market and return an order proposal if appropriate."""
        ...


@dataclass
class MarketSnapshot:
    """Single market snapshot at a point in time.

    This represents all information about a market at a specific timestamp,
    including order book state, fair value estimate, and eventual outcome.

    Attributes:
        market_id: Unique identifier for this market
        timestamp: Unix timestamp or index for this snapshot
        market_prob: Current market probability (0-1)
        fair_prob: Strategy's fair value estimate (0-1)
        time_to_expiry_hours: Hours until market resolution
        order_book: Current order book state
        outcome: Eventual outcome (0 or 1 for binary markets)
        next_mid_price: Mid price at next timestamp (for adverse selection analysis)
        metadata: Additional market metadata (category, tags, etc.)
    """

    market_id: str
    timestamp: float
    market_prob: float
    fair_prob: float
    time_to_expiry_hours: float
    order_book: OrderBook
    outcome: int
    next_mid_price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionState:
    """Current position state for position tracking.

    Tracks open positions, exposure, and position limits.

    Attributes:
        open_positions: Map of market_id to net position size
        total_exposure: Total notional exposure across all positions
        position_count: Number of open positions
    """

    open_positions: dict[str, float] = field(default_factory=dict)
    total_exposure: float = 0.0
    position_count: int = 0

    def add_position(self, market_id: str, size: float, price: float) -> None:
        """Add or update a position."""
        current = self.open_positions.get(market_id, 0.0)
        self.open_positions[market_id] = current + size
        self.total_exposure += abs(size * price)
        if market_id not in self.open_positions or current == 0:
            self.position_count += 1

    def close_position(self, market_id: str) -> None:
        """Close a position."""
        if market_id in self.open_positions:
            del self.open_positions[market_id]
            self.position_count = len(self.open_positions)


@dataclass
class BacktestResult:
    """Results from a backtest run.

    Contains all metrics, trades, and analysis from the backtest.

    Attributes:
        config: Backtest configuration used
        starting_bankroll: Initial capital
        ending_bankroll: Final capital
        total_pnl: Total profit/loss
        num_markets_seen: Number of markets evaluated
        num_trades: Number of trades executed
        forecasts: All probability forecasts made
        trades: All executed trades with outcomes
        metrics: Comprehensive performance metrics
        position_history: History of position states (if tracking enabled)
        decision_log: Detailed decision log (if logging enabled)
    """

    config: BacktestConfig
    starting_bankroll: float
    ending_bankroll: float
    total_pnl: float
    num_markets_seen: int
    num_trades: int
    forecasts: list[ForecastRecord]
    trades: list[TradeRecord]
    metrics: dict[str, Any]
    position_history: list[dict[str, Any]] = field(default_factory=list)
    decision_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "config": {
                "starting_bankroll": self.config.starting_bankroll,
                "maker_fee_bps": self.config.maker_fee_bps,
                "taker_fee_bps": self.config.taker_fee_bps,
                "enable_walk_forward": self.config.enable_walk_forward,
                "walk_forward_window": self.config.walk_forward_window,
                "monte_carlo_runs": self.config.monte_carlo_runs,
            },
            "starting_bankroll": self.starting_bankroll,
            "ending_bankroll": self.ending_bankroll,
            "total_pnl": self.total_pnl,
            "num_markets_seen": self.num_markets_seen,
            "num_trades": self.num_trades,
            "metrics": self.metrics,
            "num_forecasts": len(self.forecasts),
            "position_history_length": len(self.position_history),
            "decision_log_length": len(self.decision_log),
        }

    def save(self, path: str | Path) -> None:
        """Save backtest result to JSON file."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save main results
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)

        # Save detailed trades if any
        if self.trades:
            trades_path = output_path.parent / f"{output_path.stem}_trades.json"
            trades_data = [
                {
                    "market_id": t.market_id,
                    "side": t.side,
                    "order_type": t.order_type,
                    "requested_size": t.requested_size,
                    "filled_size": t.filled_size,
                    "fill_price": t.fill_price,
                    "mid_at_decision": t.mid_at_decision,
                    "next_mid_price": t.next_mid_price,
                    "outcome": t.outcome,
                    "pnl": t.pnl,
                    "slippage_bps": t.slippage_bps,
                    "market_impact_bps": t.market_impact_bps,
                }
                for t in self.trades
            ]
            with trades_path.open("w", encoding="utf-8") as f:
                json.dump(trades_data, f, indent=2)


class BacktestEngine:
    """Core backtest engine for prediction market strategies.

    This engine simulates strategy execution over historical market data,
    tracking positions, executing orders, and computing comprehensive metrics.

    Example:
        >>> config = BacktestConfig(starting_bankroll=1000.0)
        >>> strategy = AutoPredictAgent.from_mapping({"min_edge": 0.05})
        >>> engine = BacktestEngine(config=config, strategy=strategy)
        >>> result = engine.run(snapshots)
        >>> print(f"PnL: ${result.total_pnl:.2f}")
    """

    def __init__(
        self,
        config: BacktestConfig,
        strategy: StrategyProtocol,
    ):
        """Initialize backtest engine.

        Args:
            config: Backtest configuration
            strategy: Trading strategy to evaluate
        """
        self.config = config
        self.strategy = strategy
        self.execution_engine = ExecutionEngine(
            maker_fee_bps=config.maker_fee_bps,
            taker_fee_bps=config.taker_fee_bps,
        )

        # State tracking
        self.bankroll = config.starting_bankroll
        self.forecasts: list[ForecastRecord] = []
        self.trades: list[TradeRecord] = []
        self.position_state = PositionState()
        self.decision_log: list[dict[str, Any]] = []
        self.position_history: list[dict[str, Any]] = []
        self.markets_seen = 0

    def run(self, snapshots: list[MarketSnapshot]) -> BacktestResult:
        """Run backtest over market snapshots.

        Iterates through each market snapshot, gets strategy decision,
        simulates execution, updates positions, and tracks metrics.

        Args:
            snapshots: List of market snapshots to backtest over

        Returns:
            BacktestResult with comprehensive metrics and trade history

        Raises:
            ValueError: If snapshots list is empty or invalid
        """
        if not snapshots:
            raise ValueError("Cannot run backtest with empty snapshots list")

        # Validate snapshots
        for i, snapshot in enumerate(snapshots):
            if not isinstance(snapshot, MarketSnapshot):
                raise ValueError(f"Snapshot {i} is not a MarketSnapshot instance")
            if not (0 <= snapshot.market_prob <= 1):
                raise ValueError(f"Snapshot {i}: market_prob must be in [0,1], got {snapshot.market_prob}")
            if not (0 <= snapshot.fair_prob <= 1):
                raise ValueError(f"Snapshot {i}: fair_prob must be in [0,1], got {snapshot.fair_prob}")
            if snapshot.outcome not in {0, 1}:
                raise ValueError(f"Snapshot {i}: outcome must be 0 or 1, got {snapshot.outcome}")

        # Reset state
        self.bankroll = self.config.starting_bankroll
        self.forecasts = []
        self.trades = []
        self.position_state = PositionState()
        self.decision_log = []
        self.position_history = []
        self.markets_seen = 0

        # Main backtest loop
        for snapshot in snapshots:
            self._process_snapshot(snapshot)

        # Compute final metrics
        metrics = evaluate_all(self.forecasts, self.trades)
        total_pnl = self.bankroll - self.config.starting_bankroll

        return BacktestResult(
            config=self.config,
            starting_bankroll=self.config.starting_bankroll,
            ending_bankroll=self.bankroll,
            total_pnl=total_pnl,
            num_markets_seen=self.markets_seen,
            num_trades=len(self.trades),
            forecasts=self.forecasts,
            trades=self.trades,
            metrics=metrics,
            position_history=self.position_history,
            decision_log=self.decision_log,
        )

    def _process_snapshot(self, snapshot: MarketSnapshot) -> None:
        """Process a single market snapshot.

        Args:
            snapshot: Market snapshot to process
        """
        self.markets_seen += 1

        # Record forecast
        forecast = ForecastRecord(
            market_id=snapshot.market_id,
            probability=snapshot.fair_prob,
            outcome=snapshot.outcome,
        )
        self.forecasts.append(forecast)

        # Check position limits
        if self.config.enable_position_tracking and self.config.max_concurrent_positions > 0:
            if self.position_state.position_count >= self.config.max_concurrent_positions:
                if self.config.enable_detailed_logging:
                    self.decision_log.append({
                        "market_id": snapshot.market_id,
                        "timestamp": snapshot.timestamp,
                        "action": "skip",
                        "reason": "max_concurrent_positions_reached",
                        "position_count": self.position_state.position_count,
                    })
                return

        # Create market state for strategy
        market_state = MarketState(
            market_id=snapshot.market_id,
            market_prob=snapshot.market_prob,
            fair_prob=snapshot.fair_prob,
            time_to_expiry_hours=snapshot.time_to_expiry_hours,
            order_book=snapshot.order_book.clone(),  # Clone to prevent mutation
            metadata=snapshot.metadata,
        )

        # Get strategy decision
        try:
            proposal = self.strategy.evaluate_market(market_state, self.bankroll)
        except Exception as e:
            if self.config.enable_detailed_logging:
                self.decision_log.append({
                    "market_id": snapshot.market_id,
                    "timestamp": snapshot.timestamp,
                    "action": "error",
                    "error": str(e),
                })
            return

        if proposal is None:
            if self.config.enable_detailed_logging:
                self.decision_log.append({
                    "market_id": snapshot.market_id,
                    "timestamp": snapshot.timestamp,
                    "action": "skip",
                    "reason": "no_proposal",
                })
            return

        # Log decision
        if self.config.enable_detailed_logging:
            self.decision_log.append({
                "market_id": snapshot.market_id,
                "timestamp": snapshot.timestamp,
                "action": "trade",
                "proposal": {
                    "side": proposal.side,
                    "order_type": proposal.order_type,
                    "size": proposal.size,
                    "limit_price": proposal.limit_price,
                    "rationale": proposal.rationale,
                },
                "bankroll": self.bankroll,
            })

        # Execute order(s)
        order_sizes = proposal.split_sizes or [proposal.size]
        for order_size in order_sizes:
            self._execute_order(proposal, order_size, snapshot)

        # Track position state
        if self.config.enable_position_tracking:
            self.position_history.append({
                "timestamp": snapshot.timestamp,
                "bankroll": self.bankroll,
                "position_count": self.position_state.position_count,
                "total_exposure": self.position_state.total_exposure,
            })

    def _execute_order(
        self,
        proposal: ProposedOrder,
        size: float,
        snapshot: MarketSnapshot,
    ) -> None:
        """Execute a single order and update state.

        Args:
            proposal: Order proposal from strategy
            size: Size of this order (may be split)
            snapshot: Current market snapshot
        """
        # Clone order book to prevent mutation
        order_book = snapshot.order_book.clone()

        # Execute based on order type
        if proposal.order_type == "market":
            report = self.execution_engine.execute_market_order(
                size=size,
                side=proposal.side,
                order_book=order_book,
            )
        else:  # limit order
            limit_price = proposal.limit_price or order_book.get_mid_price()
            report = self.execution_engine.execute_limit_order(
                price=limit_price,
                size=size,
                side=proposal.side,
                order_book=order_book,
                time_in_force="GTC",
            )

        # Skip if nothing filled
        if report.filled_size <= 0 or report.average_fill_price is None:
            return

        # Calculate PnL
        pnl = self._calculate_pnl(
            side=proposal.side,
            fill_price=report.average_fill_price,
            outcome=snapshot.outcome,
            filled_size=report.filled_size,
        )

        # Update bankroll
        self.bankroll += pnl

        # Update position tracking
        if self.config.enable_position_tracking:
            self.position_state.add_position(
                market_id=snapshot.market_id,
                size=report.filled_size,
                price=report.average_fill_price,
            )

        # Record trade
        trade = TradeRecord(
            market_id=snapshot.market_id,
            side=proposal.side,
            order_type=proposal.order_type,
            requested_size=report.requested_size,
            filled_size=report.filled_size,
            fill_price=report.average_fill_price,
            mid_at_decision=report.reference_mid_price,
            next_mid_price=snapshot.next_mid_price or report.reference_mid_price,
            outcome=snapshot.outcome,
            pnl=pnl,
            slippage_bps=report.slippage_bps,
            market_impact_bps=report.market_impact_bps,
            implementation_shortfall_bps=report.implementation_shortfall_bps,
            fill_rate=report.fill_rate,
        )
        self.trades.append(trade)

    @staticmethod
    def _calculate_pnl(side: str, fill_price: float, outcome: int, filled_size: float) -> float:
        """Calculate realized PnL for a trade.

        Args:
            side: "buy" or "sell"
            fill_price: Execution price
            outcome: Market outcome (0 or 1)
            filled_size: Size of position

        Returns:
            Realized PnL
        """
        if side == "buy":
            return (float(outcome) - fill_price) * filled_size
        else:  # sell
            return (fill_price - float(outcome)) * filled_size


def load_snapshots_from_json(path: str | Path) -> list[MarketSnapshot]:
    """Load market snapshots from JSON file.

    Expected JSON format:
    [
        {
            "market_id": "politics-2025-03",
            "timestamp": 1234567890.0,
            "market_prob": 0.45,
            "fair_prob": 0.55,
            "time_to_expiry_hours": 24.0,
            "order_book": {
                "bids": [[0.44, 100], [0.43, 50]],
                "asks": [[0.46, 75], [0.47, 25]]
            },
            "outcome": 1,
            "next_mid_price": 0.46,
            "metadata": {"category": "politics"}
        },
        ...
    ]

    Args:
        path: Path to JSON file

    Returns:
        List of MarketSnapshot objects

    Raises:
        ValueError: If JSON format is invalid
        FileNotFoundError: If file doesn't exist
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Expected JSON array of market snapshots")

    snapshots = []
    for i, record in enumerate(data):
        if not isinstance(record, dict):
            raise ValueError(f"Snapshot {i} must be a JSON object")

        # Required fields
        required = ["market_id", "market_prob", "fair_prob", "order_book", "outcome"]
        for field in required:
            if field not in record:
                raise ValueError(f"Snapshot {i} missing required field: {field}")

        # Build order book
        order_book_data = record["order_book"]
        order_book = OrderBook(
            market_id=str(record["market_id"]),
            bids=[
                BookLevel(price=float(price), size=float(size))
                for price, size in order_book_data.get("bids", [])
            ],
            asks=[
                BookLevel(price=float(price), size=float(size))
                for price, size in order_book_data.get("asks", [])
            ],
        )

        # Create snapshot
        snapshot = MarketSnapshot(
            market_id=str(record["market_id"]),
            timestamp=float(record.get("timestamp", i)),
            market_prob=float(record["market_prob"]),
            fair_prob=float(record["fair_prob"]),
            time_to_expiry_hours=float(record.get("time_to_expiry_hours", 24.0)),
            order_book=order_book,
            outcome=int(record["outcome"]),
            next_mid_price=float(record["next_mid_price"]) if "next_mid_price" in record else None,
            metadata=record.get("metadata", {}),
        )
        snapshots.append(snapshot)

    return snapshots
