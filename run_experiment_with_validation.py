"""Enhanced experiment loop with input validation for fair_prob estimates.

This is an example of how to integrate FairProbValidator into the existing
run_experiment.py to catch low-quality forecasts before they hurt performance.
"""

from __future__ import annotations

import json
from pathlib import Path

from .agent import AutoPredictAgent, MarketState
from .market_env import ExecutionEngine, ForecastRecord, TradeRecord, evaluate_all
from .run_experiment import _build_order_book, _realized_pnl
from .validation import FairProbValidator, ValidationWarning


def _load_json(path: str | Path) -> dict | list:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
def run_backtest_with_validation(
    *,
    config_path: str | Path,
    dataset_path: str | Path,
    strategy_guidance_path: str | Path | None = None,
    starting_bankroll: float = 1_000.0,
    enable_validation: bool = True,
    skip_on_warnings: bool = False,  # If True, skip markets with warnings
) -> dict[str, object]:
    """
    Run a prediction market backtest with fair_prob validation.

    Args:
        config_path: Path to agent configuration
        dataset_path: Path to market dataset
        strategy_guidance_path: Optional strategy guidance
        starting_bankroll: Starting capital
        enable_validation: Enable fair_prob validation
        skip_on_warnings: Skip markets that trigger validation warnings

    Returns:
        Combined metrics including validation statistics
    """

    config = _load_json(config_path)
    dataset = _load_json(dataset_path)
    if not isinstance(config, dict):
        raise TypeError("Strategy config must be a JSON object")
    if not isinstance(dataset, list):
        raise TypeError("Dataset must be a JSON array")

    guidance = ""
    if strategy_guidance_path and Path(strategy_guidance_path).exists():
        guidance = Path(strategy_guidance_path).read_text(encoding="utf-8")

    agent = AutoPredictAgent.from_mapping(config)
    engine = ExecutionEngine()
    validator = FairProbValidator() if enable_validation else None

    bankroll = starting_bankroll
    forecasts: list[ForecastRecord] = []
    trades: list[TradeRecord] = []
    validation_stats = {
        "total_markets": 0,
        "markets_with_warnings": 0,
        "markets_skipped": 0,
        "warnings_by_severity": {"info": 0, "warning": 0, "error": 0},
        "warnings_by_category": {},
        "all_warnings": [],
    }

    print("=" * 80)
    print("RUNNING BACKTEST WITH VALIDATION")
    print("=" * 80)

    for record in dataset:
        if not isinstance(record, dict):
            continue

        market_id = str(record["market_id"])
        market_prob = float(record["market_prob"])
        fair_prob = float(record["fair_prob"])
        outcome = int(record["outcome"])
        category = record.get("category", "unknown")
        next_mid = float(record.get("next_mid_price", market_prob))
        expiry_hours = float(record.get("time_to_expiry_hours", 24.0))
        order_book = _build_order_book(market_id, record["order_book"])

        validation_stats["total_markets"] += 1

        # Validate fair_prob before using it
        should_skip = False
        if validator:
            should_reject, warnings = validator.validate_and_log(
                fair_prob=fair_prob,
                market_prob=market_prob,
                market_id=market_id,
                category=category,
                metadata=record,
            )

            if warnings:
                validation_stats["markets_with_warnings"] += 1
                for warning in warnings:
                    validation_stats["warnings_by_severity"][warning.severity] += 1
                    validation_stats["all_warnings"].append({
                        "market_id": market_id,
                        "category": category,
                        "severity": warning.severity,
                        "message": warning.message,
                        "field": warning.field,
                        "value": warning.value,
                    })

                validation_stats["warnings_by_category"][category] = (
                    validation_stats["warnings_by_category"].get(category, 0) + len(warnings)
                )

            if should_reject or (skip_on_warnings and warnings):
                validation_stats["markets_skipped"] += 1
                print(f"  ⏭️  SKIPPING market {market_id} due to validation issues\n")
                should_skip = True

        if should_skip:
            continue

        # Create market state
        state = MarketState(
            market_id=market_id,
            market_prob=market_prob,
            fair_prob=fair_prob,
            time_to_expiry_hours=expiry_hours,
            order_book=order_book,
            metadata={"category": category},
        )

        # Record forecast for calibration metrics
        forecasts.append(ForecastRecord(market_id=market_id, probability=fair_prob, outcome=outcome))

        # Get agent's trading decision
        proposal = agent.evaluate_market(state, bankroll)
        if proposal is None:
            continue

        # Execute order(s)
        order_sizes = proposal.split_sizes or [proposal.size]
        for order_size in order_sizes:
            if proposal.order_type == "market":
                report = engine.execute_market_order(order_size, proposal.side, order_book)
            else:
                report = engine.execute_limit_order(
                    price=float(proposal.limit_price or order_book.get_mid_price()),
                    size=order_size,
                    side=proposal.side,
                    order_book=order_book,
                    time_in_force="GTC",
                )

            if report.filled_size <= 0 or report.average_fill_price is None:
                continue

            # Calculate P&L
            pnl = _realized_pnl(
                side=proposal.side,
                fill_price=report.average_fill_price,
                outcome=outcome,
                filled_size=report.filled_size,
            )
            bankroll += pnl

            # Record trade
            trades.append(
                TradeRecord(
                    market_id=market_id,
                    side=proposal.side,
                    order_type=proposal.order_type,
                    requested_size=report.requested_size,
                    filled_size=report.filled_size,
                    fill_price=report.average_fill_price,
                    mid_at_decision=report.reference_mid_price,
                    next_mid_price=next_mid,
                    outcome=outcome,
                    pnl=pnl,
                    slippage_bps=report.slippage_bps,
                    market_impact_bps=report.market_impact_bps,
                    implementation_shortfall_bps=report.implementation_shortfall_bps,
                    fill_rate=report.fill_rate,
                )
            )

    # Calculate metrics
    metrics = evaluate_all(forecasts, trades)
    metrics["starting_bankroll"] = starting_bankroll
    metrics["ending_bankroll"] = bankroll
    metrics["agent_feedback"] = agent.analyze_performance(metrics, guidance)

    # Add validation statistics
    if enable_validation:
        metrics["validation_stats"] = validation_stats

        # Print validation summary
        print()
        print("=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        print(f"Total markets: {validation_stats['total_markets']}")
        print(f"Markets with warnings: {validation_stats['markets_with_warnings']}")
        print(f"Markets skipped: {validation_stats['markets_skipped']}")
        print()
        print("Warnings by severity:")
        for severity, count in validation_stats["warnings_by_severity"].items():
            print(f"  {severity}: {count}")
        print()
        print("Warnings by category:")
        for category, count in sorted(
            validation_stats["warnings_by_category"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  {category}: {count}")
        print("=" * 80)

    return metrics


# Example usage
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Default paths
    config_path = Path("/Users/howdymary/Documents/New project/autopredict/strategy_configs/baseline.json")
    dataset_path = Path("/Users/howdymary/Documents/New project/autopredict/datasets/sample_markets.json")

    print("\nRunning backtest WITH validation (warnings only, no skipping)...\n")
    results = run_backtest_with_validation(
        config_path=config_path,
        dataset_path=dataset_path,
        enable_validation=True,
        skip_on_warnings=False,  # Show warnings but don't skip
    )

    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    print(f"Brier Score: {results.get('brier_score', 0):.4f}")
    print(f"Total P&L: ${results.get('total_pnl', 0):.2f}")
    print(f"Sharpe Ratio: {results.get('sharpe', 0):.2f}")
    print(f"Win Rate: {results.get('win_rate', 0):.1%}")
    print()

    # Show calibration by bucket
    print("Calibration by Bucket:")
    cal_buckets = results.get("calibration_by_bucket", {})
    for bucket, data in sorted(cal_buckets.items()):
        print(f"  {bucket}: avg={data['avg_probability']:.2f}, realized={data['realized_rate']:.2f}, n={int(data['count'])}")

    print("\n" + "=" * 80)
