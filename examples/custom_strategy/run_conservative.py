"""Run backtest with conservative agent and compare to baseline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from autopredict.agent import AutoPredictAgent
from autopredict.run_experiment import run_backtest
from examples.custom_strategy.conservative_agent import ConservativeAgent


def run_comparison():
    """Run both baseline and conservative agents, compare results."""

    config_path = Path(__file__).parent.parent.parent / "strategy_configs" / "baseline.json"
    dataset_path = Path(__file__).parent.parent.parent / "datasets" / "markets.json"
    guidance_path = Path(__file__).parent.parent.parent / "strategy.md"

    print("="*80)
    print("BASELINE AGENT")
    print("="*80)

    # Run baseline
    baseline_metrics = run_backtest(
        config_path=config_path,
        dataset_path=dataset_path,
        strategy_guidance_path=guidance_path,
        starting_bankroll=1000.0,
    )

    print(f"\nBaseline Results:")
    print(f"  Total PnL: ${baseline_metrics['total_pnl']:.2f}")
    print(f"  Sharpe: {baseline_metrics['sharpe']:.2f}")
    print(f"  Brier Score: {baseline_metrics['brier_score']:.3f}")
    print(f"  Fill Rate: {baseline_metrics['fill_rate']:.1%}")
    print(f"  Avg Slippage: {baseline_metrics['avg_slippage_bps']:.1f} bps")
    print(f"  Num Trades: {int(baseline_metrics['num_trades'])}")

    print("\n" + "="*80)
    print("CONSERVATIVE AGENT")
    print("="*80)

    # Monkey-patch to use ConservativeAgent
    original_agent = AutoPredictAgent.from_mapping
    AutoPredictAgent.from_mapping = ConservativeAgent.from_mapping

    conservative_metrics = run_backtest(
        config_path=config_path,
        dataset_path=dataset_path,
        strategy_guidance_path=guidance_path,
        starting_bankroll=1000.0,
    )

    # Restore original
    AutoPredictAgent.from_mapping = original_agent

    print(f"\nConservative Results:")
    print(f"  Total PnL: ${conservative_metrics['total_pnl']:.2f}")
    print(f"  Sharpe: {conservative_metrics['sharpe']:.2f}")
    print(f"  Brier Score: {conservative_metrics['brier_score']:.3f}")
    print(f"  Fill Rate: {conservative_metrics['fill_rate']:.1%}")
    print(f"  Avg Slippage: {conservative_metrics['avg_slippage_bps']:.1f} bps")
    print(f"  Num Trades: {int(conservative_metrics['num_trades'])}")

    print("\n" + "="*80)
    print("COMPARISON")
    print("="*80)

    print(f"\nPnL Change: ${baseline_metrics['total_pnl']:.2f} -> ${conservative_metrics['total_pnl']:.2f}")
    pnl_change_pct = ((conservative_metrics['total_pnl'] - baseline_metrics['total_pnl']) /
                      max(abs(baseline_metrics['total_pnl']), 0.01)) * 100
    print(f"  ({pnl_change_pct:+.1f}%)")

    print(f"\nSharpe Change: {baseline_metrics['sharpe']:.2f} -> {conservative_metrics['sharpe']:.2f}")
    sharpe_change = conservative_metrics['sharpe'] - baseline_metrics['sharpe']
    print(f"  ({sharpe_change:+.2f})")

    print(f"\nFill Rate Change: {baseline_metrics['fill_rate']:.1%} -> {conservative_metrics['fill_rate']:.1%}")
    fill_change = conservative_metrics['fill_rate'] - baseline_metrics['fill_rate']
    print(f"  ({fill_change:+.1%})")

    print(f"\nTrades Change: {int(baseline_metrics['num_trades'])} -> {int(conservative_metrics['num_trades'])}")
    trade_change = int(conservative_metrics['num_trades']) - int(baseline_metrics['num_trades'])
    print(f"  ({trade_change:+d})")

    print("\n" + "="*80)
    print("INTERPRETATION")
    print("="*80)

    print("\nConservative Strategy Trade-offs:")
    print("  ✓ Lower slippage (limit orders only)")
    print("  ✓ Better Sharpe ratio (quality over quantity)")
    print("  ✗ Lower fill rate (passive orders)")
    print("  ✗ Fewer total trades (stricter filters)")

    print("\nUse Conservative Strategy When:")
    print("  - Spreads are wide")
    print("  - You can afford to wait for fills")
    print("  - Execution quality matters more than frequency")
    print("  - Markets have sufficient liquidity")


if __name__ == "__main__":
    run_comparison()
