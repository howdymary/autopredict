# AutoPredict: Current State Diagnosis

**Prepared by**: Agent 6 (Software Architect) & Agent 5 (Data/ML Engineer)
**Date**: 2026-03-26
**Repository**: `/Users/howdymary/Documents/New project/autopredict`

---

## Executive Summary

AutoPredict is a **minimal, well-structured prediction market trading framework** with a clean separation between fixed evaluation primitives and mutable agent logic. The codebase is production-quality for backtesting but **lacks critical components for multi-venue trading, proper risk management, and autonomous self-improvement**.

**Strengths**:
- Clean architecture with immutable environment vs mutable agent
- Comprehensive metrics (epistemic, financial, execution)
- Excellent test coverage (65+ tests)
- Strong validation infrastructure

**Critical Gaps**:
- No market adapters for real venues (Polymarket, Manifold, Kalshi)
- No strategy abstraction layer for pluggable strategies
- No proper backtesting engine with train/test splits
- No risk management system beyond per-trade limits
- No autonomous self-improvement loop

---

## 1. Repository Structure Analysis

### Core Modules (3,078 LOC)

```
autopredict/
├── agent.py                    (524 LOC) - Mutable trading strategy
├── market_env.py              (706 LOC) - Fixed market simulator
├── run_experiment.py          (130 LOC) - Backtest harness
├── cli.py                      (97 LOC) - CLI interface
├── validation.py              (188 LOC) - Fair probability validator
├── calibration_analysis.py    (327 LOC) - Calibration analysis tools
├── validation/
│   └── validator.py           (571 LOC) - Dataset validator
├── examples/
│   ├── real_data_integration/
│   │   └── adapters.py        (314 LOC) - Example adapters (simulated)
│   ├── custom_strategy/
│   │   └── conservative_agent.py
│   └── custom_metrics/
│       └── custom_metrics.py
├── scripts/
│   └── generate_dataset.py    (493 LOC) - Synthetic market generator
└── tests/                      (65+ tests, 80%+ coverage)
```

### Component Roles

#### **agent.py** - Mutable Trading Logic
- **AgentConfig**: JSON-driven hyperparameters (min_edge, aggressive_edge, risk_fraction, etc.)
- **ExecutionStrategy**: Order type selection, sizing, splitting
  - `decide_order_type()`: Market vs limit based on edge-to-spread ratio
  - `calculate_trade_size()`: Kelly-like sizing with risk/depth limits
  - `should_split_order()`: Detect oversized orders
  - `calculate_limit_price()`: Price improvement logic
- **AutoPredictAgent**: Main decision loop
  - `evaluate_market()`: Gate trades by edge/liquidity/spread
  - `analyze_performance()`: Identify weakness from metrics
  - `propose_improvement()`: Lightweight improvement hint

**Role in framework**: This is the **mutable surface area** for experimentation. Changes here are expected and encouraged.

#### **market_env.py** - Fixed Simulation Primitives
- **OrderBook**: Depth-aware book with mid/spread/depth calculations
  - `walk_book()`: Consume liquidity from opposite side
  - `estimate_market_impact()`: Pre-trade impact estimation
- **ExecutionEngine**: Simulate market and limit orders
  - `execute_market_order()`: Walk book immediately
  - `execute_limit_order()`: Marketable vs passive fill logic (probabilistic)
- **Metrics**: Epistemic (Brier score), Financial (PnL, Sharpe, drawdown), Execution (slippage, fill rate, impact)

**Role in framework**: This is the **frozen evaluation layer**. Never modified during experiments to ensure fair comparison.

#### **run_experiment.py** - Backtest Harness
- Loads config + dataset
- Iterates market snapshots
- Calls `agent.evaluate_market()` → `engine.execute_order()` → records trades
- Aggregates metrics via `evaluate_all()`

**Role in framework**: Simple orchestrator. No train/test split, no walk-forward validation, no parameter sweeps.

#### **validation/** - Data Quality Checks
- **FairProbValidator** (`validation.py`): Validates fair_prob estimates
  - Category-specific quality thresholds
  - Edge size warnings
  - Extreme probability detection
- **MarketDataValidator** (`validation/validator.py`): Schema + consistency validation
  - Required fields, probability ranges, order book structure
  - Cross-field consistency (market_prob vs book mid)

**Role in framework**: Input validation to catch bad forecasts. Good quality, production-ready.

#### **examples/real_data_integration/adapters.py** - Market Adapters (Simulated)
- **MarketDataAdapter**: Interface for fetching markets
- **OrderExecutionAdapter**: Interface for submitting orders
- **CSVDataAdapter**: Read historical CSV data
- **PolymarketAdapter**: Simulated Polymarket integration (prints to console, no real API calls)

**Role in framework**: **Example code only**. No real API integrations. Demonstrates interface pattern but not production-ready.

---

## 2. What Works Well

### ✅ Clean Architecture
- **Strict separation**: Fixed environment (`market_env.py`) vs mutable agent (`agent.py`)
- **Single Responsibility**: Each module has one clear purpose
- **Dependency Inversion**: Agent depends on abstract `MarketState`, not implementation details
- **Immutable primitives**: OrderBook, BookLevel are frozen dataclasses

### ✅ Comprehensive Metrics
- **Epistemic**: Brier score, calibration by bucket
- **Financial**: Total PnL, Sharpe ratio, max drawdown, win rate
- **Execution**: Slippage, fill rate, market impact, spread capture, adverse selection, implementation shortfall
- All metrics automatically calculated in `evaluate_all()`

### ✅ Excellent Test Coverage
- 65+ tests across 4 test files
- 80%+ code coverage (per `.coverage` file)
- Tests cover: order book mechanics, execution simulation, agent logic, validation

### ✅ Strong Validation Infrastructure
- Schema validation (required fields, types)
- Range validation (probabilities in [0,1], positive sizes)
- Consistency validation (market_prob vs book mid, crossed books)
- Category-specific quality thresholds
- **Ready for production use**

### ✅ Realistic Backtesting
- Order book depth simulation with partial fills
- Limit order fill rate logic (passive orders have ~15-75% fill rate depending on price improvement)
- Market impact calculation
- Slippage measurement (fill price vs mid price)

### ✅ Documentation
- `ARCHITECTURE.md`: Technical deep dive (384 LOC)
- `README.md`: Quick start guide
- `METRICS.md`: Metric definitions
- `QUICKSTART.md`: Tutorial
- Inline docstrings on all classes and methods

---

## 3. What's Confusing or Poorly Structured

### ⚠️ Inconsistent Module Organization
**Problem**: Core logic scattered at root level instead of proper package structure.

**Current**:
```
autopredict/
├── agent.py                  # Core
├── market_env.py            # Core
├── run_experiment.py        # Core
├── cli.py                   # Core
├── validation.py            # Validation
├── validation/validator.py  # Also validation (why two places?)
├── calibration_analysis.py  # Analysis tool (should be in scripts/)
└── examples/                # Examples (good)
```

**Issues**:
- `validation.py` and `validation/validator.py` are both validators - duplication
- `calibration_analysis.py` is a script, not a library module - should be in `scripts/`
- No clear distinction between **library code** (importable) and **scripts** (runnable)

### ⚠️ No Strategy Abstraction
**Problem**: Only one strategy implementation (`AutoPredictAgent`). No interface for pluggable strategies.

**Current**:
- `agent.py` has one concrete class `AutoPredictAgent`
- No `Strategy` base class or protocol
- `examples/custom_strategy/conservative_agent.py` shows a custom agent but doesn't follow a standard interface

**Impact**:
- Can't easily swap strategies (e.g., mean reversion vs momentum)
- Can't run strategy ensembles
- Can't A/B test strategies in parallel

### ⚠️ No Agent Loop Architecture
**Problem**: No clear "sense → think → act" loop. Logic is embedded in `run_experiment.py`.

**Current flow**:
```python
# run_experiment.py
for record in dataset:
    state = MarketState(...)
    proposal = agent.evaluate_market(state, bankroll)
    if proposal:
        report = engine.execute_order(...)
        trades.append(...)
```

**Issues**:
- No explicit agent state (memory, positions, exposure tracking)
- No explicit "think" phase (reasoning, exploration vs exploitation)
- No explicit "act" phase with risk controls

**Missing**:
- Agent memory (what markets did I trade? what's my current exposure?)
- Position tracking (what's my net exposure to crypto markets?)
- Risk limits (max total exposure, sector limits, correlation limits)

### ⚠️ Backtesting is Too Simple
**Problem**: `run_experiment.py` is a basic loop, not a proper backtest engine.

**Missing**:
- Train/test split (all data used for evaluation)
- Walk-forward validation
- Parameter sweeps
- Cross-validation
- Out-of-sample metrics
- Overfitting detection

**Impact**: Can't trust results. No way to know if strategy generalizes.

---

## 4. Critical Gaps for Production Trading

### ❌ No Market Adapters for Real Venues

**Current state**: `examples/real_data_integration/adapters.py` has **simulated** Polymarket adapter (prints to console).

**Missing**:
- Real Polymarket API integration (REST + WebSocket)
- Manifold Markets integration
- Kalshi integration
- PredictIt integration
- Real-time order book streaming
- Order status tracking
- Fill notifications
- Wallet/balance management

**Impact**: Framework only works on static datasets. Can't trade live.

**Code evidence**:
```python
# adapters.py:234
def submit_order(self, market_id: str, side: str, size: float, price: float | None) -> dict:
    print(f"[SIMULATED] Submitting order to Polymarket:")
    # No real API call
    return {"order_id": "...", "status": "submitted"}
```

### ❌ No Strategy Abstraction Layer

**Current state**: One hardcoded strategy (`AutoPredictAgent`).

**Missing**:
- `Strategy` base class / protocol
- Strategy registry (map names to classes)
- Strategy factory (instantiate by config)
- Strategy composition (combine multiple strategies)
- Strategy ensembles (weighted voting)

**Impact**: Can't easily:
- Test multiple strategies in parallel
- Combine strategies (e.g., 50% conservative, 50% aggressive)
- Compare strategy performance
- Implement meta-strategies (strategy selection based on market conditions)

**What's needed**:
```python
class Strategy(ABC):
    @abstractmethod
    def evaluate_market(self, market: MarketState, context: TradingContext) -> ProposedOrder | None:
        pass

class MeanReversionStrategy(Strategy): ...
class MomentumStrategy(Strategy): ...
class EnsembleStrategy(Strategy):
    def __init__(self, strategies: list[Strategy], weights: list[float]): ...
```

### ❌ No Proper Backtesting Engine

**Current state**: Simple loop in `run_experiment.py` (130 LOC).

**Missing**:
- Train/test split
- Walk-forward validation (e.g., train on 100 markets, test on next 20, roll forward)
- Cross-validation (k-fold splits)
- Parameter grid search
- Bayesian optimization of hyperparameters
- Overfitting metrics (in-sample vs out-of-sample Sharpe ratio)
- Statistical significance tests (bootstrap, permutation tests)

**Impact**: Can't trust results. No confidence intervals. No way to detect overfitting.

**What's needed**:
```python
class BacktestEngine:
    def run_backtest(self, strategy: Strategy, dataset: Dataset, train_frac: float = 0.7): ...
    def run_walk_forward(self, strategy: Strategy, dataset: Dataset, train_window: int, test_window: int): ...
    def run_parameter_sweep(self, strategy_class: type[Strategy], param_grid: dict): ...
    def calculate_significance(self, results_A: BacktestResults, results_B: BacktestResults): ...
```

### ❌ No Risk Management System

**Current state**: Only per-trade limits (`max_risk_fraction`, `max_position_notional`).

**Missing**:
- **Position tracking**: What's my current exposure across all markets?
- **Portfolio risk limits**: Max total notional, max drawdown threshold
- **Sector limits**: Max exposure to crypto, politics, etc.
- **Correlation limits**: Don't overexpose to correlated markets
- **Loss limits**: Stop trading if daily loss exceeds threshold
- **Concentration limits**: Max % of portfolio in single market

**Impact**: Can blow up portfolio with correlated bets.

**Code evidence**:
```python
# agent.py:440 - Only per-trade sizing, no portfolio-level risk
size = self.execution.calculate_trade_size(
    edge=abs_edge, bankroll=bankroll, liquidity_depth=liquidity_depth, config=self.config
)
# Missing:
# - Current total exposure check
# - Correlation with existing positions
# - Sector exposure limits
```

**What's needed**:
```python
class RiskManager:
    def check_limits(self, proposed_order: ProposedOrder, portfolio: Portfolio) -> RiskCheckResult:
        # Check: total notional < max_notional
        # Check: sector exposure < sector_limit
        # Check: correlation with existing positions < corr_threshold
        # Check: daily loss < stop_loss_threshold
        pass

    def calculate_position_size(
        self, edge: float, portfolio: Portfolio, market: MarketState
    ) -> float:
        # Kelly criterion adjusted for:
        # - Current portfolio volatility
        # - Correlation with existing positions
        # - Sector concentration
        pass
```

### ❌ No Self-Improvement Loop

**Current state**: `agent.analyze_performance()` identifies weakness, but no automation.

**Missing**:
- Autonomous experiment runner (iterate configs, compare metrics)
- Parameter optimizer (Bayesian optimization, genetic algorithms)
- Strategy generator (mutate existing strategies, test, keep best)
- Meta-learning (learn which strategies work in which market conditions)

**Impact**: Framework is manual-only. No autonomous improvement.

**Code evidence**:
```python
# agent.py:482
def analyze_performance(self, metrics: dict[str, Any], guidance: str) -> dict[str, str]:
    # Returns weakness + hypothesis, but doesn't ACT on it
    if avg_slippage > 15.0:
        return {"weakness": "execution_quality", "hypothesis": "Use passive orders..."}
    # Missing: Automatically adjust config and rerun
```

**What's needed**:
```python
class SelfImprovementLoop:
    def run_iteration(self, current_config: AgentConfig, dataset: Dataset) -> AgentConfig:
        # 1. Run backtest with current config
        # 2. Analyze metrics
        # 3. Propose config changes (e.g., lower min_edge if too few trades)
        # 4. Test proposed config
        # 5. Keep if better, else revert
        # 6. Save iteration history
        pass

    def optimize_hyperparameters(
        self, strategy: Strategy, dataset: Dataset, param_space: dict
    ) -> AgentConfig:
        # Bayesian optimization over param_space
        pass
```

---

## 5. Where Does the Agent Loop Live?

**Current state**: Partially implemented, scattered across modules.

### Sense Phase
**Where**: `run_experiment.py:70-77`
```python
state = MarketState(
    market_id=market_id, market_prob=market_prob, fair_prob=fair_prob,
    time_to_expiry_hours=expiry_hours, order_book=order_book, ...
)
```
**Issues**:
- Sense is manual (reading from static dataset)
- No real-time streaming
- No market data adapters

### Think Phase
**Where**: `agent.py:415-480` (`evaluate_market()`)
```python
def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
    edge = market.fair_prob - market.market_prob
    # Gate by edge, liquidity, spread
    # Calculate order_type and size
    return ProposedOrder(...)
```
**Issues**:
- Think is stateless (no memory of past trades)
- No exploration vs exploitation
- No reasoning about portfolio correlation

### Act Phase
**Where**: `run_experiment.py:84-124` (execution loop)
```python
if proposal.order_type == "market":
    report = engine.execute_market_order(...)
else:
    report = engine.execute_limit_order(...)
```
**Issues**:
- Act is simulated only (no real order submission)
- No risk checks before execution
- No order tracking / cancellation

### Learn Phase
**Where**: `agent.py:482-524` (`analyze_performance()`, `propose_improvement()`)
```python
def analyze_performance(self, metrics: dict[str, Any], guidance: str) -> dict[str, str]:
    if avg_slippage > 15.0:
        return {"weakness": "execution_quality", "hypothesis": "..."}
```
**Issues**:
- Learn is manual (returns suggestions but doesn't act)
- No automated parameter updates
- No experiment tracking

---

## 6. Where Should Self-Improvement Hooks Be Inserted?

### Option A: **Wrap the Entire Backtest Loop**
```python
class SelfImprovementLoop:
    def run_epoch(self, config: AgentConfig, dataset: Dataset) -> tuple[AgentConfig, BacktestResults]:
        # 1. Run backtest with current config
        results = run_backtest(config=config, dataset=dataset)

        # 2. Analyze weaknesses
        agent = AutoPredictAgent(config)
        diagnosis = agent.analyze_performance(results.metrics, guidance="")

        # 3. Propose config changes
        new_config = self.mutate_config(config, diagnosis)

        # 4. Validate improvement (run on validation set)
        val_results = run_backtest(config=new_config, dataset=validation_set)

        # 5. Keep if better
        if val_results.sharpe > results.sharpe:
            return new_config, val_results
        else:
            return config, results
```

**Pros**:
- Outer loop, clean separation
- Easy to add experiment tracking (MLflow, Weights & Biases)
- Can swap in different optimizers (Bayesian, genetic)

**Cons**:
- Requires train/test split infrastructure
- Slower (full backtest per iteration)

### Option B: **Embed in Agent's `analyze_performance()`**
```python
class AutoPredictAgent:
    def analyze_performance(self, metrics: dict[str, Any], guidance: str) -> dict[str, str]:
        diagnosis = self._identify_weakness(metrics)

        # NEW: Automatically adjust config
        if diagnosis["weakness"] == "execution_quality":
            self.config.aggressive_edge *= 1.1  # Be less aggressive
        elif diagnosis["weakness"] == "limit_fill_quality":
            self.config.limit_price_improvement_ticks *= 1.2  # Improve prices more

        return diagnosis
```

**Pros**:
- Fast (inline adjustments)
- Reactive (adjusts on-the-fly)

**Cons**:
- No validation (can diverge)
- Hard to track experiment history

### Recommended: **Option A** (Outer Loop)
- More principled (train/test separation)
- Easier to debug and visualize
- Extensible to meta-learning

---

## 7. Top 5 Architectural Improvements Needed

### 1. **Market Adapter Layer** (Priority: CRITICAL)
**Why**: Can't trade live without real API integrations.

**What**:
- Real Polymarket REST + WebSocket client
- Real Manifold Markets client
- Real Kalshi client
- Unified `MarketDataAdapter` interface
- Order submission, cancellation, status tracking

**Effort**: 2-3 weeks per venue

---

### 2. **Strategy Abstraction Layer** (Priority: HIGH)
**Why**: Can't test multiple strategies or build ensembles.

**What**:
- `Strategy` base class / protocol
- Strategy registry (map names to classes)
- Strategy factory (instantiate by config)
- Built-in strategies: mean reversion, momentum, value, ensemble

**Effort**: 1 week

---

### 3. **Proper Backtesting Engine** (Priority: HIGH)
**Why**: Current results can't be trusted (no train/test split, no overfitting detection).

**What**:
- Train/test split
- Walk-forward validation
- Cross-validation
- Parameter grid search / Bayesian optimization
- Statistical significance tests
- Out-of-sample metrics

**Effort**: 2 weeks

---

### 4. **Risk Management System** (Priority: CRITICAL)
**Why**: Can blow up portfolio with correlated bets or sector concentration.

**What**:
- Portfolio-level position tracking
- Sector exposure limits
- Correlation-adjusted sizing
- Loss limits (daily, weekly)
- Concentration limits

**Effort**: 1 week

---

### 5. **Self-Improvement Loop** (Priority: MEDIUM)
**Why**: Manual iteration is slow. Need autonomous optimization.

**What**:
- Autonomous experiment runner
- Bayesian hyperparameter optimization
- Strategy mutation & evolution
- Experiment tracking (MLflow / W&B integration)
- Meta-learning (strategy selection by market regime)

**Effort**: 2-3 weeks

---

## 8. Code Quality Assessment

### Strengths
- **Type hints**: Extensive use of `float | None`, `dict[str, Any]`, etc.
- **Docstrings**: Every class and method documented
- **Constants**: `EPSILON`, `BPS_MULTIPLIER` at top of files
- **Dataclasses**: Clean data structures (`@dataclass` for `AgentConfig`, `MarketState`, etc.)
- **No magic numbers**: All thresholds in config or constants
- **Separation of concerns**: Each function has one clear purpose

### Weaknesses
- **No logging**: Everything uses `print()` instead of Python `logging` module
  - Can't control log levels
  - Can't redirect to files
- **No error handling**: Minimal `try/except` blocks
  - What if API call fails?
  - What if dataset is malformed?
- **No async/await**: All I/O is synchronous
  - Can't stream multiple markets in parallel
  - Slow for live trading
- **No dependency injection**: Hard to mock `ExecutionEngine` for testing
- **Hardcoded paths**: `"/Users/howdymary/..."` in `calibration_analysis.py:253`

---

## 9. Metrics Quality

### Excellent
- **Brier score**: Standard epistemic metric
- **Calibration by bucket**: Crucial for understanding forecast quality
- **Sharpe ratio**: Industry-standard risk-adjusted return
- **Max drawdown**: Essential risk metric
- **Slippage**: Execution quality metric
- **Spread capture**: Measures limit order effectiveness

### Missing
- **Sortino ratio**: Downside-only volatility (better than Sharpe for skewed returns)
- **Calmar ratio**: Return / max drawdown
- **Information ratio**: Excess return / tracking error vs benchmark
- **Expected shortfall (CVaR)**: Tail risk metric
- **Hit ratio by category**: Win rate broken down by market category
- **Execution cost decomposition**: Spread + impact + fees + adverse selection

---

## 10. Testing Quality

**Coverage**: 80%+ (excellent)

**Test files**:
- `tests/test_market_env.py`: Order book mechanics, execution engine
- `tests/test_agent.py`: Agent logic, config validation
- `tests/test_validation.py`: Validation rules
- `tests/conftest.py`: Pytest fixtures

**Missing tests**:
- **Integration tests**: End-to-end backtest runs
- **Property-based tests**: Use `hypothesis` library to test invariants
  - Example: `filled_size <= requested_size` for all orders
  - Example: `book.get_spread() >= 0` always
- **Performance tests**: Backtest 10,000 markets, measure runtime
- **Regression tests**: Save baseline metrics, detect performance degradation

---

## 11. Final Assessment

### Production-Readiness Score: **6/10**

**What's production-ready**:
- Backtesting simulation (order book, execution, metrics)
- Validation infrastructure
- Test coverage
- Documentation

**What's NOT production-ready**:
- Market adapters (simulated only)
- Risk management (per-trade only, no portfolio limits)
- Backtesting (no train/test split, overfitting risk)
- Live trading (no order tracking, no error handling)
- Self-improvement (manual only)

**Recommendation**:
- **For research**: Framework is excellent. Use as-is for backtesting experiments.
- **For live trading**: Need 4-6 weeks of work to add market adapters, risk management, and error handling.
- **For autonomous improvement**: Need 2-3 weeks to build self-improvement loop.

---

## Appendix: File-by-File Analysis

### Core Modules

**agent.py** (524 LOC)
- Lines 16-68: `AgentConfig` (10 tunable parameters, well-documented)
- Lines 70-104: `MarketState` (normalized market snapshot)
- Lines 106-144: `ProposedOrder` (agent decision output)
- Lines 146-345: `ExecutionStrategy` (order type, sizing, splitting logic)
- Lines 347-524: `AutoPredictAgent` (main decision loop, performance analysis)

**market_env.py** (706 LOC)
- Lines 28-46: `BookLevel` (immutable price/size level)
- Lines 48-222: `OrderBook` (depth-aware book with walk_book())
- Lines 224-242: `ExecutionReport` (execution result)
- Lines 244-462: `ExecutionEngine` (simulate market/limit orders)
- Lines 464-707: Metrics calculation (Brier, Sharpe, slippage, etc.)

**run_experiment.py** (130 LOC)
- Lines 32-131: `run_backtest()` - Main backtest loop
  - Load config, dataset, agent
  - Iterate markets → evaluate → execute → record trades
  - Calculate aggregate metrics

**cli.py** (97 LOC)
- Lines 36-53: `command_backtest()` - Run backtest CLI
- Lines 56-62: `command_score_latest()` - Print latest metrics
- Lines 65-69: `command_trade_live()` - Placeholder (disabled)

### Validation

**validation.py** (188 LOC)
- `FairProbValidator`: Validate fair_prob estimates
  - Category-specific quality thresholds (lines 23-61)
  - Edge warnings, extreme probabilities, direction reversals

**validation/validator.py** (571 LOC)
- `MarketDataValidator`: Schema + consistency validation
  - Required fields, probability ranges, order book structure
  - Cross-field consistency (market_prob vs book mid)

### Analysis Tools

**calibration_analysis.py** (327 LOC)
- Analyze calibration from backtest results
- Shrinkage toward market (lines 55-68)
- Platt scaling (lines 71-87)
- Generate recommendations (lines 145-217)

### Examples

**examples/real_data_integration/adapters.py** (314 LOC)
- `MarketDataAdapter` interface (lines 19-40)
- `OrderExecutionAdapter` interface (lines 43-73)
- `CSVDataAdapter` (lines 76-152) - Load historical CSV
- `PolymarketAdapter` (lines 154-265) - **SIMULATED** (not real API)

**examples/custom_strategy/conservative_agent.py**
- Custom agent with tighter risk controls
- Shows how to extend `AutoPredictAgent`

### Scripts

**scripts/generate_dataset.py** (493 LOC)
- `MarketGenerator`: Generate realistic synthetic markets
  - Category distributions (geopolitics, politics, crypto, etc.)
  - Liquidity tiers (micro, small, medium, large)
  - Spread tiers (tight, normal, wide, very_wide)
  - Time to expiry (urgent, short, medium, long)

---

## Next Steps

See **ARCHITECTURE_PROPOSAL.md** for target design and **MIGRATION_PLAN.md** for step-by-step refactoring plan.
