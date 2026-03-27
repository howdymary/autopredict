# AutoPredict Architecture

AutoPredict is a minimal, modular framework for building self-improving prediction market agents. It separates concerns cleanly: fixed environment primitives, mutable agent strategy, and configuration-driven tuning.

Step 1 adds a dedicated prediction-market scaffold so venue-specific logic can evolve in its own package without entangling the current experiment harness.

Phase 1 domain specialization adds two more additive seams, Phase 2 makes those seams executable inside the scaffold runtime, Phase 3 makes the signal layer model-backed without changing the scaffold contracts, Phase 4 adds offline held-out calibration datasets for the default domain models, and Phase 5 versions those datasets and attaches report cards so promotion can cite both lineage and held-out quality:

- `autopredict/ingestion/` for fixture-backed evidence normalization
- `autopredict/domains/` for domain adapters, question-conditioned models, and specialist strategies that emit and consume normalized features and split labels

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

## Step 1 Scaffold

The new `autopredict/prediction_market/` layer is the home for market-facing orchestration. It is intentionally narrow:

- typed snapshots, signals, and decisions for prediction-market workflows
- a composable agent that turns strategy outputs into trade, hold, or skip decisions
- a strategy registry so multiple agent variants can coexist cleanly
- compatibility adapters that reuse the existing `agent.py` primitives while the migration is in progress

The existing `agent.py`, `market_env.py`, and `run_experiment.py` flow stays intact for now. Step 1 just gives the project a cleaner boundary so Step 2 can add backtesting and scoring-rule evaluation, and Step 3 can add mutation, selection, and other self-improvement loops on top of the same core surface.

The package currently ships this structure:

```
autopredict/prediction_market/
├── __init__.py     # Package exports
├── agent.py        # PredictionMarketAgent + compatibility exports
├── builtin.py      # Bridge adapters for existing strategies
├── registry.py     # Named strategy registry
├── strategy.py     # PredictionMarketStrategy protocol
└── types.py        # VenueConfig, MarketSnapshot, MarketSignal, AgentDecision
```

The key design choice in Step 1 is separating signal generation from order generation:

- `generate_signal(snapshot, context)` estimates fair value and confidence
- `build_orders(snapshot, signal, context)` converts that view into executable orders

That separation is what lets future evaluation modules score forecasts independently from execution quality, and lets future self-improvement loops mutate forecasting logic separately from order logic.

## Step 2 Evaluation Layer

`autopredict/evaluation/` is the stable scoring seam in the system. It sits beside `backtest/` rather than replacing it, and focuses on the new prediction-market scaffold.

The package owns:

1. **Proper scoring rules**
   - `brier_score` for squared-error calibration
   - `log_score` for sharper penalization of overconfident mistakes
   - `spherical_score` for a complementary normalization-aware ranking

2. **Calibration summaries**
   - bucketed forecast reliability
   - average forecast error by probability band
   - drift reports that can feed later self-improvement loops

3. **Scaffold-level backtesting**
   - deterministic evaluation of `PredictionMarketAgent` outputs
   - liquidity-aware fill assumptions
   - realized outcome tracking so scoring and execution can be compared cleanly

The core idea is to keep evaluation pure and reproducible: strategies produce signals and orders, while `autopredict/evaluation` turns those artifacts into metrics that can be compared across iterations.

## Step 3 Self-Improvement Layer

`autopredict/self_improvement/` is the mutation-and-selection seam. It sits on top of `prediction_market/` and `evaluation/` without coupling itself to exchange plumbing.

The package owns:

1. **Strategy mutation**
   - clone or perturb strategy variants
   - preserve provenance so variants are traceable
   - keep mutations deterministic when seeded

2. **Evaluation-driven selection**
   - score variants through `autopredict/evaluation`
   - prefer improvements that hold up on proper scoring rules and calibration, not just PnL
   - enforce guardrails for regression and overfitting

3. **Promotion logic**
   - keep the best variants active
   - reject candidates that improve one metric while degrading calibration or forecast quality
   - support chronological walk-forward, regime-block holdouts, and market-family holdouts before a mutation becomes the next active baseline
   - use domain model report cards as an additional comparison surface when model-backed specialists are involved
   - leave the registry as the stable handoff point for downstream backtests and experiments

The design goal is a tight loop: mutate, evaluate, compare, and promote only when the forecast-quality and execution-quality signals both clear the bar.

Today the validation config supports three held-out modes:

1. `chronological`
   - expanding train windows with the next time slice held out

2. `regime`
   - contiguous regime blocks, using explicit labels like `metadata.regime` or auto-bucketed market conditions such as spread and liquidity

3. `market_family`
   - leave-family-out validation, with `category` as the default family key and raw metadata categories preferred when present

## Domain Specialization

The new domain-specialist scaffold sits beside the generic prediction-market runtime rather than inside it.

It introduces:

1. **Ingestion**
   - fixture-backed normalization for finance, weather, and politics evidence
   - shared `EvidenceRecord`, `TimeSeriesPoint`, and `IngestionBatch` primitives
   - small registries and cache helpers for deterministic local workflows

2. **Domain adapters**
   - adapters that translate normalized evidence into reusable feature bundles
   - stable metadata labels for `domain`, `market_family`, `regime`, and `feature_version`
   - a clean handoff point for specialist strategies and held-out split logic

3. **Specialist strategies**
   - finance, weather, and politics strategies that call lightweight question-conditioned domain models
   - no new agent protocol or backtester path; the existing scaffold agent still drives execution
   - intentionally lightweight and deterministic so stronger models can replace them later without rewriting the runtime

4. **Domain models**
   - small stdlib logistic models fit from offline local datasets with `train`, `calibration`, and `evaluation` splits
   - consume `snapshot.market.question`, bundle features, and stable labels
   - apply held-out sigmoid calibration before returning the same fair-probability and confidence surface that the scaffold already expects

5. **Dataset versioning and report cards**
   - offline datasets now declare stable `dataset_name`, `dataset_version`, and domain identity at the manifest level
   - each trained specialist model emits a report card with split coverage, proper-score summaries, and held-out calibration stability
   - the same report card is surfaced through model metadata so evaluation and selection can compare data support alongside backtest quality

6. **Grouped evaluation**
   - slice reports by `domain`, `market_family`, or `regime`
   - reuse the same proper scoring rules and backtest outputs instead of forking evaluation logic by domain
   - surface sparse-support and unstable-calibration warnings for fragile slices

The contract is deliberately small: normalized evidence enters as `IngestionBatch`, adapters emit `DomainFeatureBundle`, versioned offline datasets pin lineage, domain models consume those merged snapshot inputs plus offline priors, and report cards expose whether a specialist is calibrated, well-supported, and promotable before the shared metadata keys `domain`, `market_family`, `regime`, and `feature_version` route grouped evaluation and held-out promotion.

The important constraint is still intentional: even in Phase 4, the intelligence lives inside domain-local datasets, models, and strategies, not inside the generic runtime. That keeps backtesting, scoring, and self-improvement comparable across domains.

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

### Prediction Market Scaffold (autopredict/prediction_market)

**Purpose**: Market-facing abstractions that sit between the core agent logic and specific prediction market venues.

**Key Classes**:

1. **VenueConfig**
   - normalizes venue-level assumptions such as fees, tick size, and minimum order size
   - gives later backtests a clean place to model venue-specific execution costs

2. **MarketSnapshot**
   - wraps `MarketState` with venue metadata plus optional features and labels
   - becomes the atomic unit for signal generation across markets and timeframes

3. **StrategyContext**
   - carries portfolio, current position, and experiment metadata
   - keeps state explicit so strategies are easier to test and mutate

4. **PredictionMarketAgent**
   - evaluates one snapshot with a pluggable strategy
   - returns a typed `AgentDecision` with `trade`, `hold`, or `skip`

5. **StrategyRegistry**
   - maps stable names to strategy factories
   - gives future A/B testing and self-improvement loops a consistent control point

6. **LegacyMispricedStrategyAdapter**
   - bridges the existing `MispricedProbabilityStrategy` into the new protocol
   - makes the scaffold immediately usable without a risky rewrite

**Design Principle**: this layer is the stable seam for future backtesting and self-improvement work; the learning loop can mutate strategies here without needing to know about exchange plumbing, and current experiments can keep using the legacy mutable agent unchanged.

### Evaluation Layer (autopredict/evaluation)

**Purpose**: score and compare the prediction-market scaffold with reproducible metrics.

**Key Outputs**:

1. **Proper scoring rules**
   - Brier score, log score, spherical score
   - useful for comparing forecast quality across strategy variants

2. **Calibration summaries**
   - bucketed reliability and forecast drift
   - useful for spotting overconfidence and category-specific bias

3. **Scaffold backtests**
   - deterministic fills and realized outcomes
   - useful for separating signal quality from execution quality

**Design Principle**: evaluation should stay independent from strategy code so Step 3 can mutate strategies without changing the scoring contract.

### Self-Improvement Layer (autopredict/self_improvement)

**Purpose**: mutate and select strategy variants using the fixed evaluation surface.

**Key Outputs**:

1. **Variant sets**
   - mutated strategy candidates with provenance
   - useful for A/B tests and rollbacks

2. **Promotion decisions**
   - winners chosen with score and calibration guardrails
   - useful for keeping improvements aligned with forecast quality

3. **Experiment summaries**
   - variant-by-variant score comparisons
   - useful for deciding whether to keep, tweak, or discard a mutation

**Design Principle**: self-improvement should optimize the agent, not the evaluation contract; the scoring rules remain fixed while the strategy population changes.

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
  "default_dataset": "datasets/sample_markets.json",
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

### Current layers

The package-native `evaluation/` and `self_improvement/` layers now sit on top of the Step 1 scaffold. They reuse the same market-facing surface while keeping scoring and mutation logic independent from exchange plumbing.

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
