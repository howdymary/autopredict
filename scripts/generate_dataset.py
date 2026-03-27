"""Dataset generator for AutoPredict with realistic market characteristics."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class MarketCharacteristics:
    """Configuration for market generation with realistic distributions."""

    # Category distributions with quality tiers
    CATEGORIES = {
        "geopolitics": {"weight": 0.15, "quality": "excellent", "base_brier": 0.116},
        "science": {"weight": 0.12, "quality": "excellent", "base_brier": 0.137},
        "politics": {"weight": 0.25, "quality": "good", "base_brier": 0.230},
        "crypto": {"weight": 0.18, "quality": "poor", "base_brier": 0.292},
        "macro": {"weight": 0.20, "quality": "poor", "base_brier": 0.292},
        "sports": {"weight": 0.10, "quality": "very_poor", "base_brier": 0.462},
    }

    # Liquidity tiers (total depth on both sides)
    LIQUIDITY_TIERS = {
        "micro": {"min": 100, "max": 300, "weight": 0.20},  # Low liquidity
        "small": {"min": 300, "max": 800, "weight": 0.35},  # Medium liquidity
        "medium": {"min": 800, "max": 2000, "weight": 0.30},  # Good liquidity
        "large": {"min": 2000, "max": 5000, "weight": 0.15},  # High liquidity
    }

    # Spread width tiers (as percentage of mid price)
    SPREAD_TIERS = {
        "tight": {"min": 0.005, "max": 0.015, "weight": 0.25},  # 0.5-1.5%
        "normal": {"min": 0.015, "max": 0.035, "weight": 0.45},  # 1.5-3.5%
        "wide": {"min": 0.035, "max": 0.060, "weight": 0.20},  # 3.5-6.0%
        "very_wide": {"min": 0.060, "max": 0.100, "weight": 0.10},  # 6-10%
    }

    # Time to expiry (hours)
    TIME_TO_EXPIRY = {
        "urgent": {"min": 1, "max": 12, "weight": 0.10},  # < 12 hours
        "short": {"min": 12, "max": 48, "weight": 0.25},  # 12-48 hours
        "medium": {"min": 48, "max": 168, "weight": 0.40},  # 2-7 days
        "long": {"min": 168, "max": 720, "weight": 0.25},  # 1-30 days
    }


class MarketGenerator:
    """Generate realistic prediction markets with diverse characteristics."""

    def __init__(self, seed: int | None = None) -> None:
        """Initialize generator with optional seed for reproducibility."""
        self.seed = seed
        if seed is not None:
            random.seed(seed)
        self.chars = MarketCharacteristics()

    def generate_market_id(self, category: str, index: int) -> str:
        """Generate a descriptive market ID."""
        prefixes = {
            "geopolitics": ["ceasefire", "treaty", "election", "sanctions", "summit"],
            "science": ["launch", "discovery", "trial", "breakthrough", "experiment"],
            "politics": ["election", "referendum", "vote", "approval", "poll"],
            "crypto": ["btc", "eth", "sol", "defi", "nft"],
            "macro": ["fed", "gdp", "inflation", "rate", "unemployment"],
            "sports": ["championship", "playoff", "finals", "match", "tournament"],
        }

        suffixes = [
            "before-deadline", "by-year-end", "next-quarter", "this-month",
            "within-week", "above-target", "below-threshold", "on-schedule"
        ]

        prefix = random.choice(prefixes.get(category, ["market"]))
        suffix = random.choice(suffixes)
        return f"{prefix}-{suffix}-{category[:4]}-{index:04d}"

    def select_tier(self, tier_config: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        """Select a tier based on weighted probabilities."""
        tiers = list(tier_config.items())
        weights = [tier[1]["weight"] for tier in tiers]
        selected = random.choices(tiers, weights=weights, k=1)[0]
        return selected[0], selected[1]

    def generate_probability(
        self, category: str, base_prob: float | None = None
    ) -> tuple[float, float, int]:
        """
        Generate market_prob, fair_prob, and outcome with realistic patterns.

        Returns:
            (market_prob, fair_prob, outcome)
        """
        # Generate base probability (market midpoint)
        if base_prob is None:
            # Bias towards more interesting probabilities (avoid extremes)
            base_prob = random.betavariate(2, 2)  # Beta(2,2) peaks at 0.5

        # Add category-specific noise based on quality
        category_info = self.chars.CATEGORIES[category]
        base_brier = category_info["base_brier"]

        # Quality affects edge size and accuracy
        if category_info["quality"] == "excellent":
            edge_scale = random.uniform(0.03, 0.12)
            noise_scale = 0.02
        elif category_info["quality"] == "good":
            edge_scale = random.uniform(0.04, 0.15)
            noise_scale = 0.04
        elif category_info["quality"] == "poor":
            edge_scale = random.uniform(0.05, 0.20)
            noise_scale = 0.06
        else:  # very_poor
            edge_scale = random.uniform(0.08, 0.25)
            noise_scale = 0.10

        # Generate fair_prob with edge
        edge_direction = random.choice([-1, 1])
        fair_prob = base_prob + (edge_direction * edge_scale)
        fair_prob = max(0.05, min(0.95, fair_prob))  # Keep in reasonable range

        # Market_prob is fair_prob with some noise
        market_prob = fair_prob - (edge_direction * edge_scale * random.uniform(0.8, 1.2))
        market_prob += random.gauss(0, noise_scale)
        market_prob = max(0.05, min(0.95, market_prob))

        # Generate outcome based on fair_prob (with some randomness)
        # Fair prob should win more often than market prob (shows quality)
        outcome_threshold = fair_prob + random.gauss(0, 0.15)
        outcome = 1 if random.random() < outcome_threshold else 0

        return market_prob, fair_prob, outcome

    def generate_order_book(
        self,
        market_prob: float,
        liquidity_tier: dict[str, Any],
        spread_tier: dict[str, Any],
        depth_levels: int = 10
    ) -> dict[str, Any]:
        """
        Generate realistic order book with proper structure.

        Returns:
            {"bids": [[price, size], ...], "asks": [[price, size], ...]}
        """
        # Calculate mid price from market probability
        mid_price = market_prob

        # Calculate spread width
        spread_pct = random.uniform(spread_tier["min"], spread_tier["max"])
        spread = mid_price * spread_pct
        half_spread = spread / 2

        # Best bid and ask
        best_bid = mid_price - half_spread
        best_ask = mid_price + half_spread

        # Round prices to 2 decimal places
        best_bid = round(best_bid, 2)
        best_ask = round(best_ask, 2)

        # Ensure valid probabilities and non-crossed book
        best_bid = max(0.01, min(0.98, best_bid))
        best_ask = max(0.02, min(0.99, best_ask))

        # Ensure ask is always above bid with minimum tick
        min_tick = 0.01
        if best_ask <= best_bid:
            best_ask = best_bid + min_tick
            best_ask = round(min(0.99, best_ask), 2)

        # Generate total liquidity
        total_liquidity = random.uniform(liquidity_tier["min"], liquidity_tier["max"])

        # Split between bids and asks (roughly 50/50 with some variance)
        bid_fraction = random.uniform(0.45, 0.55)
        total_bid_size = total_liquidity * bid_fraction
        total_ask_size = total_liquidity * (1 - bid_fraction)

        # Generate bids (descending prices from best_bid)
        bids = []
        remaining_bid = total_bid_size
        current_price = best_bid
        tick_size = 0.01

        for i in range(min(depth_levels, 10)):
            # Size decreases with distance from best price
            size_fraction = random.uniform(0.08, 0.15) * (1 - i * 0.05)
            size = min(remaining_bid * size_fraction, remaining_bid)

            if size < 1.0:
                break

            # Round price but ensure it decreases
            rounded_price = round(current_price, 2)
            if bids and rounded_price >= bids[-1][0]:
                rounded_price = bids[-1][0] - 0.01
                rounded_price = max(0.01, rounded_price)

            if rounded_price <= 0.01:
                break

            bids.append([rounded_price, round(size, 1)])
            remaining_bid -= size
            current_price -= tick_size
            current_price = max(0.01, current_price)

            if remaining_bid < 1.0:
                break

        # Generate asks (ascending prices from best_ask)
        asks = []
        remaining_ask = total_ask_size
        current_price = best_ask

        for i in range(min(depth_levels, 10)):
            size_fraction = random.uniform(0.08, 0.15) * (1 - i * 0.05)
            size = min(remaining_ask * size_fraction, remaining_ask)

            if size < 1.0:
                break

            # Round price but ensure it increases
            rounded_price = round(current_price, 2)
            if asks and rounded_price <= asks[-1][0]:
                rounded_price = asks[-1][0] + 0.01
                rounded_price = min(0.99, rounded_price)

            if rounded_price >= 0.99:
                break

            asks.append([rounded_price, round(size, 1)])
            remaining_ask -= size
            current_price += tick_size
            current_price = min(0.99, current_price)

            if remaining_ask < 1.0:
                break

        return {"bids": bids, "asks": asks}

    def generate_next_mid_price(
        self,
        market_prob: float,
        fair_prob: float,
        outcome: int,
        time_to_expiry_hours: float
    ) -> float:
        """
        Generate realistic next_mid_price (price after some time has passed).

        Should move towards fair_prob and outcome, with some noise.
        """
        # Base movement towards fair value
        fair_pull = 0.3 if time_to_expiry_hours > 48 else 0.5
        outcome_pull = 0.2 if time_to_expiry_hours > 24 else 0.4

        # Price moves towards fair and outcome
        target = fair_prob * fair_pull + outcome * outcome_pull + market_prob * (1 - fair_pull - outcome_pull)

        # Add noise
        noise = random.gauss(0, 0.02)
        next_mid = target + noise

        # Keep in valid range
        next_mid = max(0.05, min(0.95, next_mid))
        return round(next_mid, 2)

    def generate_market(
        self,
        index: int,
        category: str | None = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Generate a single market with all required fields.

        Args:
            index: Market index for ID generation
            category: Optional category (random if not specified)
            **kwargs: Override any generated values
        """
        # Select category
        if category is None:
            categories = list(self.chars.CATEGORIES.keys())
            weights = [self.chars.CATEGORIES[cat]["weight"] for cat in categories]
            category = random.choices(categories, weights=weights, k=1)[0]

        # Select tiers
        liquidity_tier_name, liquidity_tier = self.select_tier(self.chars.LIQUIDITY_TIERS)
        spread_tier_name, spread_tier = self.select_tier(self.chars.SPREAD_TIERS)
        time_tier_name, time_tier = self.select_tier(self.chars.TIME_TO_EXPIRY)

        # Generate probabilities and outcome
        market_prob, fair_prob, outcome = self.generate_probability(category)

        # Generate time to expiry
        time_to_expiry_hours = random.uniform(time_tier["min"], time_tier["max"])

        # Generate order book
        order_book = self.generate_order_book(
            market_prob, liquidity_tier, spread_tier
        )

        # Generate next mid price
        next_mid_price = self.generate_next_mid_price(
            market_prob, fair_prob, outcome, time_to_expiry_hours
        )

        # Build market data
        market = {
            "market_id": self.generate_market_id(category, index),
            "category": category,
            "market_prob": round(market_prob, 2),
            "fair_prob": round(fair_prob, 2),
            "outcome": outcome,
            "time_to_expiry_hours": round(time_to_expiry_hours, 1),
            "next_mid_price": next_mid_price,
            "order_book": order_book,
            # Metadata for analysis
            "metadata": {
                "liquidity_tier": liquidity_tier_name,
                "spread_tier": spread_tier_name,
                "time_tier": time_tier_name,
                "edge": round(abs(fair_prob - market_prob), 3),
                "total_depth": round(
                    sum(b[1] for b in order_book["bids"]) +
                    sum(a[1] for a in order_book["asks"]),
                    1
                ),
            }
        }

        # Allow overrides
        market.update(kwargs)

        return market

    def generate_dataset(
        self,
        num_markets: int,
        output_path: str | Path | None = None,
        diverse: bool = True
    ) -> list[dict[str, Any]]:
        """
        Generate a dataset of markets with controlled diversity.

        Args:
            num_markets: Number of markets to generate
            output_path: Optional path to save JSON file
            diverse: If True, ensure all categories represented

        Returns:
            List of market dictionaries
        """
        markets = []

        if diverse and num_markets >= 6:
            # Ensure all categories are represented
            categories = list(self.chars.CATEGORIES.keys())

            # Generate at least one of each category
            for i, category in enumerate(categories):
                market = self.generate_market(i, category=category)
                markets.append(market)

            # Generate remaining markets randomly
            for i in range(len(categories), num_markets):
                market = self.generate_market(i)
                markets.append(market)
        else:
            # Pure random generation
            for i in range(num_markets):
                market = self.generate_market(i)
                markets.append(market)

        # Save to file if requested
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w") as f:
                json.dump(markets, f, indent=2)

            print(f"Generated {num_markets} markets -> {output_path}")
            self._print_dataset_summary(markets)

        return markets

    def _print_dataset_summary(self, markets: list[dict[str, Any]]) -> None:
        """Print summary statistics for generated dataset."""
        print("\n=== Dataset Summary ===")
        print(f"Total Markets: {len(markets)}")

        # Category distribution
        category_counts = {}
        for m in markets:
            cat = m["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1

        print("\nCategory Distribution:")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            pct = count / len(markets) * 100
            print(f"  {cat:12s}: {count:3d} ({pct:5.1f}%)")

        # Liquidity distribution
        liquidity_counts = {}
        for m in markets:
            tier = m["metadata"]["liquidity_tier"]
            liquidity_counts[tier] = liquidity_counts.get(tier, 0) + 1

        print("\nLiquidity Tiers:")
        for tier, count in sorted(liquidity_counts.items(), key=lambda x: -x[1]):
            pct = count / len(markets) * 100
            print(f"  {tier:12s}: {count:3d} ({pct:5.1f}%)")

        # Edge distribution
        edges = [m["metadata"]["edge"] for m in markets]
        avg_edge = sum(edges) / len(edges)
        min_edge = min(edges)
        max_edge = max(edges)

        print(f"\nEdge Statistics:")
        print(f"  Average: {avg_edge:.3f}")
        print(f"  Min:     {min_edge:.3f}")
        print(f"  Max:     {max_edge:.3f}")

        # Time to expiry
        times = [m["time_to_expiry_hours"] for m in markets]
        avg_time = sum(times) / len(times)

        print(f"\nTime to Expiry:")
        print(f"  Average: {avg_time:.1f} hours")
        print(f"  Min:     {min(times):.1f} hours")
        print(f"  Max:     {max(times):.1f} hours")

        # Outcome distribution
        outcomes = [m["outcome"] for m in markets]
        outcome_1_count = sum(outcomes)
        outcome_0_count = len(outcomes) - outcome_1_count

        print(f"\nOutcome Distribution:")
        print(f"  Outcome 1: {outcome_1_count:3d} ({outcome_1_count/len(outcomes)*100:5.1f}%)")
        print(f"  Outcome 0: {outcome_0_count:3d} ({outcome_0_count/len(outcomes)*100:5.1f}%)")


def main():
    """Generate standard datasets for AutoPredict."""
    base_path = Path(__file__).parent.parent / "datasets"

    # Create generator with seed for reproducibility
    generator = MarketGenerator(seed=42)

    # Generate 100-market dataset
    print("Generating 100-market dataset...")
    generator.generate_dataset(
        num_markets=100,
        output_path=base_path / "sample_markets_100.json",
        diverse=True
    )

    print("\n" + "="*50 + "\n")

    # Generate 500-market dataset
    print("Generating 500-market dataset...")
    generator.generate_dataset(
        num_markets=500,
        output_path=base_path / "sample_markets_500.json",
        diverse=True
    )

    print("\n" + "="*50 + "\n")

    # Generate minimal test dataset (10 markets)
    print("Generating minimal test dataset (10 markets)...")
    generator.generate_dataset(
        num_markets=10,
        output_path=base_path / "test_markets_minimal.json",
        diverse=True
    )

    print("\n" + "="*50)
    print("✓ All datasets generated successfully!")
    print(f"✓ Location: {base_path}")


if __name__ == "__main__":
    main()
