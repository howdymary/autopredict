"""Calibration Analysis and Improvement Recommendations for AutoPredict.

This module analyzes the calibration issues in AutoPredict forecasts and proposes
solutions to improve the Brier score from the current 0.255.

Key findings from the data:
1. Current Brier score: 0.255 (higher is worse, perfect is 0.0)
2. Calibration issues by bucket:
   - 0.3-0.4: avg_prob=0.34, realized=0.0 (underconfident, should be lower)
   - 0.4-0.5: avg_prob=0.46, realized=1.0 (very underconfident)
   - 0.5-0.6: avg_prob=0.53, realized=0.5 (well calibrated!)
   - 0.6-0.7: avg_prob=0.655, realized=0.5 (overconfident, should be closer to 0.5)

3. Pattern: The fair_prob estimates appear to have systematic bias:
   - Lower probabilities (0.3-0.5) are TOO LOW when events happen
   - Higher probabilities (0.6-0.7) are TOO HIGH when events don't happen
   - This suggests the fair_prob might be overconfident (too extreme)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def isotonic_calibration(probabilities: list[float], outcomes: list[int]) -> dict[float, float]:
    """
    Simple isotonic regression for probability calibration.
    Maps raw probabilities to calibrated probabilities based on realized outcomes.
    """
    if not probabilities or len(probabilities) != len(outcomes):
        return {}

    # Group by probability buckets
    buckets: dict[str, list[int]] = {}
    bucket_probs: dict[str, list[float]] = {}

    for prob, outcome in zip(probabilities, outcomes):
        bucket_key = f"{int(prob * 10) / 10.0:.1f}"
        buckets.setdefault(bucket_key, []).append(outcome)
        bucket_probs.setdefault(bucket_key, []).append(prob)

    # Calculate realized rates for each bucket
    calibration_map = {}
    for bucket_key, outcomes_list in buckets.items():
        avg_prob = sum(bucket_probs[bucket_key]) / len(bucket_probs[bucket_key])
        realized_rate = sum(outcomes_list) / len(outcomes_list)
        calibration_map[avg_prob] = realized_rate

    return calibration_map


def shrink_toward_market(fair_prob: float, market_prob: float, shrinkage_factor: float = 0.3) -> float:
    """
    Apply shrinkage to fair_prob toward market_prob to reduce overconfidence.

    Args:
        fair_prob: The agent's fair value estimate
        market_prob: The current market price
        shrinkage_factor: Weight given to market (0.0 = no shrinkage, 1.0 = use market entirely)

    Returns:
        Calibrated probability that's less extreme
    """
    calibrated = (1 - shrinkage_factor) * fair_prob + shrinkage_factor * market_prob
    return max(0.01, min(0.99, calibrated))  # Clip to valid probability range


def platt_scaling(raw_prob: float, a: float = 1.0, b: float = 0.0) -> float:
    """
    Apply Platt scaling: P_calibrated = 1 / (1 + exp(a * logit(P_raw) + b))

    This is a parametric calibration method that can fix sigmoid-shaped miscalibration.
    """
    # Convert to log-odds
    epsilon = 1e-9
    raw_prob = max(epsilon, min(1 - epsilon, raw_prob))
    logit = math.log(raw_prob / (1 - raw_prob))

    # Apply scaling
    scaled_logit = a * logit + b

    # Convert back to probability
    calibrated = 1 / (1 + math.exp(-scaled_logit))
    return max(epsilon, min(1 - epsilon, calibrated))


def analyze_calibration_from_data(dataset_path: str | Path) -> dict[str, Any]:
    """Analyze calibration patterns in the sample dataset."""
    with Path(dataset_path).open("r") as f:
        data = json.load(f)

    fair_probs = [item["fair_prob"] for item in data]
    market_probs = [item["market_prob"] for item in data]
    outcomes = [item["outcome"] for item in data]

    # Calculate errors
    fair_errors = [(fp - o) ** 2 for fp, o in zip(fair_probs, outcomes)]
    market_errors = [(mp - o) ** 2 for mp, o in zip(market_probs, outcomes)]

    fair_brier = sum(fair_errors) / len(fair_errors)
    market_brier = sum(market_errors) / len(market_errors)

    # Test shrinkage approach
    shrinkage_results = {}
    for alpha in [0.1, 0.2, 0.3, 0.4, 0.5]:
        calibrated = [
            shrink_toward_market(fp, mp, alpha)
            for fp, mp in zip(fair_probs, market_probs)
        ]
        calibrated_errors = [(cp - o) ** 2 for cp, o in zip(calibrated, outcomes)]
        calibrated_brier = sum(calibrated_errors) / len(calibrated_errors)
        shrinkage_results[alpha] = calibrated_brier

    # Analyze by category
    category_analysis = {}
    categories = {}
    for item in data:
        cat = item.get("category", "unknown")
        categories.setdefault(cat, []).append(item)

    for cat, items in categories.items():
        cat_fair_probs = [item["fair_prob"] for item in items]
        cat_outcomes = [item["outcome"] for item in items]
        cat_errors = [(fp - o) ** 2 for fp, o in zip(cat_fair_probs, cat_outcomes)]
        category_analysis[cat] = {
            "count": len(items),
            "brier_score": sum(cat_errors) / len(cat_errors) if cat_errors else 0,
            "avg_edge": sum(abs(item["fair_prob"] - item["market_prob"]) for item in items) / len(items),
        }

    return {
        "fair_brier": fair_brier,
        "market_brier": market_brier,
        "improvement_potential": market_brier - fair_brier,
        "shrinkage_results": shrinkage_results,
        "best_shrinkage": min(shrinkage_results.items(), key=lambda x: x[1]),
        "category_analysis": category_analysis,
        "sample_size": len(data),
    }


def generate_recommendations(analysis: dict[str, Any]) -> dict[str, Any]:
    """Generate actionable recommendations based on calibration analysis."""

    fair_brier = analysis["fair_brier"]
    market_brier = analysis["market_brier"]
    best_shrinkage_alpha, best_shrinkage_brier = analysis["best_shrinkage"]

    recommendations = {
        "summary": "Calibration Analysis for AutoPredict",
        "current_state": {
            "fair_brier_score": round(fair_brier, 4),
            "market_brier_score": round(market_brier, 4),
            "verdict": "Fair estimates are worse than market" if fair_brier > market_brier else "Fair estimates beat market",
        },
        "proposed_solutions": [],
    }

    # Solution 1: Shrinkage toward market
    if best_shrinkage_brier < fair_brier:
        improvement = ((fair_brier - best_shrinkage_brier) / fair_brier) * 100
        recommendations["proposed_solutions"].append({
            "method": "shrinkage_toward_market",
            "description": f"Blend fair_prob with market_prob using {best_shrinkage_alpha:.1%} weight on market",
            "expected_brier": round(best_shrinkage_brier, 4),
            "improvement_pct": round(improvement, 1),
            "implementation": "Add calibration layer in agent.evaluate_market() before edge calculation",
            "code_location": "/Users/howdymary/Documents/New project/autopredict/agent.py lines 131-147",
        })

    # Solution 2: Category-specific calibration
    category_variances = [
        cat_data["brier_score"]
        for cat_data in analysis["category_analysis"].values()
    ]
    if category_variances and max(category_variances) - min(category_variances) > 0.1:
        recommendations["proposed_solutions"].append({
            "method": "category_specific_calibration",
            "description": "Different categories show different calibration quality; apply category-specific adjustments",
            "worst_category": max(
                analysis["category_analysis"].items(),
                key=lambda x: x[1]["brier_score"]
            )[0],
            "implementation": "Add category-based calibration map in MarketState metadata",
        })

    # Solution 3: Data quality improvements
    recommendations["data_quality_guidance"] = {
        "for_users": [
            "Avoid extreme probabilities unless you have strong evidence",
            "Consider the market price as a baseline - large deviations should be justified",
            "Use historical base rates for similar events as anchors",
            "Test your fair_prob estimates on out-of-sample data before deployment",
        ],
        "validation_rules": [
            "Flag fair_prob that differs from market_prob by >20% for review",
            "Require additional justification for probabilities <0.15 or >0.85",
            "Cross-validate against historical outcomes in similar markets",
        ],
    }

    # Solution 4: Implement proper calibration curve
    recommendations["advanced_solution"] = {
        "method": "isotonic_regression",
        "description": "Fit a calibration curve using historical (fair_prob, outcome) pairs",
        "requirements": [
            "Need more historical data (current sample: {} markets)".format(analysis["sample_size"]),
            "Minimum 100-200 markets recommended for reliable calibration",
            "Re-fit calibration curve periodically as more data accumulates",
        ],
        "implementation": "Create calibration.py module with fitted calibration map",
    }

    return recommendations


def create_calibrated_agent_code() -> str:
    """Generate code snippet for calibrated agent implementation."""
    return """
# Add to agent.py in AutoPredictAgent class:

class AutoPredictAgent:
    def __init__(self, config: AgentConfig | None = None, calibration_alpha: float = 0.3) -> None:
        self.config = config or AgentConfig()
        self.execution = ExecutionStrategy()
        self.calibration_alpha = calibration_alpha  # Shrinkage toward market

    def calibrate_probability(self, fair_prob: float, market_prob: float) -> float:
        '''Apply calibration to reduce overconfidence in fair_prob.'''
        # Shrinkage toward market consensus
        calibrated = (1 - self.calibration_alpha) * fair_prob + self.calibration_alpha * market_prob

        # Clip to valid probability range
        return max(0.01, min(0.99, calibrated))

    def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
        # BEFORE: edge = market.fair_prob - market.market_prob
        # AFTER: Apply calibration first
        calibrated_fair = self.calibrate_probability(market.fair_prob, market.market_prob)
        edge = calibrated_fair - market.market_prob

        # Rest of the method stays the same...
        abs_edge = abs(edge)
        # ... continue as before
"""


if __name__ == "__main__":
    # Run analysis
    dataset_path = "/Users/howdymary/Documents/New project/autopredict/datasets/sample_markets.json"

    print("=" * 80)
    print("AUTOPREDICT CALIBRATION ANALYSIS")
    print("=" * 80)
    print()

    analysis = analyze_calibration_from_data(dataset_path)

    print(f"Current Brier Score (fair_prob): {analysis['fair_brier']:.4f}")
    print(f"Market Brier Score (market_prob): {analysis['market_brier']:.4f}")
    print()

    if analysis['fair_brier'] > analysis['market_brier']:
        print("WARNING: Your fair_prob estimates are performing WORSE than just using market prices!")
        print(f"Potential improvement: {analysis['improvement_potential']:.4f}")
    else:
        print("Good news: Your fair_prob estimates beat the market baseline.")

    print()
    print("Shrinkage Analysis (blending fair_prob with market_prob):")
    print("-" * 60)
    for alpha, brier in sorted(analysis['shrinkage_results'].items()):
        improvement = ((analysis['fair_brier'] - brier) / analysis['fair_brier']) * 100
        marker = " <-- BEST" if (alpha, brier) == analysis['best_shrinkage'] else ""
        print(f"  Alpha={alpha:.1f} (weight on market): Brier={brier:.4f} ({improvement:+.1f}%){marker}")

    print()
    print("Category Analysis:")
    print("-" * 60)
    for cat, cat_data in sorted(analysis['category_analysis'].items(), key=lambda x: x[1]['brier_score'], reverse=True):
        print(f"  {cat:12s}: Brier={cat_data['brier_score']:.4f}, Avg Edge={cat_data['avg_edge']:.3f}, N={cat_data['count']}")

    print()
    print("=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)

    recommendations = generate_recommendations(analysis)

    print()
    print("PROPOSED SOLUTIONS:")
    for i, solution in enumerate(recommendations['proposed_solutions'], 1):
        print(f"\n{i}. {solution['method'].upper()}")
        print(f"   Description: {solution['description']}")
        if 'expected_brier' in solution:
            print(f"   Expected Brier: {solution['expected_brier']:.4f} ({solution['improvement_pct']:+.1f}% improvement)")
        if 'implementation' in solution:
            print(f"   Implementation: {solution['implementation']}")
        if 'code_location' in solution:
            print(f"   Code Location: {solution['code_location']}")

    print()
    print("DATA QUALITY GUIDANCE FOR USERS:")
    for guidance in recommendations['data_quality_guidance']['for_users']:
        print(f"  - {guidance}")

    print()
    print("VALIDATION RULES:")
    for rule in recommendations['data_quality_guidance']['validation_rules']:
        print(f"  - {rule}")

    print()
    print("=" * 80)
    print("IMPLEMENTATION CODE")
    print("=" * 80)
    print(create_calibrated_agent_code())

    # Save recommendations to file
    output_path = Path("/Users/howdymary/Documents/New project/autopredict/calibration_recommendations.json")
    with output_path.open("w") as f:
        json.dump(recommendations, f, indent=2)

    print()
    print(f"Detailed recommendations saved to: {output_path}")
