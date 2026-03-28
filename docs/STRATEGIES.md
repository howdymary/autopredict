# Strategy Development Guide

Complete guide to developing, testing, and deploying custom trading strategies in AutoPredict.

## Table of Contents

1. [Overview](#overview)
2. [Strategy Anatomy](#strategy-anatomy)
3. [Available Market Data](#available-market-data)
4. [Creating Your First Strategy](#creating-your-first-strategy)
5. [Example Strategies](#example-strategies)
6. [Testing and Validation](#testing-and-validation)
7. [Advanced Patterns](#advanced-patterns)
8. [Performance Optimization](#performance-optimization)

## Overview

AutoPredict strategies are Python classes that implement trading logic for prediction markets. A strategy receives market snapshots and decides:

1. **Whether** to trade (opportunity detection)
2. **What side** to take (buy YES or buy NO)
3. **How much** to risk (position sizing)
4. **How** to execute (market vs limit orders)

The framework separates **what is fixed** (market simulation, metrics) from **what evolves** (your strategy). This design enables rapid iteration without breaking the evaluation harness.

### Strategy Design Principles

- **Stateless**: Each decision is independent (no memory between markets)
- **Configurable**: All tuning knobs live in JSON config files
- **Testable**: Every change can be validated via backtest in seconds
- **Measurable**: Performance tracked across 3 dimensions (epistemic, financial, execution)

## Strategy Anatomy

Every AutoPredict strategy consists of three components:

### 1. AgentConfig (strategy_configs/*.json)

Tunable parameters that control strategy behavior:

```json
{
  "name": "my_strategy_v1",
  "min_edge": 0.05,
  "aggressive_edge": 0.12,
  "max_risk_fraction": 0.02,
  "max_position_notional": 25.0,
  "min_book_liquidity": 60.0,
  "max_spread_pct": 0.04,
  "max_depth_fraction": 0.15,
  "split_threshold_fraction": 0.25
}
```

### 2. AutoPredictAgent (agent.py)

Core decision-making logic:

```python
class AutoPredictAgent:
    def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
        """Main decision point: should we trade this market?"""
        # 1. Calculate edge
        # 2. Check gating rules
        # 3. Decide order type
        # 4. Calculate position size
        # 5. Return order or None
```

### 3. ExecutionStrategy (agent.py)

Order type selection and sizing logic:

```python
class ExecutionStrategy:
    def decide_order_type(self, edge, spread_pct, ...) -> str:
        """Choose 'market' or 'limit' based on edge/spread ratio"""

    def calculate_trade_size(self, edge, bankroll, ...) -> float:
        """Scale position by edge, subject to risk limits"""
```

## Available Market Data

Each market snapshot provides:

```python
@dataclass
class MarketState:
    market_id: str                    # Unique identifier
    market_prob: float                # Current market price (0-1)
    fair_prob: float                  # Your forecast (0-1)
    time_to_expiry_hours: float       # Hours until resolution
    order_book: OrderBook             # Bids/asks with depth
    metadata: dict[str, Any]          # Optional context
```

### Derived Quantities

You can calculate additional features:

```python
# Edge (directional)
edge = market.fair_prob - market.market_prob
abs_edge = abs(edge)

# Order book metrics
spread = market.order_book.get_spread()
spread_pct = spread / market.order_book.get_mid_price()
total_liquidity = market.order_book.get_total_depth()
best_bid = market.order_book.get_best_bid()
best_ask = market.order_book.get_best_ask()

# Time features
time_urgency = 1.0 / max(market.time_to_expiry_hours, 1.0)

# Edge quality
edge_to_spread_ratio = abs_edge / max(spread_pct, 0.001)
```

## Creating Your First Strategy

Let's build a simple "mispriced probability" strategy step by step.

### Step 1: Define Your Hypothesis

**Hypothesis**: Markets with large edge (>10%) and tight spreads (<2%) offer high-quality opportunities.

### Step 2: Create Config File

Create `strategy_configs/mispriced_v1.json`:

```json
{
  "name": "mispriced_v1",
  "min_edge": 0.10,
  "aggressive_edge": 0.20,
  "max_risk_fraction": 0.015,
  "max_position_notional": 20.0,
  "min_book_liquidity": 100.0,
  "max_spread_pct": 0.02,
  "max_depth_fraction": 0.10,
  "split_threshold_fraction": 0.20
}
```

**Key changes from baseline**:
- Increased `min_edge` from 0.05 to 0.10 (only high-conviction trades)
- Decreased `max_spread_pct` from 0.04 to 0.02 (only tight spreads)
- Increased `min_book_liquidity` from 60 to 100 (only deep books)

### Step 3: Override Agent Logic (Optional)

For simple strategies, config changes are enough. For custom logic, edit `agent.py`:

```python
def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
    """Custom mispriced probability strategy."""

    # Calculate edge
    edge = market.fair_prob - market.market_prob
    abs_edge = abs(edge)

    # Skip if edge too small
    if abs_edge < self.config.min_edge:
        return None

    # CUSTOM LOGIC: Require both large edge AND tight spread
    spread_pct = market.order_book.get_spread() / market.order_book.get_mid_price()
    if abs_edge < 0.10 or spread_pct > 0.02:
        return None  # Skip unless BOTH conditions met

    # Rest of logic remains the same
    side = "buy" if edge > 0 else "sell"
    order_type = self.execution_strategy.decide_order_type(...)
    size = self.execution_strategy.calculate_trade_size(...)

    return ProposedOrder(side=side, order_type=order_type, size=size, ...)
```

### Step 4: Backtest

```bash
python -m autopredict.cli backtest --config strategy_configs/mispriced_v1.json
```

### Step 5: Analyze Results

Compare metrics to baseline:

| Metric | Baseline | Mispriced v1 | Change |
|--------|----------|--------------|--------|
| Sharpe | 2.44 | 3.12 | +28% |
| Brier | 0.189 | 0.175 | Better |
| Slippage | 55 bps | 12 bps | Much better |
| Trades | 59 | 18 | Fewer (expected) |

**Interpretation**: Strategy is more selective (18 vs 59 trades), resulting in better execution quality (12 vs 55 bps slippage) and higher risk-adjusted returns (3.12 vs 2.44 Sharpe).

## Example Strategies

### 1. Mispriced Probability Strategy

**Goal**: Exploit markets where fair_prob significantly differs from market_prob

**Logic**:
- Only trade if `abs(edge) >= 10%`
- Prefer limit orders to capture spread
- Scale position size linearly with edge

**Config**:
```json
{
  "min_edge": 0.10,
  "aggressive_edge": 0.25,
  "max_spread_pct": 0.03,
  "max_risk_fraction": 0.02
}
```

**When to use**: When you have high-confidence probability estimates (e.g., from statistical models)

### 2. Momentum Strategy

**Goal**: Capitalize on markets moving in a consistent direction

**Logic**:
- Track recent price changes
- Buy if price moving toward your fair_prob
- Use market orders for speed

**Implementation** (requires state tracking):

```python
class MomentumAgent(AutoPredictAgent):
    def __init__(self, config):
        super().__init__(config)
        self.price_history = {}  # market_id -> [prices]

    def evaluate_market(self, market, bankroll):
        # Track price history
        if market.market_id not in self.price_history:
            self.price_history[market.market_id] = []

        self.price_history[market.market_id].append(market.market_prob)
        history = self.price_history[market.market_id][-5:]  # Last 5 snapshots

        if len(history) < 3:
            return None  # Need history

        # Calculate momentum
        momentum = history[-1] - history[0]
        edge = market.fair_prob - market.market_prob

        # Only trade if momentum aligns with edge
        if (momentum > 0 and edge > 0) or (momentum < 0 and edge < 0):
            # Momentum confirms edge - use market order
            return ProposedOrder(
                side="buy" if edge > 0 else "sell",
                order_type="market",
                size=self._calculate_size(abs(edge), bankroll)
            )

        return None
```

**When to use**: When markets exhibit trending behavior

### 3. Mean Reversion Strategy

**Goal**: Buy when market overreacts, expecting reversion to fair value

**Logic**:
- Identify markets with extreme spread
- Assume market will revert toward fair_prob
- Use limit orders to capture spread

**Config**:
```json
{
  "min_edge": 0.05,
  "aggressive_edge": 0.30,
  "max_spread_pct": 0.10,
  "max_risk_fraction": 0.01
}
```

**Custom logic**:
```python
def evaluate_market(self, market, bankroll):
    edge = market.fair_prob - market.market_prob
    abs_edge = abs(edge)

    spread_pct = market.order_book.get_spread() / market.order_book.get_mid_price()

    # Only trade if spread is wide (overreaction signal)
    if spread_pct < 0.05:
        return None

    # Use limit orders to capture mean reversion
    side = "buy" if edge > 0 else "sell"
    limit_price = market.order_book.get_mid_price()  # Midpoint

    return ProposedOrder(
        side=side,
        order_type="limit",
        size=self._calculate_size(abs_edge, bankroll),
        limit_price=limit_price
    )
```

**When to use**: When markets exhibit overshooting followed by correction

### 4. Liquidity-Weighted Strategy

**Goal**: Only trade markets with deep liquidity to minimize impact

**Logic**:
- Calculate liquidity score for each market
- Scale position size by available depth
- Reject thin markets entirely

**Config**:
```json
{
  "min_edge": 0.03,
  "min_book_liquidity": 200.0,
  "max_depth_fraction": 0.05
}
```

**When to use**: When trading large positions or when execution quality is paramount

### 5. Time-Decay Strategy

**Goal**: Adjust aggressiveness based on time to expiry

**Logic**:
- Near expiry: use market orders (urgency)
- Far from expiry: use limit orders (patience)
- Scale position size by time urgency

**Implementation**:
```python
def decide_order_type(self, edge, spread_pct, time_to_expiry_hours, ...):
    """Choose order type based on time urgency."""

    # Calculate time urgency (higher near expiry)
    time_urgency = 1.0 / max(time_to_expiry_hours, 1.0)

    # Use market orders if time is running out
    if time_urgency > 0.1 and edge > self.config.min_edge:
        return "market"

    # Otherwise use limit orders
    edge_to_spread_ratio = edge / max(spread_pct, 0.001)
    if edge_to_spread_ratio >= 3.0 and edge >= self.config.aggressive_edge:
        return "market"

    return "limit"
```

**When to use**: When market timing is critical

## Testing and Validation

### Backtest Workflow

1. **Create config file**
2. **Run backtest**
3. **Analyze metrics**
4. **Iterate**

```bash
# Run backtest
python -m autopredict.cli backtest --config strategy_configs/my_strategy.json

# View results
python -m autopredict.cli score-latest

# Compare to baseline
python -m autopredict.cli backtest --config strategy_configs/baseline.json
```

### Key Metrics to Track

**For strategy selection**:
- **Sharpe ratio**: Risk-adjusted returns (target: >1.0)
- **Max drawdown**: Worst loss (target: <50%)
- **Win rate**: Fraction of winning trades (target: >50%)

**For forecast quality**:
- **Brier score**: Forecast accuracy (target: <0.20)
- **Calibration**: Are 60% forecasts right 60% of the time?

**For execution quality**:
- **Slippage**: Execution cost (target: <20 bps)
- **Fill rate**: Order completion (target: >0.5)

### Common Pitfalls

#### 1. Overfitting to Sample Data

**Problem**: Strategy performs well on your dataset but fails on new data

**Solution**:
- Test on multiple datasets
- Use walk-forward testing
- Avoid tuning parameters to specific markets

```bash
# Generate new test dataset
# Collect real market data via predict.py or the Polymarket adapter

# Test on new data
python -m autopredict.cli backtest --dataset datasets/test_markets.json
```

#### 2. Ignoring Execution Costs

**Problem**: Strategy looks profitable but slippage eats all gains

**Solution**:
- Monitor `avg_slippage_bps` metric
- Prefer limit orders when edge allows
- Avoid thin markets (increase `min_book_liquidity`)

#### 3. Position Sizing Too Aggressive

**Problem**: Large drawdowns despite good Sharpe

**Solution**:
- Reduce `max_risk_fraction`
- Reduce `max_depth_fraction`
- Add position limits per market

#### 4. Not Enough Trades

**Problem**: Only 5 trades executed, high variance in results

**Solution**:
- Reduce `min_edge` threshold
- Increase `max_spread_pct` tolerance
- Reduce `min_book_liquidity` requirement

### Validation Checklist

Before deploying a strategy:

- [ ] Backtested on at least 50 markets
- [ ] Sharpe ratio > 1.0
- [ ] Brier score < 0.25
- [ ] Max drawdown < 50%
- [ ] Avg slippage < 30 bps
- [ ] Fill rate > 0.4
- [ ] At least 20 trades executed
- [ ] Win rate > 45%
- [ ] Tested on multiple datasets
- [ ] Parameters not overfit to specific markets

## Advanced Patterns

### Multi-Signal Strategies

Combine multiple signals for higher confidence:

```python
def evaluate_market(self, market, bankroll):
    # Signal 1: Edge
    edge = market.fair_prob - market.market_prob
    edge_signal = abs(edge) > 0.08

    # Signal 2: Liquidity
    liquidity = market.order_book.get_total_depth()
    liquidity_signal = liquidity > 150.0

    # Signal 3: Spread
    spread_pct = market.order_book.get_spread() / market.order_book.get_mid_price()
    spread_signal = spread_pct < 0.03

    # Require ALL signals
    if not (edge_signal and liquidity_signal and spread_signal):
        return None

    # All signals confirmed - proceed with trade
    return self._build_order(edge, market, bankroll)
```

### Conditional Position Sizing

Scale position size based on multiple factors:

```python
def calculate_trade_size(self, edge, bankroll, spread_pct, liquidity):
    """Dynamic position sizing based on opportunity quality."""

    # Base size (fraction of bankroll)
    base_fraction = self.config.max_risk_fraction

    # Scale by edge (higher edge = larger size)
    edge_multiplier = min(edge / 0.05, 3.0)  # Cap at 3x

    # Scale by spread quality (tighter = larger)
    spread_multiplier = 1.0 if spread_pct < 0.02 else 0.5

    # Scale by liquidity (more = larger)
    liquidity_multiplier = min(liquidity / 100.0, 2.0)  # Cap at 2x

    # Combined multiplier
    total_multiplier = edge_multiplier * spread_multiplier * liquidity_multiplier

    # Final size
    size = bankroll * base_fraction * total_multiplier

    # Apply hard caps
    size = min(size, self.config.max_position_notional)

    return size
```

### Category-Specific Logic

Different logic for different market categories:

```python
def evaluate_market(self, market, bankroll):
    category = market.metadata.get("category", "unknown")

    if category == "politics":
        # Politics: require higher edge (more noise)
        min_edge = 0.12
    elif category == "sports":
        # Sports: accept lower edge (more predictable)
        min_edge = 0.06
    elif category == "economics":
        # Economics: very high edge required (hard to forecast)
        min_edge = 0.15
    else:
        min_edge = self.config.min_edge

    edge = abs(market.fair_prob - market.market_prob)
    if edge < min_edge:
        return None

    # ... rest of logic
```

## Performance Optimization

### Profiling Your Strategy

Identify bottlenecks:

```bash
python -m cProfile -o profile.stats run_experiment.py
python -m pstats profile.stats
> sort cumulative
> stats 20
```

### Common Optimizations

1. **Cache derived quantities**:
```python
@cached_property
def spread_pct(self):
    return self.order_book.get_spread() / self.order_book.get_mid_price()
```

2. **Avoid redundant calculations**:
```python
# Bad
if abs(fair_prob - market_prob) > 0.05:
    edge = fair_prob - market_prob

# Good
edge = fair_prob - market_prob
if abs(edge) > 0.05:
    # use edge
```

3. **Use numpy for bulk operations** (if using custom datasets):
```python
import numpy as np

edges = np.array([m["fair_prob"] - m["market_prob"] for m in markets])
valid_markets = markets[np.abs(edges) > 0.05]
```

## Next Steps

- Read **BACKTESTING.md** to learn how to run comprehensive backtests
- Read **LEARNING.md** to understand how to tune strategies using performance feedback
- Read **DEPLOYMENT.md** for production deployment guidelines
- Explore **examples/** directory for real implementations

## Strategy Template

Use this template to create new strategies:

```python
# strategy_configs/my_strategy.json
{
  "name": "my_strategy_v1",
  "min_edge": 0.05,
  "aggressive_edge": 0.12,
  "max_risk_fraction": 0.02,
  "max_position_notional": 25.0,
  "min_book_liquidity": 60.0,
  "max_spread_pct": 0.04,
  "max_depth_fraction": 0.15
}
```

```python
# agent.py (if custom logic needed)
def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
    """
    Custom strategy logic.

    Args:
        market: Market snapshot with price, book, metadata
        bankroll: Current capital available

    Returns:
        ProposedOrder if opportunity detected, None otherwise
    """

    # 1. Calculate edge
    edge = market.fair_prob - market.market_prob
    abs_edge = abs(edge)

    # 2. Apply gating rules
    if abs_edge < self.config.min_edge:
        return None

    # 3. YOUR CUSTOM LOGIC HERE
    # Example: Check custom conditions
    spread_pct = market.order_book.get_spread() / market.order_book.get_mid_price()
    if not self._passes_quality_checks(abs_edge, spread_pct, market):
        return None

    # 4. Decide order type
    order_type = self.execution_strategy.decide_order_type(
        edge=abs_edge,
        spread_pct=spread_pct,
        time_to_expiry_hours=market.time_to_expiry_hours,
        total_liquidity=market.order_book.get_total_depth()
    )

    # 5. Calculate position size
    size = self.execution_strategy.calculate_trade_size(
        edge=abs_edge,
        bankroll=bankroll,
        spread_pct=spread_pct,
        available_depth=market.order_book.get_total_depth()
    )

    # 6. Build and return order
    side = "buy" if edge > 0 else "sell"
    return ProposedOrder(
        side=side,
        order_type=order_type,
        size=size,
        limit_price=self._calculate_limit_price(market, side) if order_type == "limit" else None
    )

def _passes_quality_checks(self, edge, spread_pct, market) -> bool:
    """Custom quality checks."""
    # Add your conditions here
    return True
```

**Run it**:
```bash
python -m autopredict.cli backtest --config strategy_configs/my_strategy.json
```
