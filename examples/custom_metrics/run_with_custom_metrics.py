"""Run backtest with custom metrics included."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from autopredict.run_experiment import run_backtest
from autopredict.market_env import evaluate_all, ForecastRecord, TradeRecord
from examples.custom_metrics.custom_metrics import calculate_all_custom_metrics


def run_with_custom_metrics():
    """Run backtest and add custom metrics to output."""

    # Paths
    config_path = Path(__file__).parent.parent.parent / "strategy_configs" / "baseline.json"
    dataset_path = Path(__file__).parent.parent.parent / "datasets" / "markets.json"
    guidance_path = Path(__file__).parent.parent.parent / "strategy.md"

    print("="*80)
    print("BACKTEST WITH CUSTOM METRICS")
    print("="*80)

    # We need to capture trades to calculate custom metrics
    # Easiest way: run backtest, then recalculate with custom metrics
    # (In production, you'd modify run_experiment.py to track trades)

    # For demo, we'll patch evaluate_all temporarily
    original_evaluate_all = evaluate_all

    captured_trades = []

    def patched_evaluate_all(forecasts: list[ForecastRecord], trades: list[TradeRecord]):
        """Wrapper that adds custom metrics."""
        nonlocal captured_trades
        captured_trades = trades

        # Get standard metrics
        metrics = original_evaluate_all(forecasts, trades)

        # Add custom metrics
        custom = calculate_all_custom_metrics(trades)
        metrics.update(custom)

        return metrics

    # Monkey-patch temporarily
    import autopredict.market_env
    autopredict.market_env.evaluate_all = patched_evaluate_all

    # Run backtest
    metrics = run_backtest(
        config_path=config_path,
        dataset_path=dataset_path,
        strategy_guidance_path=guidance_path,
        starting_bankroll=1000.0,
    )

    # Restore original
    autopredict.market_env.evaluate_all = original_evaluate_all

    print("\nSTANDARD METRICS:")
    print(f"  Total PnL: ${metrics['total_pnl']:.2f}")
    print(f"  Sharpe: {metrics['sharpe']:.2f}")
    print(f"  Win Rate: {metrics['win_rate']:.1%}")
    print(f"  Max Drawdown: ${metrics['max_drawdown']:.2f}")
    print(f"  Num Trades: {int(metrics['num_trades'])}")

    print("\n" + "="*80)
    print("CUSTOM METRICS:")
    print("="*80)

    print(f"\nProfit Factor: {metrics['profit_factor']:.2f}")
    if metrics['profit_factor'] > 1.0:
        print("  ✓ Winners are bigger than losers")
    else:
        print("  ✗ Losers are bigger than winners")

    print(f"\nConsecutive Wins: {int(metrics['max_consecutive_wins'])}")
    print(f"Consecutive Losses: {int(metrics['max_consecutive_losses'])}")
    print(f"Current Streak: {int(metrics['current_streak'])}")
    if metrics['current_streak'] > 0:
        print(f"  ✓ Currently on {int(metrics['current_streak'])} win streak")
    elif metrics['current_streak'] < 0:
        print(f"  ✗ Currently on {abs(int(metrics['current_streak']))} loss streak")
    else:
        print("  - No active streak")

    print(f"\nAverage Win: ${metrics['avg_win_size']:.2f}")
    print(f"Average Loss: ${metrics['avg_loss_size']:.2f}")
    print(f"Win/Loss Ratio: {metrics['win_loss_ratio']:.2f}")
    if metrics['win_loss_ratio'] > 1.0:
        print("  ✓ Average win is bigger than average loss")
    else:
        print("  ✗ Average loss is bigger than average win")

    print("\n" + "="*80)
    print("INTERPRETATION")
    print("="*80)

    print("\nCustom metrics provide deeper insight into trading patterns:")
    print("  - Profit factor shows overall quality of win/loss distribution")
    print("  - Consecutive metrics reveal volatility and risk of streaks")
    print("  - Win/loss sizes show if you're sizing positions correctly")

    print("\nFor this backtest:")
    if metrics['profit_factor'] > 2.0:
        print("  ✓ Excellent profit factor (>2.0)")
    elif metrics['profit_factor'] > 1.5:
        print("  ✓ Good profit factor (1.5-2.0)")
    elif metrics['profit_factor'] > 1.0:
        print("  ⚠ Acceptable profit factor (1.0-1.5)")
    else:
        print("  ✗ Poor profit factor (<1.0) - need better edge or sizing")

    print("\n" + "="*80)
    print("FULL METRICS (JSON)")
    print("="*80)
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    run_with_custom_metrics()
