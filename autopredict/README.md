# AutoPredict Package

Clean, strongly-typed abstractions for automated prediction market trading.

## Package Structure

```
autopredict/
├── core/               # Core type definitions
│   ├── __init__.py
│   └── types.py        # MarketState, Order, Position, Portfolio, etc.
│
├── strategies/         # Trading strategies
│   ├── __init__.py
│   ├── base.py         # Strategy protocol and RiskLimits
│   └── mispriced_probability.py  # First concrete strategy
│
└── markets/            # Market venue adapters
    ├── __init__.py
    ├── base.py         # MarketAdapter protocol
    ├── polymarket.py   # Polymarket CLOB integration
    └── manifold.py     # Manifold AMM integration
```

## Quick Start

### 1. Core Types

All strongly-typed dataclasses with comprehensive validation:

```python
from datetime import datetime, timedelta
from autopredict.core.types import (
    MarketState,
    MarketCategory,
    EdgeEstimate,
    Order,
    OrderSide,
    OrderType,
    Position,
    Portfolio,
)

# Create a market
market = MarketState(
    market_id="polymarket-123456",
    question="Will Bitcoin hit $100k in 2026?",
    market_prob=0.65,
    expiry=datetime.now() + timedelta(days=365),
    category=MarketCategory.CRYPTO,
    best_bid=0.64,
    best_ask=0.66,
    bid_liquidity=50000.0,
    ask_liquidity=45000.0,
)

# Access properties
print(f"Spread: {market.spread_bps:.0f} bps")
print(f"Mid: {market.mid_price:.2f}")
print(f"Time to expiry: {market.time_to_expiry_hours:.1f} hours")

# Create an edge estimate
edge = EdgeEstimate(
    market_id=market.market_id,
    fair_prob=0.75,
    market_prob=0.65,
    confidence=0.85,
)

print(f"Edge: {edge.edge:.1%}")
print(f"Direction: {edge.direction}")

# Create an order
order = Order(
    market_id=market.market_id,
    side=edge.direction,
    order_type=OrderType.LIMIT,
    size=100.0,
    limit_price=0.65,
    metadata={"strategy": "mispriced_probability"}
)

# Track position
position = Position(
    market_id=market.market_id,
    size=100.0,
    entry_price=0.65,
    current_price=0.70,
)

print(f"Unrealized PnL: ${position.unrealized_pnl:.2f}")

# Track portfolio
portfolio = Portfolio(
    cash=10000.0,
    starting_capital=10000.0,
)
portfolio.add_position(position)

print(f"Total value: ${portfolio.total_value:.2f}")
print(f"Total PnL: ${portfolio.total_pnl:.2f}")
```

### 2. Strategy Implementation

Implement the `Strategy` protocol:

```python
from autopredict.strategies.base import Strategy, RiskLimits
from autopredict.strategies.mispriced_probability import MispricedProbabilityStrategy

# Use built-in strategy
strategy = MispricedProbabilityStrategy(
    risk_limits=RiskLimits(
        max_position_size=500.0,
        max_total_exposure=5000.0,
        max_daily_loss=1000.0,
        min_edge_threshold=0.05,
        min_confidence=0.7,
    ),
    kelly_fraction=0.25,
)

# Estimate edge
edge = strategy.estimate_edge(market, {"probability_model": my_model})

# Make decision
orders = strategy.decide(market, position, {
    "probability_model": my_model,
    "portfolio": portfolio,
})

for order in orders:
    print(f"{order.side} {order.size} @ {order.limit_price}")
```

### 3. Market Adapters

Uniform interface for all venues:

```python
from autopredict.markets.polymarket import PolymarketAdapter
from autopredict.markets.manifold import ManifoldAdapter

# Polymarket (CLOB)
polymarket = PolymarketAdapter(
    api_key="your-api-key",
    private_key="your-private-key",
    testnet=True,
)

markets = polymarket.get_markets({"category": "politics"})
for market in markets:
    print(f"{market.question}: {market.market_prob:.1%}")

# Place order
report = polymarket.place_order(order)
print(f"Filled {report.filled_size} @ {report.avg_fill_price}")

# Manifold (AMM)
manifold = ManifoldAdapter(api_key="your-api-key")

markets = manifold.get_markets({"min_liquidity": 1000})
report = manifold.place_order(order)
```

## Design Principles

### 1. Strong Typing

All types are frozen dataclasses with comprehensive validation:

```python
@dataclass(frozen=True)
class MarketState:
    market_id: str
    question: str
    market_prob: float  # Validated: 0 <= prob <= 1
    # ... more fields

    def __post_init__(self):
        # Validate all invariants
        if not (0 <= self.market_prob <= 1):
            raise ValueError("Invalid probability")
```

### 2. Protocol-Based

Strategies and adapters use protocols, not inheritance:

```python
class Strategy(Protocol):
    def estimate_edge(self, market: MarketState, config: dict) -> EdgeEstimate | None:
        ...

    def decide(self, market: MarketState, position: Position | None, config: dict) -> list[Order]:
        ...
```

### 3. Immutability

Core decision objects are immutable (frozen dataclasses):

```python
# This works
market = MarketState(...)
print(market.spread)  # Computed property

# This fails
market.market_prob = 0.75  # Error: frozen dataclass
```

Mutable state is explicit:

```python
# Portfolio is mutable (position tracking)
portfolio.add_position(position)
portfolio.update_cash(-100.0)

# Position is mutable (price updates)
position.update_price(new_price)
```

### 4. Composability

All components are independently testable:

```python
# Test types in isolation
market = MarketState(...)
assert market.spread == 0.02

# Test strategy with mock model
class MockModel:
    def predict(self, market):
        return {"probability": 0.75, "confidence": 0.8}

strategy = MispricedProbabilityStrategy(...)
edge = strategy.estimate_edge(market, {"probability_model": MockModel()})
```

## Testing

Run tests:

```bash
# Core types
pytest tests/test_core_types.py -v

# Strategy
pytest tests/test_mispriced_strategy.py -v

# All
pytest tests/ -v
```

## Documentation

- **docs/STRATEGIES.md**: Strategy development guide
- **Core types**: Inline docstrings with examples
- **Strategies**: Protocol documentation with usage examples
- **Adapters**: API integration guides

## Next Steps

1. Implement API integration (Polymarket, Manifold)
2. Add more strategies (mean reversion, arbitrage)
3. Build backtesting harness using new types
4. Create CLI for live trading
5. Add position persistence (SQLite)
6. Build performance analytics

## Philosophy

**Trivial to add new strategies**: Implement the `Strategy` protocol

**Trivial to add new venues**: Implement the `MarketAdapter` protocol

**Trivial to test**: All components are independently testable with clear interfaces

**Impossible to misuse**: Strong typing prevents invalid states at compile time
