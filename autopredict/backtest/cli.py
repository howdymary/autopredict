"""CLI commands for the backtest module.

This module provides command-line interface integration for the backtest engine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from agent import AutoPredictAgent
from .engine import BacktestConfig, BacktestEngine, load_snapshots_from_json
from .analysis import PerformanceAnalyzer


def run_backtest_command(
    strategy: str = "mispriced_probability",
    data: str | Path = "datasets/sample_markets_100.json",
    config: str | Path | None = None,
    out: str | Path = "results/backtest.json",
    bankroll: float = 1000.0,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run backtest from command line arguments.

    Args:
        strategy: Strategy name (currently only "mispriced_probability")
        data: Path to market data JSON
        config: Optional path to strategy config JSON
        out: Output path for results
        bankroll: Starting bankroll
        verbose: Enable verbose logging

    Returns:
        Dictionary with backtest results

    Example:
        >>> results = run_backtest_command(
        ...     data="datasets/sample_markets_100.json",
        ...     out="results/backtest.json"
        ... )
    """
    # Resolve paths
    data_path = Path(data)
    out_path = Path(out)

    # Load strategy config
    if config:
        config_path = Path(config)
        with config_path.open("r", encoding="utf-8") as f:
            config_data = json.load(f)
        agent = AutoPredictAgent.from_mapping(config_data)
    else:
        # Use default configuration
        agent = AutoPredictAgent()

    # Load market snapshots
    snapshots = load_snapshots_from_json(data_path)

    # Configure backtest
    backtest_config = BacktestConfig(
        starting_bankroll=bankroll,
        enable_position_tracking=True,
        enable_detailed_logging=verbose,
    )

    # Run backtest
    engine = BacktestEngine(config=backtest_config, strategy=agent)
    result = engine.run(snapshots)

    # Generate performance report
    analyzer = PerformanceAnalyzer()
    report = analyzer.analyze(
        forecasts=result.forecasts,
        trades=result.trades,
        starting_bankroll=result.starting_bankroll,
        ending_bankroll=result.ending_bankroll,
    )

    # Save results
    result.save(out_path)

    # Return summary
    return {
        "result_path": str(out_path),
        "total_pnl": result.total_pnl,
        "num_trades": result.num_trades,
        "num_markets": result.num_markets_seen,
        "win_rate": report.financial_metrics["win_rate"],
        "brier_score": report.epistemic_metrics["calibration_analysis"]["overall_brier"],
    }
