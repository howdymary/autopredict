"""Autoresearch loop: iterative strategy improvement via metric-gated ratchet.

Usage:
    python experiments/run_autoresearch.py

The loop modifies strategy_configs/baseline.json and agent.py,
evaluates on the 500-market dataset, and keeps or reverts based
on composite score improvement.
"""

from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from autopredict.run_experiment import run_backtest
from autopredict.market_env import calculate_composite_score


DATASET_PRIMARY = REPO_ROOT / "datasets" / "sample_markets_500.json"
DATASET_CROSS_VAL = REPO_ROOT / "datasets" / "sample_markets_100.json"
CONFIG_PATH = REPO_ROOT / "strategy_configs" / "baseline.json"
LOG_PATH = REPO_ROOT / "experiments" / "log.jsonl"
BANKROLL = 1000.0

MAX_ITERATIONS = 50
MAX_CONSECUTIVE_REJECTS = 10
MIN_IMPROVEMENT_THRESHOLD = 0.001  # 0.1%
MAX_STALE_ACCEPTS = 5  # stop if 5 consecutive accepts improve < 0.1%


def load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with CONFIG_PATH.open("w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def run_eval(dataset_path: Path) -> dict:
    """Run backtest and return metrics."""
    return run_backtest(
        config_path=str(CONFIG_PATH),
        dataset_path=str(dataset_path),
        starting_bankroll=BANKROLL,
    )


def log_entry(entry: dict) -> None:
    """Append to experiment log."""
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def summarize_metrics(m: dict) -> dict:
    """Extract key metrics for logging."""
    return {
        "sharpe": round(m.get("sharpe", 0.0) or 0.0, 4),
        "total_pnl": round(m.get("total_pnl", 0.0) or 0.0, 2),
        "fill_rate": round(m.get("fill_rate", 0.0) or 0.0, 4),
        "max_drawdown": round(m.get("max_drawdown", 0.0) or 0.0, 2),
        "num_trades": m.get("num_trades", 0),
        "win_rate": round(m.get("win_rate", 0.0) or 0.0, 4),
        "avg_slippage_bps": round(m.get("avg_slippage_bps", 0.0) or 0.0, 2),
    }


# ---- EXPERIMENT DEFINITIONS ----
# Each experiment is a (hypothesis, change_fn, rollback_fn) tuple.
# change_fn modifies the config in place and returns a description.
# rollback_fn is called if the experiment is rejected.

def make_config_experiment(param: str, new_value: float, hypothesis: str):
    """Create a config knob experiment."""
    def apply(config):
        old = config.get(param)
        config[param] = new_value
        return f"{param}: {old} -> {new_value}"
    return hypothesis, apply


# Tier 1: Config knob sweeps
EXPERIMENTS = [
    # Tighten min_edge
    make_config_experiment("min_edge", 0.06, "Raising min_edge from 0.05 to 0.06 filters low-quality trades, improving Sharpe"),
    make_config_experiment("min_edge", 0.07, "Raising min_edge to 0.07 further reduces churn"),
    make_config_experiment("min_edge", 0.08, "Raising min_edge to 0.08 for high-conviction-only trades"),

    # Lower max_risk_fraction
    make_config_experiment("max_risk_fraction", 0.015, "Lowering max_risk_fraction from 0.02 to 0.015 reduces per-trade risk"),
    make_config_experiment("max_risk_fraction", 0.01, "Lowering max_risk_fraction to 0.01 for smaller positions"),

    # Raise min_book_liquidity
    make_config_experiment("min_book_liquidity", 80.0, "Raising min_book_liquidity from 60 to 80 filters thin books"),
    make_config_experiment("min_book_liquidity", 100.0, "Raising min_book_liquidity to 100 for deep-book-only trading"),
    make_config_experiment("min_book_liquidity", 120.0, "Raising min_book_liquidity to 120"),

    # Lower max_spread_pct
    make_config_experiment("max_spread_pct", 0.035, "Lowering max_spread_pct from 0.04 to 0.035 tightens spread filter"),
    make_config_experiment("max_spread_pct", 0.03, "Lowering max_spread_pct to 0.03"),
    make_config_experiment("max_spread_pct", 0.025, "Lowering max_spread_pct to 0.025"),

    # Lower max_depth_fraction
    make_config_experiment("max_depth_fraction", 0.12, "Lowering max_depth_fraction from 0.15 to 0.12 reduces market impact"),
    make_config_experiment("max_depth_fraction", 0.10, "Lowering max_depth_fraction to 0.10"),
    make_config_experiment("max_depth_fraction", 0.08, "Lowering max_depth_fraction to 0.08"),

    # Adjust split_threshold_fraction
    make_config_experiment("split_threshold_fraction", 0.20, "Lowering split_threshold from 0.25 to 0.20 triggers more splitting"),
    make_config_experiment("split_threshold_fraction", 0.15, "Lowering split_threshold to 0.15"),

    # Adjust aggressive_edge
    make_config_experiment("aggressive_edge", 0.15, "Raising aggressive_edge from 0.12 to 0.15 uses market orders more selectively"),
    make_config_experiment("aggressive_edge", 0.10, "Lowering aggressive_edge to 0.10 uses market orders more often for high-edge trades"),

    # Max position notional
    make_config_experiment("max_position_notional", 20.0, "Lowering max_position_notional from 25 to 20 caps position size"),
    make_config_experiment("max_position_notional", 30.0, "Raising max_position_notional to 30 allows larger positions in deep books"),

    # Limit price improvement
    make_config_experiment("limit_price_improvement_ticks", 2.0, "Raising limit_price_improvement to 2 ticks for better fill probability"),
    make_config_experiment("limit_price_improvement_ticks", 0.5, "Lowering limit_price_improvement to 0.5 ticks for less aggressive pricing"),
    make_config_experiment("limit_price_improvement_ticks", 0.0, "Setting limit_price_improvement to 0 (post at best bid/ask exactly)"),
]


def check_regression(new_metrics: dict, baseline_metrics: dict, threshold: float = 0.15) -> list[str]:
    """Check if any individual metric regressed more than threshold."""
    regressions = []
    checks = [
        ("sharpe", 1),       # higher is better
        ("total_pnl", 1),    # higher is better
        ("fill_rate", 1),    # higher is better
        ("max_drawdown", -1), # lower is better
    ]
    for metric, direction in checks:
        new_val = float(new_metrics.get(metric, 0.0) or 0.0)
        base_val = float(baseline_metrics.get(metric, 0.0) or 0.0)
        if abs(base_val) < 1e-9:
            continue
        change = (new_val - base_val) / abs(base_val)
        if direction == 1 and change < -threshold:
            regressions.append(f"{metric} regressed {change:.1%}")
        elif direction == -1 and change > threshold:
            regressions.append(f"{metric} increased {change:.1%}")
    return regressions


def main():
    print("=" * 70)
    print("AUTORESEARCH LOOP — AutoPredict Strategy Optimization")
    print("=" * 70)

    # Establish baseline
    print("\n[Baseline] Running initial evaluation on 500-market dataset...")
    baseline_metrics = run_eval(DATASET_PRIMARY)
    baseline_score = calculate_composite_score(baseline_metrics, baseline_metrics)
    baseline_config = load_config()

    print(f"  Baseline composite score: {baseline_score:.4f}")
    print(f"  Sharpe: {baseline_metrics['sharpe']:.4f}")
    print(f"  PnL: {baseline_metrics['total_pnl']:.2f}")
    print(f"  Fill rate: {baseline_metrics['fill_rate']:.4f}")
    print(f"  Max drawdown: {baseline_metrics['max_drawdown']:.2f}")
    print(f"  Num trades: {baseline_metrics['num_trades']:.0f}")

    log_entry({
        "iteration": 0,
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": "harness",
        "status": "baseline",
        "composite_score": baseline_score,
        "metrics": summarize_metrics(baseline_metrics),
        "config": baseline_config,
    })

    # Track state
    current_config = copy.deepcopy(baseline_config)
    current_metrics = baseline_metrics
    current_score = baseline_score
    consecutive_rejects = 0
    consecutive_stale_accepts = 0
    total_accepts = 0
    total_rejects = 0
    experiment_index = 0

    for i, (hypothesis, apply_fn) in enumerate(EXPERIMENTS, 1):
        if i > MAX_ITERATIONS:
            print(f"\n[STOP] Reached {MAX_ITERATIONS} iterations.")
            break
        if consecutive_rejects >= MAX_CONSECUTIVE_REJECTS:
            print(f"\n[STOP] {MAX_CONSECUTIVE_REJECTS} consecutive rejections — plateau detected.")
            break
        if consecutive_stale_accepts >= MAX_STALE_ACCEPTS:
            print(f"\n[STOP] {MAX_STALE_ACCEPTS} consecutive marginal accepts — diminishing returns.")
            break

        print(f"\n{'='*70}")
        print(f"[Iteration {i}/{len(EXPERIMENTS)}] {hypothesis}")
        print(f"{'='*70}")

        # Save rollback state
        rollback_config = copy.deepcopy(current_config)

        # Apply change
        candidate_config = copy.deepcopy(current_config)
        diff_desc = apply_fn(candidate_config)
        save_config(candidate_config)
        print(f"  Change: {diff_desc}")

        log_entry({
            "iteration": i,
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": "builder",
            "hypothesis": hypothesis,
            "change": diff_desc,
            "status": "proposed",
        })

        # Evaluate
        try:
            new_metrics = run_eval(DATASET_PRIMARY)
        except Exception as e:
            print(f"  ERROR: Backtest failed: {e}")
            save_config(rollback_config)
            log_entry({
                "iteration": i,
                "ts": datetime.now(timezone.utc).isoformat(),
                "agent": "harness",
                "status": "error",
                "error": str(e),
            })
            consecutive_rejects += 1
            total_rejects += 1
            continue

        new_score = calculate_composite_score(new_metrics, baseline_metrics)
        delta = new_score - current_score
        delta_pct = (delta / current_score * 100) if current_score > 1e-9 else 0.0

        print(f"  Composite: {current_score:.4f} -> {new_score:.4f} (delta: {delta:+.4f}, {delta_pct:+.1f}%)")
        print(f"  Sharpe: {new_metrics['sharpe']:.4f}  PnL: {new_metrics['total_pnl']:.2f}  "
              f"Fill: {new_metrics['fill_rate']:.4f}  DD: {new_metrics['max_drawdown']:.2f}  "
              f"Trades: {new_metrics['num_trades']:.0f}")

        # Check for regressions
        regressions = check_regression(new_metrics, current_metrics)

        # Decision
        if delta > 0 and not regressions:
            decision = "ACCEPT"
            current_config = candidate_config
            current_metrics = new_metrics
            current_score = new_score
            consecutive_rejects = 0
            total_accepts += 1

            if abs(delta_pct) < 0.1:
                consecutive_stale_accepts += 1
            else:
                consecutive_stale_accepts = 0

            # Cross-validate on 100-market dataset
            cv_metrics = run_eval(DATASET_CROSS_VAL)
            cv_score = calculate_composite_score(cv_metrics, baseline_metrics)

            print(f"  ACCEPTED (cross-val score: {cv_score:.4f})")

            log_entry({
                "iteration": i,
                "ts": datetime.now(timezone.utc).isoformat(),
                "agent": "evaluator",
                "decision": "accept",
                "composite_score": new_score,
                "delta": round(delta, 4),
                "cross_val_score": cv_score,
                "metrics": summarize_metrics(new_metrics),
                "config": candidate_config,
                "status": "resolved",
            })

        else:
            decision = "REJECT"
            reason = f"delta={delta:+.4f}"
            if regressions:
                reason += f", regressions: {', '.join(regressions)}"
            print(f"  REJECTED ({reason})")

            save_config(rollback_config)
            consecutive_rejects += 1
            total_rejects += 1
            consecutive_stale_accepts = 0

            log_entry({
                "iteration": i,
                "ts": datetime.now(timezone.utc).isoformat(),
                "agent": "evaluator",
                "decision": "reject",
                "composite_score": new_score,
                "delta": round(delta, 4),
                "reason": reason,
                "metrics": summarize_metrics(new_metrics),
                "status": "resolved",
            })

    # Final summary
    print("\n" + "=" * 70)
    print("AUTORESEARCH COMPLETE")
    print("=" * 70)
    print(f"Total experiments: {total_accepts + total_rejects}")
    print(f"Accepted: {total_accepts}")
    print(f"Rejected: {total_rejects}")
    print(f"Accept rate: {total_accepts / max(total_accepts + total_rejects, 1):.1%}")
    print(f"Baseline score: {baseline_score:.4f}")
    print(f"Final score: {current_score:.4f}")
    improvement = (current_score - baseline_score) / baseline_score * 100 if baseline_score > 1e-9 else 0
    print(f"Total improvement: {improvement:+.1f}%")
    print(f"\nFinal config: {json.dumps(current_config, indent=2)}")

    # Save optimized config
    optimized_path = REPO_ROOT / "strategy_configs" / "optimized.json"
    with optimized_path.open("w") as f:
        json.dump(current_config, f, indent=2)
        f.write("\n")
    print(f"\nOptimized config saved to {optimized_path}")

    # Save summary
    summary = {
        "total_experiments": total_accepts + total_rejects,
        "accepted": total_accepts,
        "rejected": total_rejects,
        "baseline_score": baseline_score,
        "final_score": current_score,
        "improvement_pct": improvement,
        "baseline_config": baseline_config,
        "final_config": current_config,
        "baseline_metrics": summarize_metrics(baseline_metrics),
        "final_metrics": summarize_metrics(current_metrics),
    }
    summary_path = REPO_ROOT / "experiments" / "summary.json"
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
