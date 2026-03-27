"""Test validation on existing sample markets to demonstrate warnings."""

from __future__ import annotations

import json
from pathlib import Path
from validation import FairProbValidator


def test_validation_on_sample_markets():
    """Run validation on sample_markets.json to show what warnings would be generated."""

    dataset_path = Path("/Users/howdymary/Documents/New project/autopredict/datasets/sample_markets.json")

    with dataset_path.open("r") as f:
        markets = json.load(f)

    validator = FairProbValidator()

    print("=" * 100)
    print("VALIDATION TEST ON SAMPLE MARKETS")
    print("=" * 100)
    print()

    total_warnings = 0
    markets_with_warnings = 0

    for market in markets:
        market_id = market["market_id"]
        category = market.get("category", "unknown")
        fair_prob = market["fair_prob"]
        market_prob = market["market_prob"]
        outcome = market["outcome"]

        warnings = validator.validate(fair_prob, market_prob, category, market)

        if warnings:
            markets_with_warnings += 1
            total_warnings += len(warnings)

            print(f"Market: {market_id}")
            print(f"  Category: {category}")
            print(f"  Fair prob: {fair_prob:.2f}, Market prob: {market_prob:.2f}, Outcome: {outcome}")
            print(f"  Edge: {abs(fair_prob - market_prob):.3f}")
            print()

            for warning in warnings:
                icon = "❌" if warning.severity == "error" else "⚠️" if warning.severity == "warning" else "ℹ️"
                print(f"  {icon} [{warning.severity.upper()}] {warning.message}")
                print(f"     Field: {warning.field} = {warning.value:.3f}")
                print(f"     Suggestion: {warning.suggestion}")
                print()

            print("-" * 100)
            print()

    print("=" * 100)
    print("VALIDATION SUMMARY")
    print("=" * 100)
    print(f"Total markets: {len(markets)}")
    print(f"Markets with warnings: {markets_with_warnings} ({markets_with_warnings/len(markets)*100:.1f}%)")
    print(f"Total warnings: {total_warnings}")
    print(f"Average warnings per market: {total_warnings/len(markets):.1f}")
    print()

    # Category breakdown
    category_warnings = {}
    for market in markets:
        category = market.get("category", "unknown")
        warnings = validator.validate(market["fair_prob"], market["market_prob"], category, market)
        category_warnings[category] = len(warnings)

    print("Warnings by category:")
    for category, count in sorted(category_warnings.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count} warnings")

    print()
    print("=" * 100)
    print("RECOMMENDATIONS")
    print("=" * 100)
    print()
    print("Based on validation results:")
    print()

    # Find problematic categories
    problematic = [cat for cat, count in category_warnings.items() if count >= 2]

    if problematic:
        print(f"Categories with multiple warnings: {', '.join(problematic)}")
        print("  → Review fair_prob estimation methodology for these categories")
        print("  → See docs/fair_prob_guidelines.md for category-specific guidance")
    else:
        print("No categories with excessive warnings detected.")

    print()
    print("General recommendations:")
    print("  1. Review markets in 'poor' or 'very_poor' quality categories (sports, macro, crypto)")
    print("  2. Consider reducing position size for markets with warnings")
    print("  3. Document reasoning when fair_prob differs significantly from market_prob")
    print("  4. Use validation.py to check new markets before adding to dataset")


if __name__ == "__main__":
    test_validation_on_sample_markets()
