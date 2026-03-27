# AutoPredict Trading Playbook

## Overview

This playbook documents the end-to-end trading system for AutoPredict, from market analysis to order execution and risk management.

**Target Venues**: Polymarket (primary), Manifold Markets (testing)

**Core Strategy**: Mispriced Probability - trade when model probability differs from market probability

**Risk Controls**: Position limits, exposure limits, daily loss limits, kill switch

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Market Representation](#market-representation)
3. [Core Decision Flow](#core-decision-flow)
4. [Strategy: Mispriced Probability](#strategy-mispriced-probability)
5. [Risk Controls](#risk-controls)
6. [Venue Adapters](#venue-adapters)
7. [Order Execution](#order-execution)
8. [Position Management](#position-management)
9. [Performance Monitoring](#performance-monitoring)

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AutoPredict System                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Market Adapters (autopredict/markets/)              │  │
│  │  - Polymarket: CLOB with limit/market orders         │  │
│  │  - Manifold: AMM with instant execution              │  │
│  │  - Common interface: MarketAdapter protocol          │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                          │
│                 │ MarketState objects                      │
│                 ▼                                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Strategy Layer (autopredict/strategies/)            │  │
│  │  - MispricedProbabilityStrategy (first strategy)     │  │
│  │  - EdgeEstimate: fair_prob vs market_prob            │  │
│  │  - Position sizing: Kelly criterion with caps        │  │
│  │  - Order type selection: market vs limit             │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                          │
│                 │ Order objects                            │
│                 ▼                                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Risk Controls                                        │  │
│  │  - Max position per market                           │  │
│  │  - Max total exposure                                │  │
│  │  - Max daily loss (kill switch)                      │  │
│  │  - Min edge threshold                                │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                          │
│                 │ Validated orders                         │
│                 ▼                                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Execution Engine                                     │  │
│  │  - Route to appropriate venue                        │  │
│  │  - Handle fills and partial fills                    │  │
│  │  - Track execution quality (slippage, fees)          │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                          │
│                 │ ExecutionReport                          │
│                 ▼                                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Portfolio Management                                 │  │
│  │  - Track positions across venues                     │  │
│  │  - Calculate unrealized PnL                          │  │
│  │  - Aggregate risk metrics                            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Core Types

All core types are defined in `autopredict/core/types.py`:

- **MarketState**: Complete market snapshot (price, liquidity, expiry, etc.)
- **EdgeEstimate**: Fair prob vs market prob with confidence
- **Order**: Side, size, type, limit price
- **Position**: Holdings, entry price, unrealized PnL
- **Portfolio**: Cash + positions + total value
- **ExecutionReport**: Fill details, slippage, fees

---

## Market Representation

### MarketState

Markets are represented using the `MarketState` dataclass:

```python
@dataclass(frozen=True)
class MarketState:
    market_id: str              # Unique identifier (e.g., "polymarket-123456")
    question: str               # Human-readable question
    market_prob: float          # Market-implied probability (0-1)
    expiry: datetime            # Market resolution time
    category: MarketCategory    # POLITICS, SPORTS, CRYPTO, etc.

    # Liquidity
    best_bid: float             # Best bid price
    best_ask: float             # Best ask price
    bid_liquidity: float        # Liquidity on bid side
    ask_liquidity: float        # Liquidity on ask side

    # Additional data
    volume_24h: float           # 24-hour trading volume
    num_traders: int            # Number of unique traders
    metadata: dict              # Venue-specific data
```

### Key Properties

```python
market.spread                  # best_ask - best_bid
market.spread_bps              # Spread in basis points
market.mid_price               # (best_bid + best_ask) / 2
market.total_liquidity         # bid_liquidity + ask_liquidity
market.time_to_expiry_hours    # Hours until expiry
```

### Market Selection Criteria

**Minimum Requirements**:
- Total liquidity > $100
- Spread < 10% (unless edge > 15%)
- Time to expiry > 6 hours
- Category in supported list

**Quality Signals**:
- High volume/liquidity ratio (active market)
- Many unique traders (diverse opinions)
- Tight spread (efficient market)

---

## Core Decision Flow

### 1. Market Scan

```python
# Fetch markets from venue
markets = adapter.get_markets({
    "min_liquidity": 100.0,
    "active_only": True
})

# Filter by category and quality
markets = [m for m in markets if m.total_liquidity >= 100 and m.spread_bps < 1000]
```

### 2. Edge Estimation

```python
# Strategy estimates edge
edge = strategy.estimate_edge(market, config)

# EdgeEstimate contains:
# - fair_prob: Model's probability estimate
# - market_prob: Current market price
# - edge: fair_prob - market_prob
# - confidence: Model confidence (0-1)
```

### 3. Trade Decision

```python
# Strategy decides whether and how to trade
orders = strategy.decide(market, current_position, config)

# Returns list of Order objects (empty if no trade)
```

### 4. Risk Check

```python
# Apply risk limits before execution
for order in orders:
    # Check position limit
    if order.size > risk_limits.max_position_size:
        order.size = risk_limits.max_position_size

    # Check total exposure
    if portfolio.total_position_value + order.size > risk_limits.max_total_exposure:
        continue  # Skip this order

    # Check daily loss limit
    if portfolio.daily_pnl < -risk_limits.max_daily_loss:
        raise KillSwitchTriggered("Daily loss limit exceeded")
```

### 5. Execution

```python
# Execute order through venue adapter
report = adapter.place_order(order)

# ExecutionReport contains:
# - filled_size: Actual amount filled
# - avg_fill_price: VWAP fill price
# - slippage_bps: Slippage relative to mid
# - fee_total: Total fees paid
```

### 6. Position Update

```python
# Update portfolio with execution
position = Position(
    market_id=market.market_id,
    size=report.filled_size,
    entry_price=report.avg_fill_price,
    current_price=market.market_prob
)
portfolio.add_position(position)
portfolio.update_cash(-report.total_cost)
```

---

## Strategy: Mispriced Probability

### Overview

The Mispriced Probability strategy is the foundational strategy:

**Core Thesis**: Markets sometimes misprice probabilities due to:
- Limited information
- Emotional bias
- Liquidity constraints
- News lag

**Approach**:
1. Build probability model (ML, statistical, fundamental)
2. Compare model prob to market prob
3. Trade when edge exceeds threshold
4. Size using Kelly criterion
5. Exit when edge reverses

### Implementation

```python
from autopredict.strategies.mispriced_probability import MispricedProbabilityStrategy
from autopredict.strategies.base import RiskLimits

# Initialize strategy
strategy = MispricedProbabilityStrategy(
    risk_limits=RiskLimits(
        max_position_size=500.0,      # Max $500 per market
        max_total_exposure=5000.0,    # Max $5000 total
        max_daily_loss=1000.0,        # Kill switch at -$1000/day
        min_edge_threshold=0.05,      # Require 5% edge minimum
        min_confidence=0.7            # Require 70% confidence
    ),
    kelly_fraction=0.25,              # Use quarter-Kelly sizing
    aggressive_edge_threshold=0.15,  # Use market orders for 15%+ edge
    min_spread_capture=10.0          # Capture 10+ bps with limits
)
```

### Edge Estimation

```python
def estimate_edge(self, market: MarketState, config: dict) -> EdgeEstimate | None:
    # Get probability model from config
    model = config["probability_model"]

    # Generate forecast
    forecast = model.predict(market)
    fair_prob = forecast["probability"]
    confidence = forecast["confidence"]

    # Create edge estimate
    return EdgeEstimate(
        market_id=market.market_id,
        fair_prob=fair_prob,
        market_prob=market.market_prob,
        confidence=confidence
    )
```

### Position Sizing

Uses **Kelly Criterion** with safety caps:

```python
# Kelly fraction = edge / variance
# For binary outcomes:
#   Long: kelly = edge / (1 - fair_prob)
#   Short: kelly = -edge / fair_prob

# Apply fractional Kelly (0.25 = quarter-Kelly)
kelly = kelly * 0.25

# Calculate base size
base_size = portfolio.total_value * kelly

# Apply confidence scaling
base_size = base_size * edge.confidence

# Apply risk limits
size = min(
    base_size,
    risk_limits.max_position_size,
    risk_limits.max_total_exposure - portfolio.total_position_value
)

# Apply liquidity constraint (max 20% of available liquidity)
size = min(size, available_liquidity * 0.20)
```

### Order Type Selection

```python
def _choose_order_type(self, edge: EdgeEstimate, market: MarketState) -> OrderType:
    # Use market order for very large edges
    if edge.abs_edge >= 0.15:
        return OrderType.MARKET

    # Use market when edge/spread ratio is high
    edge_to_spread_ratio = edge.abs_edge / market.spread
    if edge_to_spread_ratio > 3.0:
        return OrderType.MARKET

    # Use market when time is short
    if market.time_to_expiry_hours < 12:
        return OrderType.MARKET

    # Default: limit orders to capture spread
    return OrderType.LIMIT
```

### Limit Price Calculation

```python
# Place limit inside spread for better fill probability
improvement_bps = 10.0

if side == OrderSide.BUY:
    # Improve bid by 10 bps toward mid
    improvement = market.mid_price * (10.0 / 10_000)
    limit_price = market.best_bid + improvement
    limit_price = min(limit_price, market.mid_price)
else:
    # Improve ask by 10 bps toward mid
    improvement = market.mid_price * (10.0 / 10_000)
    limit_price = market.best_ask - improvement
    limit_price = max(limit_price, market.mid_price)
```

---

## Risk Controls

### Position-Level Controls

```python
@dataclass
class RiskLimits:
    max_position_size: float = 500.0          # Max $500 per market
    max_total_exposure: float = 5000.0        # Max $5000 across all positions
    max_daily_loss: float = 1000.0            # Kill switch threshold
    max_leverage: float = 2.0                 # Max 2x leverage
    min_edge_threshold: float = 0.05          # Min 5% edge to trade
    min_confidence: float = 0.7               # Min 70% confidence to trade
```

### Pre-Trade Checks

Before executing any order:

```python
# 1. Check edge threshold
if edge.abs_edge < risk_limits.min_edge_threshold:
    return []  # Skip trade

# 2. Check confidence threshold
if edge.confidence < risk_limits.min_confidence:
    return []  # Skip trade

# 3. Check position size limit
if order.size > risk_limits.max_position_size:
    order.size = risk_limits.max_position_size

# 4. Check total exposure limit
if portfolio.total_position_value + order.size > risk_limits.max_total_exposure:
    return []  # Skip trade

# 5. Check leverage limit
if portfolio.leverage > risk_limits.max_leverage:
    return []  # Skip trade
```

### Kill Switch

```python
# Check daily PnL before each trade
if portfolio.daily_pnl < -risk_limits.max_daily_loss:
    # Trigger kill switch
    logger.critical(f"KILL SWITCH: Daily loss ${-portfolio.daily_pnl:.2f} exceeds limit ${risk_limits.max_daily_loss:.2f}")

    # Close all positions
    for position in portfolio.positions.values():
        exit_order = create_exit_order(position)
        adapter.place_order(exit_order)

    # Stop trading
    raise KillSwitchTriggered("Daily loss limit exceeded")
```

### Position Exit Conditions

```python
# Exit position if edge reverses
edge_threshold = risk_limits.min_edge_threshold * 0.5

if position.is_long and edge.edge < -edge_threshold:
    # Long position, but edge now favors short
    return create_exit_order(position)

if position.is_short and edge.edge > edge_threshold:
    # Short position, but edge now favors long
    return create_exit_order(position)
```

---

## Venue Adapters

### Polymarket Adapter

**Market Type**: CLOB (Central Limit Order Book)

**Currency**: USDC on Polygon

**Features**:
- Full order book with limit and market orders
- High liquidity markets (often $100k+)
- Professional traders
- Low fees (0.2% maker, 0.4% taker)

**API**: https://docs.polymarket.com/

```python
from autopredict.markets.polymarket import PolymarketAdapter

adapter = PolymarketAdapter(
    api_key="your-api-key",
    private_key="your-private-key",  # For signing transactions
    testnet=True  # Use testnet for safety
)

# Fetch markets
markets = adapter.get_markets({
    "category": "politics",
    "min_liquidity": 10000
})

# Place order
order = Order(
    market_id="polymarket-123456",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    size=100.0,
    limit_price=0.65
)
report = adapter.place_order(order)
```

### Manifold Adapter

**Market Type**: AMM (Automated Market Maker)

**Currency**: Mana (play money)

**Features**:
- Instant execution (no order book)
- Good for testing strategies
- Active community
- No real money at risk

**API**: https://docs.manifold.markets/api

```python
from autopredict.markets.manifold import ManifoldAdapter

adapter = ManifoldAdapter(api_key="your-api-key")

# Fetch markets
markets = adapter.get_markets({
    "min_liquidity": 1000,
    "binary_only": True
})

# Place bet (AMM, so always market order)
order = Order(
    market_id="manifold-abc123",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    size=100.0
)
report = adapter.place_order(order)
```

### Adding New Venues

To add a new venue, implement the `MarketAdapter` protocol:

```python
from autopredict.markets.base import MarketAdapter

class MyVenueAdapter:
    def get_markets(self, filters: dict | None = None) -> list[MarketState]:
        # Fetch and convert markets
        pass

    def get_market(self, market_id: str) -> MarketState | None:
        # Fetch specific market
        pass

    def place_order(self, order: Order) -> ExecutionReport:
        # Execute order
        pass

    def cancel_order(self, market_id: str, order_id: str) -> bool:
        # Cancel order
        pass

    def get_position(self, market_id: str) -> float:
        # Get current position
        pass

    def get_balance(self) -> float:
        # Get cash balance
        pass
```

---

## Order Execution

### Execution Flow

```python
# 1. Generate order from strategy
orders = strategy.decide(market, position, config)

# 2. Validate orders
for order in orders:
    validate_order(order, risk_limits, portfolio)

# 3. Execute through adapter
for order in orders:
    try:
        report = adapter.place_order(order)

        # 4. Check fill quality
        if report.fill_rate < 0.5:
            logger.warning(f"Low fill rate: {report.fill_rate:.1%}")

        if report.slippage_bps > 50:
            logger.warning(f"High slippage: {report.slippage_bps:.0f} bps")

        # 5. Update portfolio
        update_portfolio(portfolio, report)

    except Exception as e:
        logger.error(f"Order execution failed: {e}")
```

### Execution Metrics

Track these metrics for each execution:

```python
@dataclass(frozen=True)
class ExecutionReport:
    order: Order
    filled_size: float          # Actual fill
    avg_fill_price: float       # VWAP
    fills: list[tuple[float, float]]  # Individual fills
    slippage_bps: float         # Slippage vs mid
    fee_total: float            # Total fees
    timestamp: datetime

    @property
    def fill_rate(self) -> float:
        return self.filled_size / self.order.size

    @property
    def total_cost(self) -> float:
        return self.filled_size * self.avg_fill_price + self.fee_total
```

**Target Metrics**:
- Fill rate > 80% (market orders)
- Fill rate > 30% (limit orders)
- Slippage < 30 bps (market orders)
- Slippage < 10 bps (limit orders)

---

## Position Management

### Position Tracking

```python
@dataclass
class Position:
    market_id: str
    size: float              # Positive = long, negative = short
    entry_price: float
    current_price: float
    timestamp: datetime

    @property
    def unrealized_pnl(self) -> float:
        return self.size * (self.current_price - self.entry_price)

    @property
    def unrealized_pnl_pct(self) -> float:
        return (self.current_price - self.entry_price) / self.entry_price
```

### Portfolio Tracking

```python
@dataclass
class Portfolio:
    cash: float
    positions: dict[str, Position]
    starting_capital: float

    @property
    def total_value(self) -> float:
        return self.cash + sum(pos.unrealized_pnl for pos in self.positions.values())

    @property
    def total_pnl(self) -> float:
        return self.total_value - self.starting_capital

    @property
    def leverage(self) -> float:
        position_value = sum(pos.notional for pos in self.positions.values())
        return position_value / self.total_value
```

### Position Updates

```python
# After execution
def update_portfolio(portfolio: Portfolio, report: ExecutionReport):
    market_id = report.order.market_id

    # Get or create position
    position = portfolio.positions.get(market_id)

    if position is None:
        # New position
        position = Position(
            market_id=market_id,
            size=report.filled_size if report.order.side == OrderSide.BUY else -report.filled_size,
            entry_price=report.avg_fill_price,
            current_price=report.avg_fill_price
        )
    else:
        # Add to existing position
        # Recalculate average entry price
        old_notional = position.size * position.entry_price
        new_notional = report.filled_size * report.avg_fill_price
        total_size = position.size + report.filled_size

        position.entry_price = (old_notional + new_notional) / total_size
        position.size = total_size

    portfolio.positions[market_id] = position
    portfolio.update_cash(-report.total_cost)
```

---

## Performance Monitoring

### Key Metrics

**Epistemic Quality**:
- Brier score: Mean squared error of probabilities
- Calibration: Are 70% predictions correct 70% of the time?
- Log score: Logarithmic scoring rule

**Financial Performance**:
- Total PnL: Net profit/loss
- Sharpe ratio: Risk-adjusted returns
- Max drawdown: Largest peak-to-trough decline
- Win rate: Fraction of profitable trades

**Execution Quality**:
- Average slippage (bps)
- Fill rate (%)
- Spread capture (bps, for limit orders)
- Market impact (bps)

### Monitoring Dashboard

Track these in real-time:

```python
# Daily metrics
{
    "date": "2026-03-26",
    "total_pnl": 250.50,
    "daily_pnl": 45.20,
    "num_trades": 12,
    "win_rate": 0.667,
    "avg_slippage_bps": 18.5,
    "sharpe_ratio": 1.85,
    "max_drawdown": 0.15,
    "current_positions": 5,
    "total_exposure": 2340.00,
    "leverage": 1.2
}
```

### Alerts

Set up alerts for:
- Daily loss approaching limit (80% of max_daily_loss)
- High slippage (> 50 bps)
- Low fill rates (< 50%)
- Large drawdown (> 20%)
- Unusual position concentration (> 30% in one market)

---

## Usage Example

```python
from autopredict.core.types import Portfolio
from autopredict.markets.polymarket import PolymarketAdapter
from autopredict.strategies.mispriced_probability import MispricedProbabilityStrategy
from autopredict.strategies.base import RiskLimits

# 1. Initialize components
adapter = PolymarketAdapter(api_key="...", testnet=True)
strategy = MispricedProbabilityStrategy(
    risk_limits=RiskLimits(
        max_position_size=500.0,
        max_total_exposure=5000.0,
        max_daily_loss=1000.0
    )
)
portfolio = Portfolio(cash=10000.0, starting_capital=10000.0)

# 2. Fetch markets
markets = adapter.get_markets({"min_liquidity": 1000})

# 3. For each market
for market in markets:
    # Get current position (if any)
    position_size = adapter.get_position(market.market_id)
    position = portfolio.positions.get(market.market_id)

    # Generate orders
    config = {
        "probability_model": my_model,
        "portfolio": portfolio
    }
    orders = strategy.decide(market, position, config)

    # Execute orders
    for order in orders:
        # Apply risk checks
        if portfolio.daily_pnl < -1000:
            break  # Kill switch

        # Execute
        report = adapter.place_order(order)

        # Update portfolio
        update_portfolio(portfolio, report)

        # Log
        logger.info(f"Executed {order.side} {order.size} @ {report.avg_fill_price}")

# 4. Monitor performance
print(f"Total PnL: ${portfolio.total_pnl:.2f}")
print(f"Win rate: {calculate_win_rate(portfolio):.1%}")
```

---

## Next Steps

### Immediate (Phase 2 Complete)
- [x] Core types defined
- [x] Strategy protocol defined
- [x] Market adapter protocol defined
- [x] Mispriced probability strategy implemented
- [x] Polymarket adapter scaffolded
- [x] Manifold adapter scaffolded
- [x] Risk controls documented

### Near-term (Phase 3)
- [ ] Implement Polymarket API integration
- [ ] Implement Manifold API integration
- [ ] Add portfolio persistence (SQLite)
- [ ] Add performance analytics
- [ ] Create backtesting harness using new types
- [ ] Build CLI for live trading

### Medium-term
- [ ] Add more strategies (mean reversion, arbitrage)
- [ ] Implement limit order management
- [ ] Add position rebalancing
- [ ] Build web dashboard
- [ ] Add alerting system

### Long-term
- [ ] Multi-venue arbitrage
- [ ] Advanced order types (iceberg, TWAP)
- [ ] Machine learning for edge estimation
- [ ] Automated parameter tuning
