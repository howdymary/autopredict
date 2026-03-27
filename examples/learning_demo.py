#!/usr/bin/env python3
"""Demo script showing the self-improvement learning loop.

This example demonstrates:
1. Creating synthetic trade logs
2. Analyzing performance
3. Identifying failure regimes
4. Parameter tuning with grid search
5. Validating improvements
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import random

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autopredict.learning.logger import TradeLog, TradeLogger
from autopredict.learning.analyzer import PerformanceAnalyzer
from autopredict.learning.tuner import (
    GridSearchTuner,
    ParameterGrid,
    BacktestResult,
    create_param_grid_from_current,
)


def generate_synthetic_logs(n_logs: int = 100) -> list[TradeLog]:
    """Generate synthetic trade logs for demonstration.

    Creates logs with various market conditions and outcomes.
    """
    logs = []
    categories = ["politics", "sports", "economics", "tech"]
    base_time = datetime.now(timezone.utc) - timedelta(days=30)

    for i in range(n_logs):
        # Random market characteristics
        category = random.choice(categories)
        market_prob = random.uniform(0.2, 0.8)
        model_prob = market_prob + random.gauss(0, 0.15)  # Model with some noise
        model_prob = max(0.01, min(0.99, model_prob))  # Clamp to valid range

        edge = abs(model_prob - market_prob)
        decision = "pass"
        size = 0.0
        execution_price = None
        outcome = None
        pnl = None

        # Decide whether to trade
        if edge > 0.05:  # min_edge threshold
            decision = "buy" if model_prob > market_prob else "sell"
            size = min(20.0, edge * 200)  # Size based on edge

            # Simulate execution
            spread_pct = random.uniform(0.01, 0.08)
            execution_price = market_prob + spread_pct / 2 if decision == "buy" else market_prob - spread_pct / 2

            # Simulate outcome (model is right 60% of time)
            is_correct = random.random() < 0.60
            if decision == "buy":
                outcome = 1 if is_correct else 0
            else:
                outcome = 0 if is_correct else 1

            # Calculate PnL
            if decision == "buy":
                pnl = size * (outcome - execution_price)
            else:
                pnl = size * (execution_price - outcome)

        # Create log
        log = TradeLog(
            timestamp=base_time + timedelta(hours=i * 7),  # Spread over 30 days
            market_id=f"{category}-market-{i % 20}",
            market_prob=market_prob,
            model_prob=model_prob,
            edge=edge,
            decision=decision,
            size=size,
            execution_price=execution_price,
            outcome=outcome,
            pnl=pnl,
            rationale={
                "category": category,
                "order_type": "limit" if edge < 0.12 else "market",
                "spread_pct": random.uniform(0.01, 0.08),
                "liquidity_depth": random.uniform(50, 300),
                "time_to_expiry_hours": random.uniform(6, 168),
            }
        )
        logs.append(log)

    return logs


def demo_logging():
    """Demonstrate trade logging."""
    print("=" * 60)
    print("DEMO: Trade Logging")
    print("=" * 60)

    # Create temp directory for demo
    log_dir = Path("demo_logs")
    log_dir.mkdir(exist_ok=True)

    logger = TradeLogger(log_dir)

    # Generate and log synthetic trades
    print("\nGenerating 100 synthetic trade logs...")
    logs = generate_synthetic_logs(100)

    print(f"Logging {len(logs)} trades...")
    logger.append_batch(logs)

    print(f"Logs saved to {log_dir}/")
    print(f"Created {len(list(log_dir.glob('*.jsonl')))} daily log files")

    # Load back and verify
    loaded_logs = logger.load_all()
    print(f"Successfully loaded {len(loaded_logs)} logs")

    return log_dir


def demo_analysis(log_dir: Path):
    """Demonstrate performance analysis."""
    print("\n" + "=" * 60)
    print("DEMO: Performance Analysis")
    print("=" * 60)

    logger = TradeLogger(log_dir)
    logs = logger.load_all()

    analyzer = PerformanceAnalyzer(logs)
    report = analyzer.generate_report()

    # Print summary
    print(f"\nTotal trades: {report.total_trades}")
    print(f"Total PnL: ${report.total_pnl:.2f}")
    print(f"Win rate: {report.win_rate:.2%}")
    print(f"Avg win: ${report.avg_win:.2f}")
    print(f"Avg loss: ${report.avg_loss:.2f}")
    if report.sharpe_ratio is not None:
        print(f"Sharpe ratio: {report.sharpe_ratio:.3f}")
    print(f"Calibration error: {report.calibration_error:.3f}")
    print(f"Edge capture rate: {report.edge_capture_rate:.2%}")

    print("\nDecision breakdown:")
    for decision, count in report.by_decision.items():
        print(f"  {decision}: {count}")

    print("\nPerformance by category:")
    for category, stats in report.by_category.items():
        print(f"  {category}:")
        print(f"    Trades: {stats['trades']}")
        print(f"    PnL: ${stats['pnl']:.2f}")
        print(f"    Win rate: {stats['win_rate']:.1%}")
        print(f"    Calibration error: {stats['calibration_error']:.3f}")

    if report.failure_regimes:
        print("\nFailure regimes identified:")
        for regime in report.failure_regimes:
            print(f"  ⚠️  {regime}")

    if report.recommendations:
        print("\nRecommendations:")
        for rec in report.recommendations:
            print(f"  💡 {rec}")


def demo_tuning():
    """Demonstrate parameter tuning."""
    print("\n" + "=" * 60)
    print("DEMO: Parameter Tuning")
    print("=" * 60)

    # Current parameters
    current_params = {
        "min_edge": 0.05,
        "aggressive_edge": 0.12,
        "max_risk_fraction": 0.02,
    }

    print(f"\nCurrent parameters:")
    for param, value in current_params.items():
        print(f"  {param}: {value}")

    # Create parameter grid
    print("\nCreating parameter grid (±20% variation, 2 steps)...")
    param_grid = create_param_grid_from_current(
        current_params,
        perturbation_factor=0.2,
        n_steps=2,
    )

    print(f"Grid size: {len(param_grid)} configurations")

    # Mock backtest function
    def mock_backtest(params: dict) -> BacktestResult:
        """Mock backtest that returns random but plausible results."""
        # Better results for params closer to optimal
        optimal = {"min_edge": 0.08, "aggressive_edge": 0.10, "max_risk_fraction": 0.015}

        # Calculate distance from optimal
        distance = sum(
            abs(params.get(k, 0) - optimal[k]) / optimal[k]
            for k in optimal.keys()
        )

        # Better score for closer to optimal
        base_sharpe = 0.8 - distance * 0.5
        noise = random.gauss(0, 0.1)
        sharpe = max(0.1, base_sharpe + noise)

        return BacktestResult(
            params=params,
            total_pnl=sharpe * 100,
            sharpe_ratio=sharpe,
            win_rate=0.50 + sharpe * 0.1,
            total_trades=random.randint(15, 30),
            calibration_error=random.uniform(0.05, 0.15),
            edge_capture_rate=0.5 + sharpe * 0.2,
        )

    # Run grid search
    print("\nRunning grid search (mock backtests)...")
    tuner = GridSearchTuner(
        param_grid=param_grid,
        backtest_fn=mock_backtest,
        verbose=False,  # Less verbose for demo
    )

    best_params, best_result = tuner.tune()

    print("\n" + "-" * 60)
    print("TUNING RESULTS")
    print("-" * 60)
    print(f"\nBest parameters:")
    for param, value in best_params.items():
        old_value = current_params.get(param, 0)
        change = ((value - old_value) / old_value * 100) if old_value else 0
        print(f"  {param}: {value:.4f} (was {old_value:.4f}, {change:+.1f}%)")

    print(f"\nBest score: {best_result.score():.4f}")
    print(f"Expected Sharpe: {best_result.sharpe_ratio:.3f}")
    print(f"Expected win rate: {best_result.win_rate:.2%}")

    print("\nTop 3 configurations:")
    for i, (params, result) in enumerate(tuner.get_top_n(3), 1):
        print(f"{i}. Score: {result.score():.4f}, Sharpe: {result.sharpe_ratio:.3f}")
        print(f"   {params}")


def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("AUTOPREDICT LEARNING SYSTEM DEMO")
    print("=" * 60)

    # Demo 1: Logging
    log_dir = demo_logging()

    # Demo 2: Analysis
    demo_analysis(log_dir)

    # Demo 3: Tuning
    demo_tuning()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print(f"\nDemo logs saved to: {log_dir.resolve()}/")
    print("To clean up: rm -rf demo_logs/")


if __name__ == "__main__":
    main()
