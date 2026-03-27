#!/usr/bin/env python3
"""Main learning and improvement workflow for AutoPredict.

This script orchestrates the complete self-improvement loop:
1. Load recent trade logs
2. Analyze performance and identify failure regimes
3. Propose parameter improvements via grid search
4. Validate improvements on holdout data
5. Save improved configuration if better than current
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autopredict.learning.logger import TradeLogger
from autopredict.learning.analyzer import PerformanceAnalyzer
from autopredict.learning.tuner import (
    GridSearchTuner,
    ParameterGrid,
    BacktestResult,
    create_param_grid_from_current,
)


def load_config(config_path: Path) -> dict:
    """Load strategy configuration from JSON file."""
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config_path: Path, config: dict) -> None:
    """Save strategy configuration to JSON file."""
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Configuration saved to {config_path}")


def analyze_performance(args: argparse.Namespace) -> None:
    """Analyze recent trading performance and generate report.

    Args:
        args: Command-line arguments with log_dir and output options
    """
    log_dir = Path(args.log_dir)
    logger = TradeLogger(log_dir)

    # Load logs
    if args.days:
        logs = logger.load_recent(days=args.days)
        print(f"Loaded {len(logs)} trade logs from last {args.days} days")
    else:
        logs = logger.load_all()
        print(f"Loaded {len(logs)} total trade logs")

    if not logs:
        print("No trade logs found. Run some backtests first!")
        return

    # Generate analysis
    analyzer = PerformanceAnalyzer(logs)
    report = analyzer.generate_report()

    # Print summary
    print("\n" + "=" * 60)
    print("PERFORMANCE ANALYSIS")
    print("=" * 60)
    print(f"Total trades: {report.total_trades}")
    print(f"Total PnL: ${report.total_pnl:.2f}")
    print(f"Win rate: {report.win_rate:.2%}")
    print(f"Avg win: ${report.avg_win:.2f}")
    print(f"Avg loss: ${report.avg_loss:.2f}")
    print(f"Sharpe ratio: {report.sharpe_ratio:.3f}" if report.sharpe_ratio else "Sharpe ratio: N/A")
    print(f"Calibration error: {report.calibration_error:.3f}")
    print(f"Edge capture rate: {report.edge_capture_rate:.2%}")

    print("\nDecision breakdown:")
    for decision, count in report.by_decision.items():
        print(f"  {decision}: {count}")

    if report.failure_regimes:
        print("\nFailure regimes identified:")
        for regime in report.failure_regimes:
            print(f"  - {regime}")

    if report.recommendations:
        print("\nRecommendations:")
        for rec in report.recommendations:
            print(f"  - {rec}")

    print("\nPerformance by category:")
    for category, stats in report.by_category.items():
        print(f"  {category}: {stats['trades']} trades, "
              f"${stats['pnl']:.2f} PnL, "
              f"{stats['win_rate']:.1%} win rate")

    # Save full report if requested
    if args.output:
        output_path = Path(args.output)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\nFull report saved to {output_path}")


def tune_parameters(args: argparse.Namespace) -> None:
    """Tune strategy parameters via grid search over historical data.

    Args:
        args: Command-line arguments with config, grid, and output options
    """
    # Load current config
    config_path = Path(args.config)
    current_config = load_config(config_path)
    print(f"Loaded current config from {config_path}")
    print(f"Current params: {json.dumps(current_config, indent=2)}")

    # Define parameter grid
    if args.grid_config:
        # Load custom grid from JSON file
        with Path(args.grid_config).open("r", encoding="utf-8") as f:
            grid_spec = json.load(f)
        param_grid = ParameterGrid(grid_spec)
        print(f"Using custom parameter grid from {args.grid_config}")
    else:
        # Create grid around current parameters
        param_grid = create_param_grid_from_current(
            current_config,
            perturbation_factor=args.perturbation,
            n_steps=args.steps,
        )
        print(f"Created parameter grid with ±{args.perturbation*100:.0f}% perturbation, "
              f"{args.steps} steps")

    print(f"Grid size: {len(param_grid)} configurations to test")

    # Define backtest function (placeholder - needs actual implementation)
    def backtest_with_params(params: dict) -> BacktestResult:
        """Run backtest with given parameters.

        This is a placeholder. In production, this would:
        1. Create strategy config with params
        2. Run backtest on validation dataset
        3. Collect metrics and return BacktestResult
        """
        # TODO: Import and call actual backtest engine
        # from autopredict.backtest import BacktestEngine
        # engine = BacktestEngine(...)
        # result = engine.run(params)

        print(f"    [Placeholder] Would run backtest with: {params}")

        # Placeholder: return dummy result
        return BacktestResult(
            params=params,
            total_pnl=10.0,  # Dummy value
            sharpe_ratio=0.5,  # Dummy value
            win_rate=0.55,  # Dummy value
            total_trades=20,  # Dummy value
            calibration_error=0.08,  # Dummy value
            edge_capture_rate=0.6,  # Dummy value
        )

    # Run grid search
    tuner = GridSearchTuner(
        param_grid=param_grid,
        backtest_fn=backtest_with_params,
        verbose=True,
    )

    best_params, best_result = tuner.tune()

    print("\n" + "=" * 60)
    print("TUNING RESULTS")
    print("=" * 60)
    print(f"Best parameters: {json.dumps(best_params, indent=2)}")
    print(f"Best score: {best_result.score():.4f}")
    print(f"Total PnL: ${best_result.total_pnl:.2f}")
    print(f"Sharpe ratio: {best_result.sharpe_ratio:.3f}" if best_result.sharpe_ratio else "Sharpe: N/A")
    print(f"Win rate: {best_result.win_rate:.2%}")
    print(f"Total trades: {best_result.total_trades}")

    # Show improvement over current
    print("\nTop 5 configurations:")
    for i, (params, result) in enumerate(tuner.get_top_n(5), 1):
        print(f"{i}. Score: {result.score():.4f}, PnL: ${result.total_pnl:.2f}, "
              f"Sharpe: {result.sharpe_ratio:.3f if result.sharpe_ratio else 'N/A'}")
        print(f"   Params: {params}")

    # Save results
    if args.output:
        output_path = Path(args.output)
        save_config(output_path, best_params)

        # Also save full tuning results
        results_path = output_path.with_suffix('.results.json')
        tuner.save_results(results_path)


def improve_strategy(args: argparse.Namespace) -> None:
    """Run complete improvement loop: analyze + tune + validate.

    Args:
        args: Command-line arguments with all options
    """
    print("=" * 60)
    print("SELF-IMPROVEMENT LOOP")
    print("=" * 60)

    # Step 1: Analyze recent performance
    print("\nStep 1: Analyzing recent performance...")
    log_dir = Path(args.log_dir)
    logger = TradeLogger(log_dir)
    logs = logger.load_recent(days=args.days)

    if not logs:
        print("No recent trade logs found. Cannot proceed with improvement.")
        return

    analyzer = PerformanceAnalyzer(logs)
    report = analyzer.generate_report()

    print(f"Recent performance: ${report.total_pnl:.2f} PnL, "
          f"{report.win_rate:.1%} win rate, "
          f"{report.total_trades} trades")

    if report.failure_regimes:
        print("\nIdentified failure regimes:")
        for regime in report.failure_regimes:
            print(f"  - {regime}")

    # Step 2: Load current config
    print("\nStep 2: Loading current strategy configuration...")
    config_path = Path(args.config)
    current_config = load_config(config_path)
    current_sharpe = report.sharpe_ratio or 0.0

    print(f"Current Sharpe ratio: {current_sharpe:.3f}")

    # Step 3: Propose improvements
    print("\nStep 3: Tuning parameters via grid search...")

    # Create focused grid based on recommendations
    param_grid = create_param_grid_from_current(
        current_config,
        perturbation_factor=args.perturbation,
        n_steps=args.steps,
    )

    def backtest_with_params(params: dict) -> BacktestResult:
        # Placeholder - needs actual backtest implementation
        print(f"    [Placeholder] Testing: {params}")
        return BacktestResult(
            params=params,
            total_pnl=10.0,
            sharpe_ratio=0.5,
            win_rate=0.55,
            total_trades=20,
            calibration_error=0.08,
            edge_capture_rate=0.6,
        )

    tuner = GridSearchTuner(param_grid, backtest_with_params, verbose=False)
    best_params, best_result = tuner.tune()

    print(f"Best configuration found: {best_params}")
    print(f"Expected Sharpe: {best_result.sharpe_ratio:.3f}" if best_result.sharpe_ratio else "Expected Sharpe: N/A")

    # Step 4: Validate improvement
    print("\nStep 4: Validating improvement...")
    improvement = (best_result.sharpe_ratio or 0.0) - current_sharpe

    if improvement > args.min_improvement:
        print(f"Improvement detected: +{improvement:.3f} Sharpe")

        # Step 5: Save improved config
        if args.auto_save:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            improved_path = config_path.parent / f"strategy_improved_{timestamp}.json"
            save_config(improved_path, best_params)
            print(f"Improved configuration saved to {improved_path}")
            print(f"To use: mv {improved_path} {config_path}")
        else:
            print("Auto-save disabled. To save improved config, use --auto-save")
    else:
        print(f"No significant improvement found (change: {improvement:.3f}, "
              f"threshold: {args.min_improvement})")
        print("Current configuration is already well-tuned.")


def main():
    parser = argparse.ArgumentParser(
        description="AutoPredict self-improvement and learning tools"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Analyze command
    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze recent trading performance"
    )
    analyze.add_argument(
        "--log-dir",
        default="state/trades",
        help="Directory containing trade log JSONL files"
    )
    analyze.add_argument(
        "--days",
        type=int,
        help="Only analyze last N days (default: all logs)"
    )
    analyze.add_argument(
        "--output",
        help="Save full report to JSON file"
    )
    analyze.set_defaults(func=analyze_performance)

    # Tune command
    tune = subparsers.add_parser(
        "tune",
        help="Tune strategy parameters via grid search"
    )
    tune.add_argument(
        "--config",
        required=True,
        help="Current strategy config JSON file"
    )
    tune.add_argument(
        "--grid-config",
        help="Custom parameter grid JSON file (optional)"
    )
    tune.add_argument(
        "--perturbation",
        type=float,
        default=0.2,
        help="Perturbation factor for auto grid (default: 0.2 = ±20%%)"
    )
    tune.add_argument(
        "--steps",
        type=int,
        default=3,
        help="Number of steps in auto grid (default: 3)"
    )
    tune.add_argument(
        "--output",
        help="Save best config to this file"
    )
    tune.set_defaults(func=tune_parameters)

    # Improve command (full loop)
    improve = subparsers.add_parser(
        "improve",
        help="Run full improvement loop (analyze + tune + validate)"
    )
    improve.add_argument(
        "--config",
        required=True,
        help="Current strategy config JSON file"
    )
    improve.add_argument(
        "--log-dir",
        default="state/trades",
        help="Directory containing trade logs"
    )
    improve.add_argument(
        "--days",
        type=int,
        default=30,
        help="Days of history to analyze (default: 30)"
    )
    improve.add_argument(
        "--perturbation",
        type=float,
        default=0.2,
        help="Parameter perturbation factor (default: 0.2)"
    )
    improve.add_argument(
        "--steps",
        type=int,
        default=3,
        help="Grid search steps (default: 3)"
    )
    improve.add_argument(
        "--min-improvement",
        type=float,
        default=0.05,
        help="Minimum Sharpe improvement to save new config (default: 0.05)"
    )
    improve.add_argument(
        "--auto-save",
        action="store_true",
        help="Automatically save improved config if better"
    )
    improve.set_defaults(func=improve_strategy)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
