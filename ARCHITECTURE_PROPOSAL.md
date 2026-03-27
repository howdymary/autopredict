# AutoPredict: Target Architecture Proposal

**Prepared by**: Agent 6 (Software Architect) & Agent 5 (Data/ML Engineer)
**Date**: 2026-03-26

---

## Executive Summary

This document proposes a **clean, modular architecture** for AutoPredict that enables:
1. Multi-venue live trading (Polymarket, Manifold, Kalshi)
2. Pluggable strategy system
3. Rigorous backtesting with train/test splits
4. Portfolio-level risk management
5. Autonomous self-improvement loop

**Design Principles**:
- **Separation of concerns**: Each module has one clear responsibility
- **Interface-driven**: Abstract interfaces, concrete implementations
- **Testability**: All components mockable and unit-testable
- **Extensibility**: Easy to add new venues, strategies, metrics
- **Production-ready**: Error handling, logging, monitoring

---

## 1. Target Module Layout

```
autopredict/
├── __init__.py
│
├── markets/                 # Venue adapters
│   ├── __init__.py
│   ├── base.py             # Abstract interfaces
│   ├── polymarket.py       # Polymarket REST + WebSocket
│   ├── manifold.py         # Manifold Markets
│   ├── kalshi.py           # Kalshi
│   └── simulator.py        # Simulation mode (current behavior)
│
├── data/                    # Historical data & feature pipelines
│   ├── __init__.py
│   ├── loaders.py          # Load datasets (JSON, CSV, Parquet)
│   ├── features.py         # Feature engineering
│   ├── splits.py           # Train/test split utilities
│   └── validation.py       # Data validation (move from root)
│
├── strategies/              # Strategy interface + implementations
│   ├── __init__.py
│   ├── base.py             # Strategy protocol
│   ├── registry.py         # Strategy factory
│   ├── autopredict.py      # Current AutoPredictAgent (renamed)
│   ├── mean_reversion.py   # Mean reversion strategy
│   ├── momentum.py         # Momentum strategy
│   ├── value.py            # Value strategy (edge-based)
│   └── ensemble.py         # Ensemble of strategies
│
├── agents/                  # Agent loop: sense → think → act
│   ├── __init__.py
│   ├── base.py             # Agent interface
│   ├── trading_agent.py    # Main trading agent (stateful)
│   ├── context.py          # TradingContext (state, portfolio, memory)
│   └── policy.py           # Policy selection (which strategy when?)
│
├── backtest/                # Backtest engine
│   ├── __init__.py
│   ├── engine.py           # BacktestEngine
│   ├── simulator.py        # OrderBook simulator (from market_env.py)
│   ├── metrics.py          # Metric calculation (from market_env.py)
│   ├── splits.py           # Train/test/validation splits
│   ├── optimization.py     # Hyperparameter optimization
│   └── reports.py          # Generate backtest reports
│
├── live/                    # Live trading execution
│   ├── __init__.py
│   ├── executor.py         # Live order executor
│   ├── risk.py             # Risk manager (pre-trade checks)
│   ├── monitor.py          # Real-time monitoring
│   └── reconcile.py        # Position reconciliation
│
├── config/                  # Configuration schemas
│   ├── __init__.py
│   ├── schema.py           # Pydantic models for configs
│   ├── defaults.py         # Default configs
│   └── loader.py           # Config loader
│
├── learning/                # Self-improvement loop
│   ├── __init__.py
│   ├── optimizer.py        # Bayesian optimizer
│   ├── evolution.py        # Genetic algorithm
│   ├── meta_learner.py     # Meta-learning (strategy selection)
│   └── experiment.py       # Experiment tracking (MLflow)
│
├── utils/                   # Shared utilities
│   ├── __init__.py
│   ├── logging.py          # Logging setup
│   ├── errors.py           # Custom exceptions
│   └── types.py            # Shared type definitions
│
└── cli.py                   # CLI entrypoints (keep at root)
```

---

## 2. Core Interfaces

### 2.1. Market Adapters (`markets/base.py`)

```python
from abc import ABC, abstractmethod
from typing import Iterator, Optional
from dataclasses import dataclass

@dataclass
class MarketSnapshot:
    """Normalized market snapshot from any venue."""
    venue: str                      # "polymarket", "manifold", etc.
    market_id: str
    question: str
    category: str
    market_prob: float              # Current price
    time_to_expiry_hours: float
    order_book: OrderBook
    metadata: dict[str, Any]        # Venue-specific fields


class MarketDataAdapter(ABC):
    """Interface for fetching market data from venues."""

    @abstractmethod
    async def fetch_markets(self, filters: dict[str, Any] | None = None) -> list[MarketSnapshot]:
        """Fetch current market snapshots (async for parallel requests)."""
        pass

    @abstractmethod
    async def stream_markets(self) -> AsyncIterator[MarketSnapshot]:
        """Stream market updates in real-time via WebSocket."""
        pass

    @abstractmethod
    async def get_order_book(self, market_id: str) -> OrderBook:
        """Fetch order book for a specific market."""
        pass


class OrderExecutionAdapter(ABC):
    """Interface for submitting orders to venues."""

    @abstractmethod
    async def submit_order(
        self,
        market_id: str,
        side: str,
        size: float,
        order_type: str,
        limit_price: Optional[float] = None
    ) -> OrderConfirmation:
        """Submit an order (async for non-blocking)."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderStatus:
        """Get current status of an order."""
        pass

    @abstractmethod
    async def get_fills(self, order_id: str) -> list[Fill]:
        """Get all fills for an order."""
        pass
```

**Rationale**:
- **Async/await**: Non-blocking I/O for live trading (critical for performance)
- **Venue-agnostic**: Works with any prediction market
- **Normalized**: All venues return same `MarketSnapshot` structure
- **Extensible**: Easy to add new venues

### 2.2. Strategy Interface (`strategies/base.py`)

```python
from abc import ABC, abstractmethod
from typing import Protocol

class Strategy(Protocol):
    """Strategy protocol (duck typing for flexibility)."""

    def evaluate_market(
        self,
        market: MarketSnapshot,
        context: TradingContext
    ) -> ProposedOrder | None:
        """Evaluate a market and return order proposal."""
        ...

    def analyze_performance(
        self,
        metrics: BacktestMetrics,
        guidance: str = ""
    ) -> PerformanceAnalysis:
        """Analyze performance and identify weaknesses."""
        ...


class StrategyRegistry:
    """Factory for creating strategies by name."""

    _strategies: dict[str, type[Strategy]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a strategy."""
        def decorator(strategy_class: type[Strategy]):
            cls._strategies[name] = strategy_class
            return strategy_class
        return decorator

    @classmethod
    def create(cls, name: str, config: dict[str, Any]) -> Strategy:
        """Create a strategy instance by name."""
        if name not in cls._strategies:
            raise ValueError(f"Unknown strategy: {name}")
        return cls._strategies[name].from_config(config)


# Usage:
@StrategyRegistry.register("autopredict")
class AutoPredictStrategy(Strategy):
    ...

@StrategyRegistry.register("mean_reversion")
class MeanReversionStrategy(Strategy):
    ...
```

**Rationale**:
- **Protocol over ABC**: More flexible (no inheritance required)
- **Registry pattern**: Easy to add new strategies
- **Config-driven**: Strategies instantiated from JSON/YAML
- **Composable**: Can build `EnsembleStrategy` from multiple strategies

### 2.3. Trading Context (`agents/context.py`)

```python
from dataclasses import dataclass, field

@dataclass
class TradingContext:
    """Agent state: portfolio, memory, risk limits."""

    # Portfolio state
    bankroll: float
    positions: dict[str, Position]      # market_id -> Position
    pending_orders: dict[str, Order]    # order_id -> Order

    # Risk state
    daily_pnl: float = 0.0
    total_exposure: float = 0.0
    sector_exposure: dict[str, float] = field(default_factory=dict)

    # Memory
    trade_history: list[TradeRecord] = field(default_factory=list)
    market_history: dict[str, list[MarketSnapshot]] = field(default_factory=dict)

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)

    def get_net_exposure(self, category: str | None = None) -> float:
        """Calculate net exposure (optionally filtered by category)."""
        if category is None:
            return sum(pos.notional for pos in self.positions.values())
        return sum(
            pos.notional for pos in self.positions.values()
            if pos.category == category
        )

    def get_correlation_risk(self, market: MarketSnapshot) -> float:
        """Calculate correlation risk with existing positions."""
        # Estimate correlation based on category overlap
        # More sophisticated: use historical price correlations
        category_exposure = self.sector_exposure.get(market.category, 0.0)
        return category_exposure / max(self.bankroll, 1.0)
```

**Rationale**:
- **Stateful**: Agent remembers past trades, positions
- **Risk-aware**: Tracks exposure by sector, correlation
- **Queryable**: Easy to check limits before trading

### 2.4. Risk Manager (`live/risk.py`)

```python
@dataclass
class RiskLimits:
    """Portfolio-level risk limits."""
    max_total_notional: float = 10_000.0
    max_sector_notional: float = 3_000.0
    max_single_position: float = 500.0
    max_daily_loss: float = 500.0
    max_correlation_risk: float = 0.3
    min_bankroll: float = 100.0


@dataclass
class RiskCheckResult:
    """Result of pre-trade risk check."""
    approved: bool
    violations: list[str]
    adjusted_size: float | None = None  # Suggested size reduction


class RiskManager:
    """Pre-trade risk checks."""

    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def check_trade(
        self,
        proposed_order: ProposedOrder,
        context: TradingContext,
        market: MarketSnapshot
    ) -> RiskCheckResult:
        """Check if trade passes risk limits."""
        violations = []

        # Check 1: Total exposure
        new_exposure = context.total_exposure + proposed_order.size
        if new_exposure > self.limits.max_total_notional:
            violations.append(f"Total exposure limit: {new_exposure:.1f} > {self.limits.max_total_notional:.1f}")

        # Check 2: Sector exposure
        sector_exposure = context.sector_exposure.get(market.category, 0.0) + proposed_order.size
        if sector_exposure > self.limits.max_sector_notional:
            violations.append(f"Sector exposure limit for {market.category}: {sector_exposure:.1f} > {self.limits.max_sector_notional:.1f}")

        # Check 3: Single position size
        if proposed_order.size > self.limits.max_single_position:
            violations.append(f"Single position limit: {proposed_order.size:.1f} > {self.limits.max_single_position:.1f}")

        # Check 4: Daily loss limit
        if context.daily_pnl < -self.limits.max_daily_loss:
            violations.append(f"Daily loss limit: {context.daily_pnl:.1f} < -{self.limits.max_daily_loss:.1f}")

        # Check 5: Correlation risk
        corr_risk = context.get_correlation_risk(market)
        if corr_risk > self.limits.max_correlation_risk:
            violations.append(f"Correlation risk: {corr_risk:.2f} > {self.limits.max_correlation_risk:.2f}")

        # Check 6: Minimum bankroll
        if context.bankroll < self.limits.min_bankroll:
            violations.append(f"Below minimum bankroll: {context.bankroll:.1f} < {self.limits.min_bankroll:.1f}")

        approved = len(violations) == 0

        # If size is the issue, suggest reduction
        adjusted_size = None
        if not approved and proposed_order.size > self.limits.max_single_position:
            adjusted_size = self.limits.max_single_position

        return RiskCheckResult(
            approved=approved,
            violations=violations,
            adjusted_size=adjusted_size
        )
```

**Rationale**:
- **Pre-trade checks**: Block bad trades before submission
- **Multi-dimensional**: Total exposure, sector limits, correlation
- **Graceful degradation**: Suggests size reduction instead of rejecting outright

### 2.5. Backtest Engine (`backtest/engine.py`)

```python
from typing import Callable

@dataclass
class BacktestConfig:
    """Configuration for backtest."""
    train_fraction: float = 0.7
    validation_fraction: float = 0.15
    test_fraction: float = 0.15
    walk_forward_window: int | None = None  # If set, use walk-forward
    random_seed: int = 42


@dataclass
class BacktestResults:
    """Results from a backtest run."""
    metrics: BacktestMetrics
    trades: list[TradeRecord]
    forecasts: list[ForecastRecord]
    config: dict[str, Any]
    timestamp: datetime

    # Split metrics
    train_metrics: BacktestMetrics | None = None
    val_metrics: BacktestMetrics | None = None
    test_metrics: BacktestMetrics | None = None


class BacktestEngine:
    """Rigorous backtesting with train/test splits."""

    def __init__(self, simulator: OrderBookSimulator, risk_manager: RiskManager):
        self.simulator = simulator
        self.risk_manager = risk_manager

    def run_backtest(
        self,
        strategy: Strategy,
        dataset: Dataset,
        config: BacktestConfig,
        initial_bankroll: float = 1000.0
    ) -> BacktestResults:
        """Run backtest with train/test split."""

        # Split dataset
        train_data, val_data, test_data = dataset.split(
            train_frac=config.train_fraction,
            val_frac=config.validation_fraction,
            test_frac=config.test_fraction,
            random_seed=config.random_seed
        )

        # Run on each split
        train_results = self._run_on_split(strategy, train_data, initial_bankroll)
        val_results = self._run_on_split(strategy, val_data, initial_bankroll)
        test_results = self._run_on_split(strategy, test_data, initial_bankroll)

        # Combine
        return BacktestResults(
            metrics=test_results.metrics,      # Report test metrics as primary
            trades=test_results.trades,
            forecasts=test_results.forecasts,
            config=strategy.get_config(),
            timestamp=datetime.now(),
            train_metrics=train_results.metrics,
            val_metrics=val_results.metrics,
            test_metrics=test_results.metrics
        )

    def run_walk_forward(
        self,
        strategy: Strategy,
        dataset: Dataset,
        train_window: int,
        test_window: int,
        initial_bankroll: float = 1000.0
    ) -> list[BacktestResults]:
        """Run walk-forward validation."""
        results = []
        for i in range(0, len(dataset) - train_window - test_window, test_window):
            train_data = dataset[i:i + train_window]
            test_data = dataset[i + train_window:i + train_window + test_window]

            # Optionally retrain strategy on train_data
            # (For AutoPredict, this would mean re-calibrating hyperparameters)

            result = self._run_on_split(strategy, test_data, initial_bankroll)
            results.append(result)

        return results

    def run_parameter_sweep(
        self,
        strategy_class: type[Strategy],
        dataset: Dataset,
        param_grid: dict[str, list[Any]],
        config: BacktestConfig
    ) -> list[tuple[dict[str, Any], BacktestResults]]:
        """Run grid search over parameter space."""
        results = []

        # Generate all parameter combinations
        from itertools import product
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())

        for param_combo in product(*param_values):
            params = dict(zip(param_names, param_combo))

            # Create strategy with these params
            strategy = strategy_class.from_config(params)

            # Run backtest
            result = self.run_backtest(strategy, dataset, config)
            results.append((params, result))

        # Sort by test Sharpe ratio
        results.sort(key=lambda x: x[1].test_metrics.sharpe, reverse=True)
        return results

    def _run_on_split(
        self,
        strategy: Strategy,
        data: Dataset,
        initial_bankroll: float
    ) -> BacktestResults:
        """Run backtest on a single data split."""
        context = TradingContext(bankroll=initial_bankroll, positions={}, pending_orders={})
        trades = []
        forecasts = []

        for market_snapshot in data:
            # Strategy evaluates market
            proposal = strategy.evaluate_market(market_snapshot, context)
            if proposal is None:
                continue

            # Risk check
            risk_check = self.risk_manager.check_trade(proposal, context, market_snapshot)
            if not risk_check.approved:
                continue

            # Simulate execution
            execution_report = self.simulator.execute(proposal, market_snapshot.order_book)

            # Update context
            if execution_report.filled_size > 0:
                trade = TradeRecord(...)
                trades.append(trade)
                context.trade_history.append(trade)
                context.bankroll += trade.pnl

            # Record forecast
            forecast = ForecastRecord(...)
            forecasts.append(forecast)

        # Calculate metrics
        metrics = calculate_metrics(forecasts, trades)

        return BacktestResults(
            metrics=metrics,
            trades=trades,
            forecasts=forecasts,
            config=strategy.get_config(),
            timestamp=datetime.now()
        )
```

**Rationale**:
- **Train/test split**: Prevents overfitting
- **Walk-forward validation**: More realistic than static split
- **Parameter sweeps**: Automate hyperparameter search
- **Composable**: Easy to add cross-validation, bootstrapping

### 2.6. Self-Improvement Loop (`learning/optimizer.py`)

```python
from typing import Callable
import optuna  # Bayesian optimization library

class BayesianOptimizer:
    """Bayesian hyperparameter optimization."""

    def __init__(
        self,
        backtest_engine: BacktestEngine,
        dataset: Dataset,
        objective_metric: str = "sharpe"
    ):
        self.backtest_engine = backtest_engine
        self.dataset = dataset
        self.objective_metric = objective_metric

    def optimize(
        self,
        strategy_class: type[Strategy],
        param_space: dict[str, tuple[float, float]],  # {param: (min, max)}
        n_trials: int = 50
    ) -> dict[str, Any]:
        """Find best hyperparameters using Bayesian optimization."""

        def objective(trial: optuna.Trial) -> float:
            # Sample parameters
            params = {
                name: trial.suggest_float(name, bounds[0], bounds[1])
                for name, bounds in param_space.items()
            }

            # Create strategy
            strategy = strategy_class.from_config(params)

            # Run backtest
            result = self.backtest_engine.run_backtest(
                strategy=strategy,
                dataset=self.dataset,
                config=BacktestConfig()
            )

            # Return objective (use validation set to prevent overfitting)
            if result.val_metrics is None:
                return result.metrics.get(self.objective_metric, 0.0)
            return result.val_metrics.get(self.objective_metric, 0.0)

        # Run optimization
        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_trials)

        return study.best_params


class EvolutionaryOptimizer:
    """Genetic algorithm for strategy evolution."""

    def __init__(
        self,
        backtest_engine: BacktestEngine,
        dataset: Dataset,
        population_size: int = 20,
        mutation_rate: float = 0.1
    ):
        self.backtest_engine = backtest_engine
        self.dataset = dataset
        self.population_size = population_size
        self.mutation_rate = mutation_rate

    def evolve(
        self,
        strategy_class: type[Strategy],
        param_space: dict[str, tuple[float, float]],
        n_generations: int = 10
    ) -> list[dict[str, Any]]:
        """Evolve population of strategies."""

        # Initialize population
        population = self._initialize_population(param_space)

        for generation in range(n_generations):
            # Evaluate fitness
            fitness_scores = []
            for params in population:
                strategy = strategy_class.from_config(params)
                result = self.backtest_engine.run_backtest(strategy, self.dataset, BacktestConfig())
                fitness_scores.append(result.val_metrics.sharpe)

            # Select parents (top 50%)
            sorted_idx = sorted(range(len(fitness_scores)), key=lambda i: fitness_scores[i], reverse=True)
            parents = [population[i] for i in sorted_idx[:self.population_size // 2]]

            # Create next generation
            population = parents.copy()
            while len(population) < self.population_size:
                # Crossover
                parent1, parent2 = random.sample(parents, 2)
                child = self._crossover(parent1, parent2)

                # Mutation
                if random.random() < self.mutation_rate:
                    child = self._mutate(child, param_space)

                population.append(child)

        # Return best strategies
        return population[:5]

    def _initialize_population(self, param_space: dict[str, tuple[float, float]]) -> list[dict[str, Any]]:
        """Random initialization."""
        return [
            {name: random.uniform(bounds[0], bounds[1]) for name, bounds in param_space.items()}
            for _ in range(self.population_size)
        ]

    def _crossover(self, parent1: dict, parent2: dict) -> dict:
        """Single-point crossover."""
        child = {}
        for key in parent1:
            child[key] = parent1[key] if random.random() < 0.5 else parent2[key]
        return child

    def _mutate(self, params: dict, param_space: dict[str, tuple[float, float]]) -> dict:
        """Gaussian mutation."""
        mutated = params.copy()
        for key, (min_val, max_val) in param_space.items():
            if random.random() < 0.3:  # 30% chance to mutate each param
                noise = random.gauss(0, (max_val - min_val) * 0.1)
                mutated[key] = max(min_val, min(max_val, mutated[key] + noise))
        return mutated
```

**Rationale**:
- **Bayesian optimization**: Efficient hyperparameter search (uses past results to guide future trials)
- **Genetic algorithm**: Explores diverse strategies, good for multi-modal optimization
- **Validation-based**: Uses validation set to prevent overfitting
- **Extensible**: Easy to add other optimizers (grid search, random search, etc.)

---

## 3. Agent Loop Architecture

### Sense → Think → Act → Learn

```
┌─────────────────────────────────────────────────────────────┐
│                      TradingAgent                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │ 1. SENSE (Market Data)                             │    │
│  │  - Fetch markets from venue adapters               │    │
│  │  - Update order book snapshots                     │    │
│  │  - Monitor existing positions                      │    │
│  └────────────────┬───────────────────────────────────┘    │
│                   │                                         │
│                   ▼                                         │
│  ┌────────────────────────────────────────────────────┐    │
│  │ 2. THINK (Strategy Evaluation)                     │    │
│  │  - Select active strategy (policy)                 │    │
│  │  - Evaluate each market with strategy              │    │
│  │  - Generate order proposals                        │    │
│  │  - Prioritize by expected value                    │    │
│  └────────────────┬───────────────────────────────────┘    │
│                   │                                         │
│                   ▼                                         │
│  ┌────────────────────────────────────────────────────┐    │
│  │ 3. ACT (Risk Check + Execution)                    │    │
│  │  - Risk manager validates proposals                │    │
│  │  - Submit approved orders to venue                 │    │
│  │  - Track order status                              │    │
│  │  - Update context (positions, exposure)            │    │
│  └────────────────┬───────────────────────────────────┘    │
│                   │                                         │
│                   ▼                                         │
│  ┌────────────────────────────────────────────────────┐    │
│  │ 4. LEARN (Performance Analysis)                    │    │
│  │  - Calculate metrics (Sharpe, Brier, slippage)     │    │
│  │  - Identify weaknesses                             │    │
│  │  - Propose hyperparameter adjustments              │    │
│  │  - Log experiments (MLflow)                        │    │
│  └────────────────┬───────────────────────────────────┘    │
│                   │                                         │
│                   └─────────────► (Loop back to SENSE)      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Implementation (`agents/trading_agent.py`)

```python
class TradingAgent:
    """Main trading agent with sense-think-act-learn loop."""

    def __init__(
        self,
        market_adapter: MarketDataAdapter,
        execution_adapter: OrderExecutionAdapter,
        strategy: Strategy,
        risk_manager: RiskManager,
        context: TradingContext
    ):
        self.market_adapter = market_adapter
        self.execution_adapter = execution_adapter
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.context = context

    async def run_iteration(self) -> None:
        """Run one iteration of sense-think-act-learn loop."""

        # 1. SENSE: Fetch markets
        markets = await self.market_adapter.fetch_markets()
        logger.info(f"Sensed {len(markets)} markets")

        # 2. THINK: Evaluate markets
        proposals = []
        for market in markets:
            proposal = self.strategy.evaluate_market(market, self.context)
            if proposal is not None:
                proposals.append((market, proposal))

        logger.info(f"Generated {len(proposals)} proposals")

        # 3. ACT: Risk check + execute
        for market, proposal in proposals:
            # Risk check
            risk_check = self.risk_manager.check_trade(proposal, self.context, market)
            if not risk_check.approved:
                logger.warning(f"Risk check failed for {market.market_id}: {risk_check.violations}")
                continue

            # Submit order
            try:
                order_confirmation = await self.execution_adapter.submit_order(
                    market_id=proposal.market_id,
                    side=proposal.side,
                    size=proposal.size,
                    order_type=proposal.order_type,
                    limit_price=proposal.limit_price
                )
                logger.info(f"Order submitted: {order_confirmation.order_id}")

                # Update context
                self.context.pending_orders[order_confirmation.order_id] = order_confirmation

            except Exception as e:
                logger.error(f"Order submission failed for {market.market_id}: {e}")

        # 4. LEARN: Performance analysis (done periodically, not every iteration)
        if self._should_analyze_performance():
            metrics = self._calculate_recent_metrics()
            analysis = self.strategy.analyze_performance(metrics)
            logger.info(f"Performance analysis: {analysis}")

    def _should_analyze_performance(self) -> bool:
        """Check if it's time to analyze performance (e.g., every 24 hours or 100 trades)."""
        return len(self.context.trade_history) % 100 == 0

    def _calculate_recent_metrics(self) -> BacktestMetrics:
        """Calculate metrics on recent trades."""
        recent_trades = self.context.trade_history[-100:]
        # Calculate Sharpe, Brier, etc.
        return calculate_metrics([], recent_trades)
```

**Rationale**:
- **Async**: Non-blocking I/O for live trading
- **Clear phases**: Each phase has one responsibility
- **Error handling**: Exceptions don't crash the loop
- **Logging**: Every action logged for monitoring

---

## 4. Configuration System

### 4.1. Schema (`config/schema.py`)

Use **Pydantic** for type-safe configs with validation:

```python
from pydantic import BaseModel, Field, field_validator

class AgentConfig(BaseModel):
    """Agent hyperparameters."""
    min_edge: float = Field(0.05, ge=0.0, le=1.0, description="Minimum edge to trade")
    aggressive_edge: float = Field(0.12, ge=0.0, le=1.0)
    max_risk_fraction: float = Field(0.02, ge=0.0, le=0.5)
    max_position_notional: float = Field(25.0, ge=0.0)
    min_book_liquidity: float = Field(60.0, ge=0.0)
    max_spread_pct: float = Field(0.04, ge=0.0, le=1.0)
    max_depth_fraction: float = Field(0.15, ge=0.0, le=1.0)

    @field_validator("aggressive_edge")
    def aggressive_must_exceed_min(cls, v, values):
        if "min_edge" in values and v < values["min_edge"]:
            raise ValueError("aggressive_edge must be >= min_edge")
        return v


class RiskConfig(BaseModel):
    """Risk limits."""
    max_total_notional: float = Field(10_000.0, ge=0.0)
    max_sector_notional: float = Field(3_000.0, ge=0.0)
    max_single_position: float = Field(500.0, ge=0.0)
    max_daily_loss: float = Field(500.0, ge=0.0)
    max_correlation_risk: float = Field(0.3, ge=0.0, le=1.0)


class VenueConfig(BaseModel):
    """Venue API credentials."""
    name: str
    api_key: str
    api_secret: str | None = None
    base_url: str


class SystemConfig(BaseModel):
    """Top-level config."""
    agent: AgentConfig
    risk: RiskConfig
    venues: list[VenueConfig]
    strategy: str = "autopredict"
    mode: str = Field("paper", pattern="^(paper|live|backtest)$")
```

### 4.2. Config Files (YAML)

```yaml
# config/production.yaml
agent:
  min_edge: 0.05
  aggressive_edge: 0.12
  max_risk_fraction: 0.02
  max_position_notional: 25.0
  min_book_liquidity: 60.0
  max_spread_pct: 0.04
  max_depth_fraction: 0.15

risk:
  max_total_notional: 10000.0
  max_sector_notional: 3000.0
  max_single_position: 500.0
  max_daily_loss: 500.0
  max_correlation_risk: 0.3

venues:
  - name: polymarket
    api_key: ${POLYMARKET_API_KEY}
    base_url: https://api.polymarket.com

  - name: manifold
    api_key: ${MANIFOLD_API_KEY}
    base_url: https://api.manifold.markets

strategy: autopredict
mode: paper  # paper | live | backtest
```

**Rationale**:
- **Type-safe**: Pydantic validates types and ranges
- **Environment variables**: Secrets via `${ENV_VAR}` (no hardcoded credentials)
- **Multiple configs**: Easy to have `dev.yaml`, `prod.yaml`, `backtest.yaml`

---

## 5. Data Flow for Live Trading

```
┌──────────────────────────────────────────────────────────────┐
│                    Live Trading System                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────┐         ┌─────────────────┐             │
│  │  Polymarket    │◄────────┤ Market Adapters │             │
│  │  (WebSocket)   │         │                 │             │
│  └────────────────┘         │  - Polymarket   │             │
│                             │  - Manifold     │             │
│  ┌────────────────┐         │  - Kalshi       │             │
│  │  Manifold      │◄────────┤                 │             │
│  │  (REST API)    │         └────────┬────────┘             │
│  └────────────────┘                  │                      │
│                                      │ MarketSnapshot       │
│  ┌────────────────┐                  │                      │
│  │  Kalshi        │◄─────────────────┘                      │
│  │  (WebSocket)   │                                         │
│  └────────────────┘                  │                      │
│                                      ▼                      │
│                        ┌──────────────────────────┐         │
│                        │   TradingAgent           │         │
│                        │  - Sense                 │         │
│                        │  - Think (Strategy)      │         │
│                        │  - Act (Risk + Execute)  │         │
│                        │  - Learn                 │         │
│                        └──────────┬───────────────┘         │
│                                   │ ProposedOrder           │
│                                   ▼                         │
│                        ┌──────────────────────────┐         │
│                        │   RiskManager            │         │
│                        │  - Pre-trade checks      │         │
│                        │  - Position limits       │         │
│                        │  - Sector limits         │         │
│                        └──────────┬───────────────┘         │
│                                   │ Approved                │
│                                   ▼                         │
│                        ┌──────────────────────────┐         │
│                        │   OrderExecutor          │         │
│                        │  - Submit orders         │         │
│                        │  - Track fills           │         │
│                        │  - Handle errors         │         │
│                        └──────────┬───────────────┘         │
│                                   │ OrderConfirmation       │
│                                   ▼                         │
│  ┌────────────────┐    ┌──────────────────────────┐         │
│  │  Polymarket    │◄───┤   Venue APIs             │         │
│  │  (Submit)      │    └──────────────────────────┘         │
│  └────────────────┘                                         │
│                                   │                         │
│  ┌────────────────┐               │ Fill notifications      │
│  │  Database      │◄──────────────┘                         │
│  │  (Positions)   │                                         │
│  └────────────────┘                                         │
│                                                              │
│  ┌────────────────────────────────────────────────┐         │
│  │  Monitoring & Logging                          │         │
│  │  - Prometheus metrics                          │         │
│  │  - Structured logging (JSON)                   │         │
│  │  - Alerts (PagerDuty, Slack)                   │         │
│  └────────────────────────────────────────────────┘         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Migration from Current Architecture

### What to Keep As-Is

1. **market_env.py** → Move to `backtest/simulator.py` and `backtest/metrics.py`
   - OrderBook class (depth-aware execution)
   - ExecutionEngine (market/limit simulation)
   - Metrics calculation (Brier, Sharpe, slippage)

2. **agent.py** → Rename to `strategies/autopredict.py`
   - Keep ExecutionStrategy
   - Keep AutoPredictAgent (rename to AutoPredictStrategy)
   - Keep AgentConfig (move to config/schema.py)

3. **validation/** → Move to `data/validation.py`
   - Keep FairProbValidator
   - Keep MarketDataValidator

4. **scripts/generate_dataset.py** → Keep in `scripts/`
   - Useful for generating synthetic test data

### What to Refactor

1. **run_experiment.py** → Replace with `backtest/engine.py`
   - Add train/test split
   - Add walk-forward validation
   - Add parameter sweeps

2. **cli.py** → Expand with new commands
   - Keep `backtest` command
   - Add `live` command
   - Add `optimize` command
   - Add `monitor` command

3. **examples/adapters.py** → Implement real adapters in `markets/`
   - Replace simulated Polymarket with real API
   - Add Manifold, Kalshi

### What to Add (New)

1. **markets/** - Venue adapters (new)
2. **strategies/** - Strategy registry (new)
3. **agents/** - Agent loop (new)
4. **backtest/** - Proper backtest engine (new)
5. **live/** - Live trading execution (new)
6. **learning/** - Self-improvement loop (new)
7. **config/** - Pydantic schemas (new)
8. **utils/** - Logging, errors (new)

---

## 7. Testing Strategy

### Unit Tests
- Each module independently testable
- Mock all external dependencies (API calls, WebSocket)
- Test edge cases (empty order book, crossed book, API errors)

### Integration Tests
- End-to-end backtest (load dataset → run strategy → calculate metrics)
- Multi-venue market fetching (parallel API calls)
- Order submission flow (submit → track → fill)

### Property-Based Tests
Use `hypothesis` library to test invariants:
- `filled_size <= requested_size` (always)
- `total_exposure <= max_total_notional` (always)
- `book.get_spread() >= 0` (always)

### Performance Tests
- Backtest 10,000 markets in < 10 seconds
- Live trading loop < 100ms latency

---

## 8. Deployment Architecture

### Development Mode
```bash
python -m autopredict.cli backtest --config dev.yaml --dataset datasets/sample_markets.json
```

### Paper Trading Mode
```bash
python -m autopredict.cli live --config paper.yaml --mode paper
```
- Fetches real market data
- Simulates order execution (no real money)
- Logs all decisions

### Live Trading Mode
```bash
python -m autopredict.cli live --config prod.yaml --mode live
```
- Fetches real market data
- Submits real orders (real money!)
- Requires API keys in environment variables
- Risk manager enforces limits

### Monitoring
- **Prometheus metrics**: Expose `/metrics` endpoint
  - Trades per minute
  - Fill rate
  - Slippage
  - Current exposure
- **Structured logging**: JSON logs to stdout
  - Ingest to Elasticsearch / CloudWatch
- **Alerts**: PagerDuty / Slack
  - Daily loss > threshold
  - API errors
  - Risk limit violations

---

## 9. Rationale for Design Choices

### Why async/await?
- **Live trading requires non-blocking I/O**
  - Fetch markets from 3 venues in parallel (3x speedup)
  - Submit orders without blocking
  - Stream WebSocket updates
- **Python's asyncio is production-ready**
  - Used by major trading firms
  - Good library ecosystem (aiohttp, websockets)

### Why Pydantic for config?
- **Type safety**: Catch errors at load time, not runtime
- **Validation**: Automatic range checks, custom validators
- **Documentation**: Schema doubles as API docs
- **IDE support**: Autocomplete, type checking

### Why Protocol over ABC for Strategy?
- **Flexibility**: No inheritance required (duck typing)
- **Composability**: Easy to wrap strategies (logging, caching)
- **Testing**: Easy to create mock strategies

### Why separate backtest/ and live/?
- **Different concerns**:
  - Backtest: Historical simulation, train/test splits, parameter sweeps
  - Live: Real-time execution, error handling, monitoring
- **Safety**: Can't accidentally run backtest code in production

### Why registry pattern for strategies?
- **Extensibility**: Users can register custom strategies
- **Config-driven**: Create strategies from YAML/JSON
- **Discoverability**: `StrategyRegistry.list()` shows all available strategies

---

## 10. Next Steps

See **MIGRATION_PLAN.md** for step-by-step refactoring plan.

**Summary of changes**:
1. Reorganize modules into clean package structure
2. Implement real market adapters (Polymarket, Manifold, Kalshi)
3. Build strategy abstraction layer + registry
4. Build proper backtest engine with train/test splits
5. Build portfolio-level risk manager
6. Build self-improvement loop with Bayesian optimization
7. Add comprehensive logging and monitoring

**Effort estimate**: 6-8 weeks for full implementation.
