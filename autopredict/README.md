# AutoPredict Package

Core library for prediction market trading agents.

## Package Structure

```
autopredict/
├── core/               # Core type definitions
│   ├── __init__.py
│   └── types.py        # MarketState, Order, Position, Portfolio
│
├── strategies/         # Trading strategies
│   ├── __init__.py
│   ├── base.py         # Strategy protocol and RiskLimits
│   └── mispriced_probability.py  # Mispriced probability strategy
│
├── markets/            # Market venue adapters
│   ├── __init__.py
│   ├── base.py         # MarketAdapter protocol
│   └── polymarket.py   # Polymarket Gamma + CLOB integration
│
├── backtest/           # Backtesting engine
├── learning/           # Parameter tuning (GridSearchTuner)
├── live/               # Live trading (PaperTrader, RiskManager, Monitor)
└── config/             # Configuration loading
```

## Market Adapter

The Polymarket adapter connects to real APIs (no auth needed for reads):

```python
from autopredict.markets.polymarket import PolymarketAdapter

adapter = PolymarketAdapter()

# Fetch live markets
markets = adapter.get_active_markets(limit=50, min_liquidity=5000)
for m in markets:
    print(f"{m.question}: {m.market_prob:.1%} (spread={m.spread:.3f})")

# Fetch real order book from CLOB
book = adapter.get_order_book(m.token_id_yes)
print(f"Bids: {len(book['bids'])} levels, Asks: {len(book['asks'])} levels")

# Convert to agent format with your fair_prob
state = adapter.to_agent_market_state(m, fair_prob=0.65)
```

## Strategy Protocol

Strategies implement `estimate_edge()` and `decide()`:

```python
from autopredict.strategies.mispriced_probability import MispricedProbabilityStrategy
from autopredict.strategies.base import RiskLimits

strategy = MispricedProbabilityStrategy(
    risk_limits=RiskLimits(
        max_position_size=500.0,
        max_total_exposure=5000.0,
        min_edge_threshold=0.05,
    ),
)
```

## Testing

```bash
pytest tests/ -v
```
