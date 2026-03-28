# AutoPredict Architecture

AutoPredict is a minimal, modular framework for building self-improving prediction market agents. It separates concerns cleanly: fixed environment primitives, mutable agent strategy, and configuration-driven tuning.

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     AutoPredict System                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  CLI Layer (cli.py)                                  │  │
│  │  - backtest: Run experiment loop                     │  │
│  │  - score-latest: Retrieve latest metrics            │  │
│  │  - trade-live: [intentionally disabled]             │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                          │
│  ┌──────────────▼───────────────────────────────────────┐  │
│  │  Experiment Loop (run_experiment.py)                 │  │
│  │  - Load config + dataset                             │  │
│  │  - Iterate over market snapshots                     │  │
│  │  - Collect forecasts + trades                        │  │
│  │  - Evaluate with metrics                             │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                          │
│  ┌──────────────┴─────────────────────────────────────┐   │
│  │                                                    │   │
│  ▼                                                    ▼   │
│  ┌──────────────────────┐      ┌──────────────────────┐  │
│  │   Agent Layer        │      │  Market Environment  │  │
│  │   (agent.py)         │      │  (market_env.py)     │  │
│  │                      │      │                      │  │
│  │ AutoPredictAgent     │      │ ExecutionEngine      │  │
│  │ ├─ evaluate_market   │      │ ├─ market_order      │  │
│  │ ├─ analyze_perf      │      │ ├─ limit_order       │  │
│  │ └─ propose_improv    │      │ └─ calc_metrics      │  │
│  │                      │      │                      │  │
│  │ ExecutionStrategy    │      │ OrderBook            │  │
│  │ ├─ order_type        │      │ ├─ walk_book         │  │
│  │ ├─ trade_size        │      │ ├─ mid_price         │  │
│  │ └─ split_order       │      │ └─ impact_estimate   │  │
│  │                      │      │                      │  │
│  │ AgentConfig          │      │ Metrics             │  │
│  │ └─ tunable knobs     │      │ ├─ slippage          │  │
│  │   (JSON-driven)      │      │ ├─ fill_rate         │  │
│  │                      │      │ └─ drawdown          │  │
│  └──────────────────────┘      └──────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Configuration                                        │  │
│  │  - strategy_configs/{name}.json (AgentConfig)        │  │
│  │  - strategy.md (human guidance)                      │  │
│  │  - config.json (experiment paths)                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### Backtest Execution

```
Market Snapshot (JSON)
  │
  ├─ market_id, market_prob, fair_prob
  ├─ time_to_expiry_hours
  ├─ order_book (bids, asks)
  └─ outcome [after market resolves]
  │
  ▼
┌─────────────────────────────────────┐
│ MarketState (normalized)            │
│ - fair_prob vs market_prob edge      │
│ - time to expiry                     │
│ - order book depth & spread          │
└─────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────┐
│ AutoPredictAgent.evaluate_market()  │
│ ├─ Check gating rules               │
│ │  ├─ min_edge exceeded?            │
│ │  ├─ liquidity sufficient?          │
│ │  └─ spread acceptable?             │
│ ├─ Calculate order_type              │
│ │  ├─ edge vs spread ratio           │
│ │  ├─ time urgency                   │
│ │  └─ liquidity quality              │
│ ├─ Calculate trade size              │
│ │  ├─ edge scaling                   │
│ │  ├─ risk limits (% bankroll)       │
│ │  └─ depth limits (% visible)       │
│ └─ Return ProposedOrder or None      │
└─────────────────────────────────────┘
  │
  ├─ None: Skip market (no edge)
  │
  └─ ProposedOrder
     │
     ├─ market order?
     │  └─ side, size
     │
     └─ limit order?
        └─ side, size, limit_price
        │
        └─ Optionally split into N slices
  │
  ▼
┌─────────────────────────────────────┐
│ ExecutionEngine.execute_{type}()    │
│ ├─ Walk order book                  │
│ ├─ Calculate fills                  │
│ ├─ Measure slippage                 │
│ └─ Return ExecutionReport           │
└─────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────┐
│ TradeRecord                         │
│ - filled_size, fill_price           │
│ - slippage_bps, fill_rate           │
│ - realized outcome, pnl             │
└─────────────────────────────────────┘
  │
  ▼
  Aggregate into metrics
  - Brier score (epistemic)
  - PnL, Sharpe, max drawdown (financial)
  - Slippage, spread capture (execution)
```

## Component Details

### Agent Layer (agent.py)

**Purpose**: Decision-making logic for when and how to trade

**Key Classes**:

1. **AgentConfig**
   - Tunable parameters (JSON-driven)
   - All numeric knobs for order selection
   - Example: `min_edge=0.05` means "skip if edge < 5%"

2. **ExecutionStrategy**
   - `decide_order_type()`: Market vs limit based on edge/spread ratio
   - `calculate_trade_size()`: Scale by edge, risk limits, depth
   - `should_split_order()`: Detect oversized orders
   - `split_order()`: Create TWAP-like schedule

3. **AutoPredictAgent**
   - `evaluate_market()`: Main decision point
   - `analyze_performance()`: Identify dominant weakness
   - `propose_improvement()`: Lightweight next-iteration hint

**Design Principle**: Agent is *mutable by design*. Every method is simple and overridable.

### Market Environment (market_env.py)

**Purpose**: Fixed simulation primitives for testing agent logic

**Key Classes**:

1. **OrderBook**
   - `get_spread()`: Best ask - best bid
   - `get_mid_price()`: (bid + ask) / 2
   - `get_total_depth()`: Sum of visible liquidity
   - `walk_book()`: Consume depth from opposite side
   - `estimate_market_impact()`: Simulate fill scenario

2. **ExecutionEngine**
   - Simulates market order execution (immediate, walks book)
   - Simulates limit order execution (probabilistic passive fill)
   - Returns `ExecutionReport` with slippage, fill_rate, impact

3. **Metrics Functions**
   - `evaluate_all()`: Combine epistemic + financial + execution
   - Brier score from forecasts
   - PnL-based Sharpe, drawdown
   - Slippage, fill rate, spread capture

**Design Principle**: Environment is *immutable*. No business logic, only mechanics.

## Configuration Schema

### strategy_configs/{name}.json

Configures the AgentConfig for one experiment:

```json
{
  "name": "baseline_execution_aware",
  "min_edge": 0.05,
  "aggressive_edge": 0.12,
  "max_risk_fraction": 0.02,
  "max_position_notional": 25.0,
  "min_book_liquidity": 60.0,
  "max_spread_pct": 0.04,
  "max_depth_fraction": 0.15,
  "split_threshold_fraction": 0.25,
  "passive_requote_fraction": 0.25
}
```

**Key Knobs**:
- `min_edge`: Minimum edge (prob units) to consider a trade
- `aggressive_edge`: Threshold for using market orders
- `max_risk_fraction`: Max loss per trade as % of bankroll
- `max_position_notional`: Hard cap per order ($)
- `min_book_liquidity`: Min total visible depth to trade
- `max_spread_pct`: Max spread before rejecting (unless edge is very strong)
- `max_depth_fraction`: Limit trade to max_depth_fraction of visible depth

### config.json (Experiment Harness)

```json
{
  "default_strategy_config": "strategy_configs/baseline.json",
  "default_dataset": null,
  "strategy_guidance": "strategy.md",
  "state_dir": "state/backtests",
  "starting_bankroll": 1000.0,
  "live_trading_enabled": false
}
```

Points to:
- Which strategy config to use by default
- Which dataset to backtest against
- Where to save state
- Starting capital

### strategy.md (Human Guidance)

Free-form text file that agents can read for context:
- Domain knowledge
- Current focus areas
- Hard constraints
- Open research questions

## Metrics Explanation

All metrics are calculated in `market_env.py` via `evaluate_all()`:

### Epistemic Metrics

**Brier Score** (lower is better)
- Mean squared error of probability forecasts
- Formula: `(forecast_prob - outcome)^2`
- Range: 0 (perfect) to 1 (worst)
- Target: < 0.20
- Calibration buckets: 0.0-0.1, 0.1-0.2, ... 0.9-1.0

### Financial Metrics

**Total PnL**
- Sum of realized gains/losses across all trades
- Formula: For buy side: `(outcome - fill_price) * filled_size`
- Units: Same as bankroll (typically $)

**Sharpe Ratio** (higher is better)
- Risk-adjusted returns
- Formula: `mean(pnl_series) / std(pnl_series) * sqrt(N)`
- Threshold: > 1.0 is "good"

**Max Drawdown** (lower is better)
- Largest peak-to-trough decline
- Formula: `max(peak - running_balance)`
- Threshold: < 50% is acceptable

**Win Rate** (higher is better)
- Fraction of trades with positive PnL
- Threshold: > 50% (break-even)

### Execution Metrics

**Average Slippage** (lower is better, in basis points)
- How much worse than mid price you filled
- Buy: `(fill_price - mid_price) / mid_price * 10000`
- Sell: `(mid_price - fill_price) / mid_price * 10000`
- Threshold: < 10 bps for limit, < 30 bps for market

**Fill Rate** (higher is better, 0-1)
- Fraction of requested size that filled
- Formula: `filled_size / requested_size`
- Market orders: typically 0.8-1.0
- Limit orders: typically 0.15-0.75

**Spread Capture** (higher is better, in basis points)
- How much of the spread you captured with passive orders
- Passive buy: `(mid - fill_price) / mid * 10000`
- Threshold: > 0 for profitable limit order

**Market Impact** (lower is better, in basis points)
- How much the mid price moved after your trade
- Formula: `|price_after - price_before| / price_before * 10000`
- Threshold: < 50 bps

**Implementation Shortfall** (lower is better, in basis points)
- Total cost: slippage + fees
- Formula: `slippage_bps + fee_bps`
- Threshold: < 30 bps

**Adverse Selection Rate** (lower is better, 0-1)
- Fraction of passive orders that moved against you
- For limit buys: count times `next_mid_price < fill_price`
- Threshold: < 20% (good execution timing)

## Iteration Patterns

AutoPredict is designed for iterative improvement through diffs:

### Pattern 1: Adjust Config

Change `strategy_configs/baseline.json`:
```bash
# Lower min_edge to capture more opportunities
"min_edge": 0.03  # was 0.05

python -m autopredict.cli backtest
```

### Pattern 2: Override Agent Method

In `agent.py`, override `decide_order_type()`:
```python
def decide_order_type(self, *, edge, spread_pct, ...):
    # New logic here
    if edge > 0.20:
        return "market"  # More aggressive
    return "limit"
```

### Pattern 3: Add Domain Logic

Extend `MarketState` with new fields:
```python
@dataclass
class MarketState:
    # ... existing fields ...
    volatility_estimate: float = 0.0  # new
    time_of_day: str = "unknown"      # new
```

Then use in agent:
```python
if market.volatility_estimate > 0.5:
    return None  # Skip high-volatility markets
```

### Pattern 4: Improve Execution Simulation

In `market_env.py`, enhance `ExecutionEngine`:
```python
def execute_limit_order(self, ...):
    # Add queue position estimation
    # Add simulated latency effects
    # Add inventory-based pricing impact
```

## Extension Points

Key places to extend AutoPredict:

1. **Agent decision logic**: `AutoPredictAgent.evaluate_market()`
2. **Order type logic**: `ExecutionStrategy.decide_order_type()`
3. **Sizing logic**: `ExecutionStrategy.calculate_trade_size()`
4. **Execution simulation**: `ExecutionEngine.execute_market_order/limit_order()`
5. **Metrics**: `evaluate_all()` in market_env.py
6. **Forecasting**: Input fair_prob logic (external to framework)

## Design Philosophy

AutoPredict follows these principles:

1. **Separation of Concerns**: Agent (mutable) vs Environment (fixed)
2. **Minimal by Design**: Only ~500 lines of core logic
3. **Opinionated but Overridable**: Strong defaults, easy to customize
4. **Metrics-First**: All decisions tied to measurable outcomes
5. **Iterative Improvement**: Support lightweight diffs, not big rewrites
6. **Bankroll as Oracle**: Test decisions on real edge/liquidity/execution
