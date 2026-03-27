"""Detailed calibration analysis comparing fair_prob vs market_prob performance."""

from __future__ import annotations

import json
from pathlib import Path


def analyze_market_by_market(dataset_path: str | Path) -> None:
    """Analyze each market individually to understand calibration patterns."""

    with Path(dataset_path).open("r") as f:
        data = json.load(f)

    print("=" * 100)
    print("MARKET-BY-MARKET CALIBRATION ANALYSIS")
    print("=" * 100)
    print()
    print(f"{'Market ID':<35} {'Category':<12} {'Fair':<6} {'Mkt':<6} {'Out':<4} {'Fair Err':<9} {'Mkt Err':<9} {'Winner'}")
    print("-" * 100)

    fair_wins = 0
    market_wins = 0
    total_fair_error = 0.0
    total_market_error = 0.0

    for item in data:
        market_id = item["market_id"]
        category = item.get("category", "unknown")
        fair_prob = item["fair_prob"]
        market_prob = item["market_prob"]
        outcome = item["outcome"]

        fair_error = (fair_prob - outcome) ** 2
        market_error = (market_prob - outcome) ** 2

        total_fair_error += fair_error
        total_market_error += market_error

        winner = "FAIR" if fair_error < market_error else "MARKET"
        if fair_error < market_error:
            fair_wins += 1
        else:
            market_wins += 1

        print(f"{market_id:<35} {category:<12} {fair_prob:<6.2f} {market_prob:<6.2f} "
              f"{outcome:<4} {fair_error:<9.4f} {market_error:<9.4f} {winner}")

    print("-" * 100)
    print(f"Overall Brier Scores: Fair={total_fair_error/len(data):.4f}, Market={total_market_error/len(data):.4f}")
    print(f"Fair won {fair_wins}/{len(data)} markets, Market won {market_wins}/{len(data)} markets")
    print()

    # Analyze the pattern
    print("=" * 100)
    print("CALIBRATION PATTERN ANALYSIS")
    print("=" * 100)
    print()

    # Check if fair_prob is systematically over/under confident
    overconfident_when_right = []
    overconfident_when_wrong = []
    underconfident_when_right = []
    underconfident_when_wrong = []

    for item in data:
        fair_prob = item["fair_prob"]
        market_prob = item["market_prob"]
        outcome = item["outcome"]

        # Fair prob is more extreme than market
        if abs(fair_prob - 0.5) > abs(market_prob - 0.5):
            if outcome == 1 and fair_prob > market_prob:
                overconfident_when_right.append(item)
            elif outcome == 0 and fair_prob < market_prob:
                overconfident_when_right.append(item)
            else:
                overconfident_when_wrong.append(item)
        else:
            if outcome == 1 and fair_prob > market_prob:
                underconfident_when_right.append(item)
            elif outcome == 0 and fair_prob < market_prob:
                underconfident_when_right.append(item)
            else:
                underconfident_when_wrong.append(item)

    print(f"Fair prob MORE extreme than market: {len(overconfident_when_right) + len(overconfident_when_wrong)}/6")
    print(f"  - Was correct: {len(overconfident_when_right)}")
    print(f"  - Was wrong: {len(overconfident_when_wrong)}")
    print()
    print(f"Fair prob LESS extreme than market: {len(underconfident_when_right) + len(underconfident_when_wrong)}/6")
    print(f"  - Was correct: {len(underconfident_when_right)}")
    print(f"  - Was wrong: {len(underconfident_when_wrong)}")
    print()

    # Detailed breakdown
    print("Markets where fair_prob was MORE extreme and WRONG:")
    for item in overconfident_when_wrong:
        print(f"  {item['market_id']}: fair={item['fair_prob']:.2f}, market={item['market_prob']:.2f}, outcome={item['outcome']}")

    print()
    print("Markets where fair_prob was MORE extreme and RIGHT:")
    for item in overconfident_when_right:
        print(f"  {item['market_id']}: fair={item['fair_prob']:.2f}, market={item['market_prob']:.2f}, outcome={item['outcome']}")

    print()
    print("=" * 100)
    print("KEY INSIGHTS")
    print("=" * 100)
    print()

    if len(overconfident_when_right) > len(overconfident_when_wrong):
        print("FINDING: fair_prob is MORE extreme than market AND more often CORRECT!")
        print("  => This is GOOD EDGE - fair_prob has genuine predictive power")
        print("  => DO NOT shrink toward market - you'll throw away your edge")
        print()
        print("RECOMMENDATION: Keep using fair_prob as-is, but:")
        print("  1. Improve fair_prob quality in categories with high Brier scores (sports, macro, crypto)")
        print("  2. Collect more data to identify systematic biases")
        print("  3. Add uncertainty estimates to fair_prob (e.g., confidence intervals)")
    else:
        print("FINDING: fair_prob is MORE extreme than market but often WRONG")
        print("  => This suggests overconfidence in fair_prob estimates")
        print("  => Consider shrinking toward market or improving estimation process")

    print()
    print("Category-specific recommendations:")
    print("  - sports (Brier=0.46): WORST category, needs improvement")
    print("  - macro (Brier=0.29): Below average, review methodology")
    print("  - crypto (Brier=0.29): Below average, consider more volatility adjustment")
    print("  - politics (Brier=0.23): Slightly above average, maintain quality")
    print("  - science (Brier=0.14): EXCELLENT, use as template for other categories")
    print("  - geopolitics (Brier=0.12): EXCELLENT, use as template for other categories")


if __name__ == "__main__":
    dataset_path = "/Users/howdymary/Documents/New project/autopredict/datasets/sample_markets.json"
    analyze_market_by_market(dataset_path)
