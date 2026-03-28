"""Example backtest using the MispricedProbability strategy.

This script demonstrates how to:
1. Load historical market data
2. Initialize a trading strategy
3. Run a backtest
4. Generate performance reports with charts
5. Save results to JSON/CSV

Usage:
    python examples/backtest_mispriced_prob.py
    python examples/backtest_mispriced_prob.py --data datasets/markets.json
    python examples/backtest_mispriced_prob.py --config configs/aggressive.json --out results/
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Direct imports from root-level modules
from agent import AutoPredictAgent, AgentConfig
from autopredict.backtest.engine import (
    BacktestConfig,
    BacktestEngine,
    load_snapshots_from_json,
)
from autopredict.backtest.analysis import PerformanceAnalyzer


def main():
    """Run example backtest with MispricedProbability strategy."""
    parser = argparse.ArgumentParser(
        description="Run backtest with MispricedProbability strategy"
    )
    parser.add_argument(
        "--data",
        type=str,
        default="datasets/markets.json",
        help="Path to market data JSON file",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to strategy config JSON (optional)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="results",
        help="Output directory for results",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=1000.0,
        help="Starting bankroll",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging",
    )
    args = parser.parse_args()

    # Resolve paths
    project_root = Path(__file__).resolve().parent.parent
    data_path = project_root / args.data
    output_dir = project_root / args.out

    print("=" * 70)
    print("PREDICTION MARKET BACKTEST - MispricedProbability Strategy")
    print("=" * 70)
    print(f"\n📁 Data: {data_path}")
    print(f"💰 Starting Bankroll: ${args.bankroll:.2f}")

    # Load market snapshots
    print("\n⏳ Loading market data...")
    try:
        snapshots = load_snapshots_from_json(data_path)
        print(f"✅ Loaded {len(snapshots)} market snapshots")
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return 1

    # Initialize strategy
    print("\n🎯 Initializing strategy...")
    if args.config:
        config_path = project_root / args.config
        with config_path.open("r") as f:
            config_data = json.load(f)
        agent = AutoPredictAgent.from_mapping(config_data)
        print(f"✅ Loaded strategy config from {config_path}")
    else:
        # Use default MispricedProbability configuration
        agent = AutoPredictAgent(
            config=AgentConfig(
                min_edge=0.05,
                aggressive_edge=0.12,
                max_risk_fraction=0.02,
                max_position_notional=25.0,
                min_book_liquidity=60.0,
                max_spread_pct=0.04,
                max_depth_fraction=0.15,
            )
        )
        print("✅ Using default MispricedProbability configuration")
        print("   - min_edge: 0.05 (5%)")
        print("   - aggressive_edge: 0.12 (12%)")
        print("   - max_risk_fraction: 0.02 (2%)")
        print("   - max_position_notional: $25.00")

    # Configure backtest
    backtest_config = BacktestConfig(
        starting_bankroll=args.bankroll,
        maker_fee_bps=0.0,
        taker_fee_bps=0.0,
        enable_position_tracking=True,
        enable_detailed_logging=args.verbose,
    )

    # Run backtest
    print("\n🚀 Running backtest...")
    engine = BacktestEngine(config=backtest_config, strategy=agent)

    try:
        result = engine.run(snapshots)
        print(f"✅ Backtest complete!")
        print(f"   - Markets seen: {result.num_markets_seen}")
        print(f"   - Trades executed: {result.num_trades}")
        print(f"   - Forecasts made: {len(result.forecasts)}")
    except Exception as e:
        print(f"❌ Error during backtest: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Generate performance report
    print("\n📊 Generating performance report...")
    analyzer = PerformanceAnalyzer()
    report = analyzer.analyze(
        forecasts=result.forecasts,
        trades=result.trades,
        starting_bankroll=result.starting_bankroll,
        ending_bankroll=result.ending_bankroll,
    )

    # Print summary to console
    report.print_summary()

    # Save results
    print(f"\n💾 Saving results to {output_dir}/...")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save backtest result
    result_path = output_dir / "backtest_result.json"
    result.save(result_path)
    print(f"✅ Saved backtest result: {result_path}")

    # Save performance report
    report_path = output_dir / "performance_report.json"
    report.save(report_path)
    print(f"✅ Saved performance report: {report_path}")

    # Save trades to CSV-friendly format
    if result.trades:
        trades_csv_path = output_dir / "trades.csv"
        with trades_csv_path.open("w") as f:
            # CSV header
            f.write(
                "market_id,side,order_type,requested_size,filled_size,fill_price,"
                "mid_at_decision,outcome,pnl,slippage_bps,fill_rate\n"
            )
            # CSV rows
            for trade in result.trades:
                f.write(
                    f"{trade.market_id},{trade.side},{trade.order_type},"
                    f"{trade.requested_size:.4f},{trade.filled_size:.4f},"
                    f"{trade.fill_price:.4f},{trade.mid_at_decision:.4f},"
                    f"{trade.outcome},{trade.pnl:.4f},{trade.slippage_bps:.2f},"
                    f"{trade.fill_rate:.4f}\n"
                )
        print(f"✅ Saved trades CSV: {trades_csv_path}")

    # Print key insights
    print("\n💡 KEY INSIGHTS")
    print("-" * 70)

    if result.total_pnl > 0:
        print(f"✅ Strategy was PROFITABLE: ${result.total_pnl:.2f}")
        roi = (result.total_pnl / result.starting_bankroll) * 100
        print(f"   ROI: {roi:.2f}%")
    else:
        print(f"❌ Strategy was UNPROFITABLE: ${result.total_pnl:.2f}")

    if result.trades:
        win_rate = report.financial_metrics["win_rate"]
        print(f"\n🎯 Win Rate: {win_rate:.2%}")

        if win_rate > 0.55:
            print("   ✅ Strong win rate!")
        elif win_rate > 0.50:
            print("   ✔️  Positive win rate")
        else:
            print("   ⚠️  Win rate below 50%")

        # Calibration quality
        cal = report.epistemic_metrics["calibration_analysis"]
        brier = cal["overall_brier"]
        print(f"\n📐 Brier Score: {brier:.4f}")
        if brier < 0.15:
            print("   ✅ Well calibrated!")
        elif brier < 0.20:
            print("   ✔️  Reasonable calibration")
        else:
            print("   ⚠️  Poor calibration - forecasts need improvement")

        # Execution quality
        avg_slippage = report.execution_metrics["avg_slippage_bps"]
        print(f"\n⚡ Avg Slippage: {avg_slippage:.2f} bps")
        if avg_slippage < 10:
            print("   ✅ Excellent execution quality!")
        elif avg_slippage < 20:
            print("   ✔️  Good execution quality")
        else:
            print("   ⚠️  High slippage - consider more limit orders")

    # Recommendations
    print("\n🔧 RECOMMENDATIONS")
    print("-" * 70)
    recommendations = []

    if not result.trades or result.num_trades == 0:
        recommendations.append("⚠️  No trades executed - strategy may be too conservative")
        recommendations.append("   → Try lowering min_edge or max_spread_pct")
    elif result.num_trades < len(snapshots) * 0.1:
        recommendations.append("⚠️  Very few trades - strategy is highly selective")
        recommendations.append("   → Consider loosening filters if more activity desired")

    if result.trades:
        if report.financial_metrics["win_rate"] < 0.50:
            recommendations.append("⚠️  Win rate below 50% - edge identification needs work")
            recommendations.append("   → Review fair_prob calculations and min_edge threshold")

        if report.risk_metrics["max_drawdown_pct"] > 20:
            recommendations.append("⚠️  High drawdown detected")
            recommendations.append("   → Consider reducing max_risk_fraction or max_position_notional")

        if report.execution_metrics["avg_fill_rate"] < 0.4:
            recommendations.append("⚠️  Low fill rate on limit orders")
            recommendations.append("   → Increase limit_price_improvement_ticks for better fills")

    if not recommendations:
        recommendations.append("✅ Strategy performance looks solid!")
        recommendations.append("   Continue monitoring and consider parameter optimization")

    for rec in recommendations:
        print(rec)

    print("\n" + "=" * 70)
    print("Backtest complete! Review results in:", output_dir)
    print("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
