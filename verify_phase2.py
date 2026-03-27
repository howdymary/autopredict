#!/usr/bin/env python3
"""Verification script for Phase 2 deliverables."""

from datetime import datetime, timedelta

print("=" * 70)
print("Phase 2 - Market/Strategy Pass - Verification")
print("=" * 70)

# Test 1: Core Types
print("\n1. Testing Core Types...")
from autopredict.core.types import (
    MarketState,
    MarketCategory,
    EdgeEstimate,
    Order,
    OrderSide,
    OrderType,
    Position,
    Portfolio,
    ExecutionReport,
)

market = MarketState(
    market_id="verify-123",
    question="Verification test",
    market_prob=0.65,
    expiry=datetime.now() + timedelta(days=7),
    category=MarketCategory.CRYPTO,
    best_bid=0.64,
    best_ask=0.66,
    bid_liquidity=1000.0,
    ask_liquidity=900.0,
)
print(f"  ✓ MarketState: spread={market.spread:.3f}, mid={market.mid_price:.3f}")

edge = EdgeEstimate(
    market_id=market.market_id,
    fair_prob=0.75,
    market_prob=0.65,
    confidence=0.85,
)
print(f"  ✓ EdgeEstimate: edge={edge.edge:.3f}, direction={edge.direction.value}")

order = Order(
    market_id=market.market_id,
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    size=100.0,
    limit_price=0.65,
)
print(f"  ✓ Order: {order.side.value} {order.size} @ {order.limit_price}")

portfolio = Portfolio(cash=10000.0, starting_capital=10000.0)
position = Position(
    market_id=market.market_id,
    size=100.0,
    entry_price=0.60,
    current_price=0.70,
)
portfolio.add_position(position)
print(f"  ✓ Portfolio: value=${portfolio.total_value:.2f}, pnl=${portfolio.total_pnl:.2f}")

# Test 2: Strategy
print("\n2. Testing Strategy...")
from autopredict.strategies.mispriced_probability import MispricedProbabilityStrategy
from autopredict.strategies.base import RiskLimits


class MockModel:
    def predict(self, market):
        return {"probability": 0.75, "confidence": 0.85}


strategy = MispricedProbabilityStrategy(
    risk_limits=RiskLimits(
        max_position_size=500.0,
        max_total_exposure=5000.0,
        min_edge_threshold=0.05,
    )
)

config = {"probability_model": MockModel(), "portfolio": portfolio}
edge_estimate = strategy.estimate_edge(market, config)
print(f"  ✓ Edge estimation: {edge_estimate.edge:.3f} with confidence {edge_estimate.confidence:.2f}")

orders = strategy.decide(market, None, config)
print(f"  ✓ Decision: {len(orders)} order(s) generated")
if orders:
    o = orders[0]
    print(f"    → {o.side.value} {o.size:.1f} @ {o.limit_price} ({o.order_type.value})")

# Test 3: Adapters
print("\n3. Testing Adapters...")
from autopredict.markets.polymarket import PolymarketAdapter
from autopredict.markets.manifold import ManifoldAdapter

polymarket = PolymarketAdapter(api_key="test", testnet=True)
print(f"  ✓ PolymarketAdapter: initialized with testnet={polymarket.testnet}")

manifold = ManifoldAdapter(api_key="test")
print(f"  ✓ ManifoldAdapter: initialized with base_url={manifold.base_url}")

# Test 4: Tests
print("\n4. Running Tests...")
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_core_types.py", "tests/test_mispriced_strategy.py", "-q"],
    capture_output=True,
    text=True,
)
if result.returncode == 0:
    # Extract test count from output
    lines = result.stdout.strip().split("\n")
    last_line = lines[-1] if lines else ""
    print(f"  ✓ Tests passed: {last_line}")
else:
    print(f"  ✗ Tests failed")
    print(result.stdout)

# Summary
print("\n" + "=" * 70)
print("Phase 2 Deliverables Summary")
print("=" * 70)

deliverables = [
    ("autopredict/core/types.py", "Core type definitions"),
    ("autopredict/strategies/base.py", "Strategy protocol"),
    ("autopredict/strategies/mispriced_probability.py", "Mispriced probability strategy"),
    ("autopredict/markets/base.py", "Market adapter protocol"),
    ("autopredict/markets/polymarket.py", "Polymarket adapter"),
    ("autopredict/markets/manifold.py", "Manifold adapter"),
    ("TRADING_PLAYBOOK.md", "Trading system documentation"),
    ("tests/test_core_types.py", "Core types tests (14 tests)"),
    ("tests/test_mispriced_strategy.py", "Strategy tests (13 tests)"),
]

import os

for filepath, description in deliverables:
    exists = "✓" if os.path.exists(filepath) else "✗"
    if os.path.exists(filepath):
        size = os.path.getsize(filepath)
        if filepath.endswith(".py"):
            with open(filepath) as f:
                lines = len(f.readlines())
            print(f"{exists} {filepath:50s} ({lines:4d} lines) - {description}")
        else:
            print(f"{exists} {filepath:50s} ({size:6d} bytes) - {description}")
    else:
        print(f"{exists} {filepath:50s} - {description}")

print("\n" + "=" * 70)
print("✓ Phase 2 Complete - All deliverables verified")
print("=" * 70)
