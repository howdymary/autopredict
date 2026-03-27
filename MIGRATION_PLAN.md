# AutoPredict: Migration Plan

**Prepared by**: Agent 6 (Software Architect) & Agent 5 (Data/ML Engineer)
**Date**: 2026-03-26

---

## Executive Summary

This document provides a **step-by-step plan** to migrate AutoPredict from its current minimal structure to the proposed target architecture. The migration is designed to be **incremental** - each phase is self-contained and testable.

**Total estimated time**: 6-8 weeks (1 developer)

**Phases**:
1. **Phase 1**: Reorganize package structure (1 week)
2. **Phase 2**: Build data layer and proper backtesting (2 weeks)
3. **Phase 3**: Build strategy abstraction layer (1 week)
4. **Phase 4**: Build market adapters (2 weeks)
5. **Phase 5**: Build risk management and agent loop (1 week)
6. **Phase 6**: Build self-improvement loop (1-2 weeks)

---

## Phase 1: Reorganize Package Structure (Week 1)

### Goal
Clean up root-level modules into proper package structure.

### Tasks

#### 1.1. Create New Package Structure

```bash
mkdir -p autopredict/markets
mkdir -p autopredict/data
mkdir -p autopredict/strategies
mkdir -p autopredict/agents
mkdir -p autopredict/backtest
mkdir -p autopredict/live
mkdir -p autopredict/config
mkdir -p autopredict/learning
mkdir -p autopredict/utils
```

**Files to create**:
```bash
touch autopredict/markets/__init__.py
touch autopredict/data/__init__.py
touch autopredict/strategies/__init__.py
touch autopredict/agents/__init__.py
touch autopredict/backtest/__init__.py
touch autopredict/live/__init__.py
touch autopredict/config/__init__.py
touch autopredict/learning/__init__.py
touch autopredict/utils/__init__.py
```

#### 1.2. Move Existing Modules

**market_env.py → Split into backtest/**

```bash
# Create new files
touch autopredict/backtest/simulator.py
touch autopredict/backtest/metrics.py
```

**Move code**:
- `market_env.py` lines 28-222 (OrderBook, BookLevel) → `backtest/simulator.py`
- `market_env.py` lines 244-462 (ExecutionEngine) → `backtest/simulator.py`
- `market_env.py` lines 464-707 (metrics functions) → `backtest/metrics.py`

**Update imports**:
```python
# Old
from autopredict.market_env import OrderBook, ExecutionEngine

# New
from autopredict.backtest.simulator import OrderBook, ExecutionEngine
from autopredict.backtest.metrics import calculate_metrics, evaluate_all
```

**agent.py → Rename to strategies/autopredict.py**

```bash
mv autopredict/agent.py autopredict/strategies/autopredict.py
```

**Update imports**:
```python
# Old
from autopredict.agent import AutoPredictAgent, AgentConfig

# New
from autopredict.strategies.autopredict import AutoPredictAgent, AgentConfig
```

**validation.py + validation/validator.py → Consolidate to data/validation.py**

```bash
# Merge both validators
cat autopredict/validation.py > autopredict/data/validation.py
cat autopredict/validation/validator.py >> autopredict/data/validation.py

# Remove old files
rm autopredict/validation.py
rm -rf autopredict/validation/
```

**Update imports**:
```python
# Old
from autopredict.validation import FairProbValidator
from autopredict.validation.validator import MarketDataValidator

# New
from autopredict.data.validation import FairProbValidator, MarketDataValidator
```

**calibration_analysis.py → Move to scripts/**

```bash
mv autopredict/calibration_analysis.py autopredict/scripts/calibration_analysis.py
```

#### 1.3. Update All Import Statements

**Files to update**:
- `run_experiment.py`
- `cli.py`
- `tests/test_agent.py`
- `tests/test_market_env.py`
- `tests/test_validation.py`
- `examples/**/*.py`

**Script to help**:
```bash
# Find all Python files
find autopredict -name "*.py" -type f

# Search for old import patterns
grep -r "from autopredict.agent import" autopredict/
grep -r "from autopredict.market_env import" autopredict/
grep -r "from autopredict.validation import" autopredict/

# Replace with new imports (manually or with sed)
```

#### 1.4. Create utils/logging.py

**Purpose**: Centralized logging setup (replace all `print()` calls).

**Create file**: `autopredict/utils/logging.py`

```python
"""Centralized logging configuration for AutoPredict."""

import logging
import sys
from typing import Optional

def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    json_format: bool = False
) -> logging.Logger:
    """Configure logging for AutoPredict.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path to write logs
        json_format: If True, use JSON structured logging

    Returns:
        Configured logger
    """
    # Create logger
    logger = logging.getLogger("autopredict")
    logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Format
    if json_format:
        # Structured logging (for production)
        import json
        from datetime import datetime

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno
                }
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_data)

        formatter = JsonFormatter()
    else:
        # Human-readable (for development)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

# Create default logger
logger = setup_logging()
```

**Usage**:
```python
from autopredict.utils.logging import logger

# Replace print() calls
# Before:
print(f"Loaded {len(markets)} markets")

# After:
logger.info(f"Loaded {len(markets)} markets")
```

#### 1.5. Create utils/errors.py

**Purpose**: Custom exceptions for better error handling.

**Create file**: `autopredict/utils/errors.py`

```python
"""Custom exceptions for AutoPredict."""

class AutoPredictError(Exception):
    """Base exception for AutoPredict."""
    pass


class ConfigurationError(AutoPredictError):
    """Raised when configuration is invalid."""
    pass


class ValidationError(AutoPredictError):
    """Raised when data validation fails."""
    pass


class RiskCheckError(AutoPredictError):
    """Raised when trade fails risk checks."""
    pass


class MarketAdapterError(AutoPredictError):
    """Raised when market adapter fails."""
    pass


class OrderExecutionError(AutoPredictError):
    """Raised when order execution fails."""
    pass
```

#### 1.6. Run Tests

After reorganization, all tests must pass:

```bash
pytest tests/ -v
```

**Fix any import errors**. Update test files to use new import paths.

#### 1.7. Update Documentation

**Files to update**:
- `README.md`: Update import examples
- `ARCHITECTURE.md`: Update file paths
- `QUICKSTART.md`: Update import examples

### Phase 1 Deliverables

- ✅ Clean package structure
- ✅ All modules in proper locations
- ✅ Centralized logging
- ✅ Custom exceptions
- ✅ All tests passing
- ✅ Updated documentation

**Estimated time**: 3-5 days

---

## Phase 2: Build Data Layer and Proper Backtesting (Weeks 2-3)

### Goal
Implement rigorous backtesting with train/test splits, walk-forward validation, and parameter sweeps.

### Tasks

#### 2.1. Create Data Loaders (`data/loaders.py`)

**Purpose**: Load datasets from various formats.

```python
"""Dataset loaders for AutoPredict."""

from pathlib import Path
from typing import List
import json
import pandas as pd

from autopredict.utils.logging import logger
from autopredict.utils.errors import ValidationError

class Dataset:
    """Container for market snapshots."""

    def __init__(self, markets: List[dict]):
        self.markets = markets

    def __len__(self) -> int:
        return len(self.markets)

    def __getitem__(self, idx) -> dict:
        return self.markets[idx]

    def split(self, train_frac: float = 0.7, val_frac: float = 0.15, test_frac: float = 0.15, random_seed: int = 42):
        """Split dataset into train/val/test."""
        import random
        random.seed(random_seed)

        shuffled = self.markets.copy()
        random.shuffle(shuffled)

        n = len(shuffled)
        train_end = int(n * train_frac)
        val_end = train_end + int(n * val_frac)

        return (
            Dataset(shuffled[:train_end]),
            Dataset(shuffled[train_end:val_end]),
            Dataset(shuffled[val_end:])
        )


def load_json(path: str | Path) -> Dataset:
    """Load dataset from JSON file."""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    with open(path, 'r') as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValidationError(f"Expected list of markets, got {type(data)}")

    logger.info(f"Loaded {len(data)} markets from {path}")
    return Dataset(data)


def load_csv(path: str | Path) -> Dataset:
    """Load dataset from CSV file."""
    df = pd.read_csv(path)

    # Convert to list of dicts
    markets = df.to_dict('records')

    logger.info(f"Loaded {len(markets)} markets from {path}")
    return Dataset(markets)
```

#### 2.2. Create Backtest Engine (`backtest/engine.py`)

**Purpose**: Proper backtest with train/test split.

**Code**: See ARCHITECTURE_PROPOSAL.md section 2.5 for full implementation.

**Key features**:
- `run_backtest()`: Run with train/val/test split
- `run_walk_forward()`: Walk-forward validation
- `run_parameter_sweep()`: Grid search over hyperparameters

#### 2.3. Create Splits Utility (`backtest/splits.py`)

```python
"""Train/test split utilities."""

from typing import Tuple, List
import random

def time_series_split(data: List[dict], train_frac: float = 0.7) -> Tuple[List[dict], List[dict]]:
    """Split time series data (no shuffling)."""
    n = len(data)
    split_idx = int(n * train_frac)
    return data[:split_idx], data[split_idx:]


def walk_forward_splits(
    data: List[dict],
    train_window: int,
    test_window: int
) -> List[Tuple[List[dict], List[dict]]]:
    """Generate walk-forward splits."""
    splits = []
    for i in range(0, len(data) - train_window - test_window, test_window):
        train = data[i:i + train_window]
        test = data[i + train_window:i + train_window + test_window]
        splits.append((train, test))
    return splits
```

#### 2.4. Update run_experiment.py to Use New Engine

**Old**: Simple loop in `run_experiment.py`

**New**: Use `BacktestEngine`

```python
"""Experiment runner using BacktestEngine."""

from autopredict.backtest.engine import BacktestEngine, BacktestConfig
from autopredict.backtest.simulator import ExecutionEngine
from autopredict.data.loaders import load_json
from autopredict.strategies.autopredict import AutoPredictAgent
from autopredict.live.risk import RiskManager, RiskLimits
from autopredict.utils.logging import logger

def run_backtest(config_path, dataset_path, strategy_guidance_path=None, starting_bankroll=1000.0):
    """Run backtest with train/test split."""

    # Load data
    dataset = load_json(dataset_path)

    # Load agent config
    import json
    with open(config_path) as f:
        agent_config_dict = json.load(f)

    # Create agent
    agent = AutoPredictAgent.from_mapping(agent_config_dict)

    # Create risk manager
    risk_manager = RiskManager(RiskLimits())

    # Create backtest engine
    simulator = ExecutionEngine()
    engine = BacktestEngine(simulator, risk_manager)

    # Run backtest
    results = engine.run_backtest(
        strategy=agent,
        dataset=dataset,
        config=BacktestConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15),
        initial_bankroll=starting_bankroll
    )

    logger.info(f"Backtest complete. Test Sharpe: {results.test_metrics.sharpe:.2f}")

    return results.metrics
```

#### 2.5. Add Statistical Tests (`backtest/statistics.py`)

```python
"""Statistical significance tests for backtesting."""

import numpy as np
from typing import List
from scipy import stats

def sharpe_ratio_significance(
    sharpe_A: float,
    sharpe_B: float,
    n_trades_A: int,
    n_trades_B: int,
    alpha: float = 0.05
) -> dict:
    """Test if Sharpe ratio difference is statistically significant.

    Uses Jobson-Korkie test.
    """
    # Standard error of Sharpe difference
    se = np.sqrt((1 + 0.5 * sharpe_A**2) / n_trades_A + (1 + 0.5 * sharpe_B**2) / n_trades_B)

    # Z-statistic
    z = (sharpe_A - sharpe_B) / se

    # P-value (two-tailed)
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    return {
        "sharpe_A": sharpe_A,
        "sharpe_B": sharpe_B,
        "z_statistic": z,
        "p_value": p_value,
        "significant": p_value < alpha,
        "conclusion": f"Strategy A {'significantly' if p_value < alpha else 'not significantly'} better than Strategy B"
    }


def bootstrap_confidence_interval(
    trades: List[float],
    metric_fn,
    n_bootstrap: int = 1000,
    confidence: float = 0.95
) -> dict:
    """Bootstrap confidence interval for a metric.

    Args:
        trades: List of PnL values
        metric_fn: Function to calculate metric (e.g., lambda x: np.mean(x) / np.std(x))
        n_bootstrap: Number of bootstrap samples
        confidence: Confidence level

    Returns:
        Dict with mean, lower_bound, upper_bound
    """
    boot_metrics = []

    for _ in range(n_bootstrap):
        sample = np.random.choice(trades, size=len(trades), replace=True)
        boot_metrics.append(metric_fn(sample))

    lower_percentile = (1 - confidence) / 2 * 100
    upper_percentile = (1 + confidence) / 2 * 100

    return {
        "mean": np.mean(boot_metrics),
        "lower_bound": np.percentile(boot_metrics, lower_percentile),
        "upper_bound": np.percentile(boot_metrics, upper_percentile),
        "confidence": confidence
    }
```

### Phase 2 Deliverables

- ✅ Data loaders (JSON, CSV)
- ✅ BacktestEngine with train/val/test split
- ✅ Walk-forward validation
- ✅ Parameter sweep
- ✅ Statistical significance tests
- ✅ Updated run_experiment.py
- ✅ New tests for backtest engine

**Estimated time**: 1.5-2 weeks

---

## Phase 3: Build Strategy Abstraction Layer (Week 4)

### Goal
Decouple strategy implementations from core framework. Enable pluggable strategies.

### Tasks

#### 3.1. Create Strategy Protocol (`strategies/base.py`)

```python
"""Base strategy protocol."""

from typing import Protocol, Any, Optional
from autopredict.agents.context import TradingContext
from autopredict.backtest.simulator import MarketSnapshot, ProposedOrder
from autopredict.backtest.metrics import BacktestMetrics

class Strategy(Protocol):
    """Strategy protocol (duck typing)."""

    def evaluate_market(
        self,
        market: MarketSnapshot,
        context: TradingContext
    ) -> Optional[ProposedOrder]:
        """Evaluate market and return order proposal."""
        ...

    def analyze_performance(
        self,
        metrics: BacktestMetrics,
        guidance: str = ""
    ) -> dict[str, str]:
        """Analyze performance and identify weaknesses."""
        ...

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Strategy":
        """Create strategy from config dict."""
        ...

    def get_config(self) -> dict[str, Any]:
        """Return current config as dict."""
        ...
```

#### 3.2. Create Strategy Registry (`strategies/registry.py`)

**Code**: See ARCHITECTURE_PROPOSAL.md section 2.2 for full implementation.

#### 3.3. Refactor AutoPredictAgent to Use Protocol

**File**: `strategies/autopredict.py`

**Changes**:
- Rename `AutoPredictAgent` → `AutoPredictStrategy`
- Implement `Strategy` protocol
- Register with `StrategyRegistry`

```python
"""AutoPredict strategy (original implementation)."""

from autopredict.strategies.base import Strategy
from autopredict.strategies.registry import StrategyRegistry

@StrategyRegistry.register("autopredict")
class AutoPredictStrategy:
    """Original AutoPredict strategy."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.execution = ExecutionStrategy()

    def evaluate_market(self, market: MarketSnapshot, context: TradingContext) -> ProposedOrder | None:
        # Same as before
        ...

    def analyze_performance(self, metrics: BacktestMetrics, guidance: str = "") -> dict[str, str]:
        # Same as before
        ...

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "AutoPredictStrategy":
        agent_config = AgentConfig(**config)
        return cls(agent_config)

    def get_config(self) -> dict[str, Any]:
        return {
            "min_edge": self.config.min_edge,
            "aggressive_edge": self.config.aggressive_edge,
            # ... all config fields
        }
```

#### 3.4. Implement Example Strategies

**Mean Reversion Strategy** (`strategies/mean_reversion.py`):

```python
"""Mean reversion strategy."""

from autopredict.strategies.base import Strategy
from autopredict.strategies.registry import StrategyRegistry

@StrategyRegistry.register("mean_reversion")
class MeanReversionStrategy:
    """Buy when market is below fair value, sell when above."""

    def __init__(self, reversion_threshold: float = 0.10):
        self.reversion_threshold = reversion_threshold

    def evaluate_market(self, market: MarketSnapshot, context: TradingContext) -> ProposedOrder | None:
        edge = market.fair_prob - market.market_prob

        # Only trade if edge exceeds reversion threshold
        if abs(edge) < self.reversion_threshold:
            return None

        # Check if price is far from fair value (mean reversion signal)
        # Use more aggressive sizing when price is very far from fair
        size_scale = min(abs(edge) / self.reversion_threshold, 3.0)
        base_size = 10.0
        size = base_size * size_scale

        side = "buy" if edge > 0 else "sell"

        return ProposedOrder(
            market_id=market.market_id,
            side=side,
            order_type="limit",
            size=size,
            limit_price=market.order_book.get_mid_price(),
            rationale=f"Mean reversion: edge={edge:.3f}, size_scale={size_scale:.2f}"
        )

    @classmethod
    def from_config(cls, config: dict) -> "MeanReversionStrategy":
        return cls(reversion_threshold=config.get("reversion_threshold", 0.10))

    def get_config(self) -> dict:
        return {"reversion_threshold": self.reversion_threshold}
```

**Ensemble Strategy** (`strategies/ensemble.py`):

```python
"""Ensemble of multiple strategies."""

from typing import List
from autopredict.strategies.base import Strategy
from autopredict.strategies.registry import StrategyRegistry

@StrategyRegistry.register("ensemble")
class EnsembleStrategy:
    """Weighted ensemble of strategies."""

    def __init__(self, strategies: List[Strategy], weights: List[float]):
        assert len(strategies) == len(weights)
        assert abs(sum(weights) - 1.0) < 1e-6, "Weights must sum to 1.0"

        self.strategies = strategies
        self.weights = weights

    def evaluate_market(self, market: MarketSnapshot, context: TradingContext) -> ProposedOrder | None:
        proposals = []

        # Get proposals from each strategy
        for strategy in self.strategies:
            proposal = strategy.evaluate_market(market, context)
            if proposal is not None:
                proposals.append(proposal)

        if not proposals:
            return None

        # Weighted average of sizes
        total_size = sum(
            proposal.size * weight
            for proposal, weight in zip(proposals, self.weights[:len(proposals)])
        )

        # Use most common side
        sides = [p.side for p in proposals]
        most_common_side = max(set(sides), key=sides.count)

        return ProposedOrder(
            market_id=market.market_id,
            side=most_common_side,
            order_type="limit",
            size=total_size,
            limit_price=market.order_book.get_mid_price(),
            rationale=f"Ensemble of {len(proposals)} strategies"
        )
```

#### 3.5. Update CLI to Support Multiple Strategies

**cli.py**:

```python
def command_backtest(args: argparse.Namespace) -> None:
    defaults = _load_defaults()

    # NEW: Strategy selection
    strategy_name = args.strategy or defaults.get("default_strategy", "autopredict")
    strategy = StrategyRegistry.create(strategy_name, config_dict)

    # Run backtest with selected strategy
    results = run_backtest(strategy=strategy, ...)
```

**Add CLI argument**:
```python
backtest.add_argument("--strategy", help="Strategy name (autopredict, mean_reversion, ensemble)")
```

### Phase 3 Deliverables

- ✅ Strategy protocol
- ✅ Strategy registry
- ✅ AutoPredictStrategy (refactored)
- ✅ MeanReversionStrategy
- ✅ EnsembleStrategy
- ✅ Updated CLI
- ✅ Tests for all strategies

**Estimated time**: 5-7 days

---

## Phase 4: Build Market Adapters (Weeks 5-6)

### Goal
Implement real API integrations for Polymarket, Manifold, and Kalshi.

### Tasks

#### 4.1. Create Base Adapter Interface (`markets/base.py`)

**Code**: See ARCHITECTURE_PROPOSAL.md section 2.1 for full implementation.

#### 4.2. Implement Polymarket Adapter (`markets/polymarket.py`)

**Research Polymarket API**:
- REST API documentation: https://docs.polymarket.com
- WebSocket documentation for real-time updates
- Authentication (API key, signature)

**Implementation**:
```python
"""Polymarket adapter."""

import aiohttp
import asyncio
from typing import List, AsyncIterator, Optional

from autopredict.markets.base import MarketDataAdapter, OrderExecutionAdapter, MarketSnapshot
from autopredict.backtest.simulator import OrderBook, BookLevel
from autopredict.utils.logging import logger
from autopredict.utils.errors import MarketAdapterError

class PolymarketAdapter(MarketDataAdapter, OrderExecutionAdapter):
    """Polymarket REST + WebSocket adapter."""

    BASE_URL = "https://api.polymarket.com/v1"
    WS_URL = "wss://api.polymarket.com/v1/ws"

    def __init__(self, api_key: str, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def fetch_markets(self, filters: dict | None = None) -> List[MarketSnapshot]:
        """Fetch markets from Polymarket REST API."""
        if not self.session:
            raise MarketAdapterError("Session not initialized. Use 'async with' context.")

        # Build request
        url = f"{self.BASE_URL}/markets"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = filters or {}

        try:
            async with self.session.get(url, headers=headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()

            markets = []
            for item in data["markets"]:
                market = self._parse_market(item)
                markets.append(market)

            logger.info(f"Fetched {len(markets)} markets from Polymarket")
            return markets

        except aiohttp.ClientError as e:
            raise MarketAdapterError(f"Failed to fetch markets: {e}")

    async def stream_markets(self) -> AsyncIterator[MarketSnapshot]:
        """Stream market updates via WebSocket."""
        import websockets

        async with websockets.connect(self.WS_URL) as ws:
            # Subscribe to market updates
            await ws.send(json.dumps({"action": "subscribe", "channel": "markets"}))

            async for message in ws:
                data = json.loads(message)
                market = self._parse_market(data)
                yield market

    async def get_order_book(self, market_id: str) -> OrderBook:
        """Fetch order book for specific market."""
        url = f"{self.BASE_URL}/markets/{market_id}/orderbook"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with self.session.get(url, headers=headers) as response:
            response.raise_for_status()
            data = await response.json()

        return self._parse_order_book(market_id, data)

    async def submit_order(
        self,
        market_id: str,
        side: str,
        size: float,
        order_type: str,
        limit_price: Optional[float] = None
    ):
        """Submit order to Polymarket."""
        url = f"{self.BASE_URL}/orders"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "market_id": market_id,
            "side": side,
            "size": size,
            "type": order_type,
            "price": limit_price
        }

        async with self.session.post(url, headers=headers, json=payload) as response:
            response.raise_for_status()
            data = await response.json()

        logger.info(f"Order submitted: {data['order_id']}")
        return data

    def _parse_market(self, item: dict) -> MarketSnapshot:
        """Parse Polymarket API response into MarketSnapshot."""
        return MarketSnapshot(
            venue="polymarket",
            market_id=item["id"],
            question=item["question"],
            category=item.get("category", "unknown"),
            market_prob=item["current_price"],
            time_to_expiry_hours=self._calculate_expiry(item["end_date"]),
            order_book=self._parse_order_book(item["id"], item.get("orderbook", {})),
            metadata={"polymarket_data": item}
        )

    def _parse_order_book(self, market_id: str, data: dict) -> OrderBook:
        """Parse order book from API response."""
        bids = [BookLevel(float(b["price"]), float(b["size"])) for b in data.get("bids", [])]
        asks = [BookLevel(float(a["price"]), float(a["size"])) for a in data.get("asks", [])]

        return OrderBook(
            market_id=market_id,
            bids=bids,
            asks=asks
        )
```

#### 4.3. Implement Manifold Adapter (`markets/manifold.py`)

Similar to Polymarket, but using Manifold's API:
- API docs: https://docs.manifold.markets/api
- Different authentication (API key in headers)
- Different data format

#### 4.4. Implement Kalshi Adapter (`markets/kalshi.py`)

Similar structure, Kalshi API specifics.

#### 4.5. Create Simulator Adapter (`markets/simulator.py`)

**Purpose**: For backtesting, use simulated data (current behavior).

```python
"""Simulator adapter for backtesting."""

from typing import List, AsyncIterator, Optional
from autopredict.markets.base import MarketDataAdapter
from autopredict.data.loaders import Dataset

class SimulatorAdapter(MarketDataAdapter):
    """Adapter for simulated/historical data."""

    def __init__(self, dataset: Dataset):
        self.dataset = dataset
        self.index = 0

    async def fetch_markets(self, filters: dict | None = None) -> List[MarketSnapshot]:
        """Return all markets from dataset."""
        return [self._parse_market(m) for m in self.dataset.markets]

    async def stream_markets(self) -> AsyncIterator[MarketSnapshot]:
        """Stream markets one at a time."""
        for market in self.dataset.markets:
            yield self._parse_market(market)

    def _parse_market(self, market_dict: dict) -> MarketSnapshot:
        """Convert dataset dict to MarketSnapshot."""
        return MarketSnapshot(
            venue="simulator",
            market_id=market_dict["market_id"],
            question=market_dict.get("question", ""),
            category=market_dict.get("category", "unknown"),
            market_prob=market_dict["market_prob"],
            time_to_expiry_hours=market_dict["time_to_expiry_hours"],
            order_book=self._build_order_book(market_dict),
            metadata=market_dict
        )
```

### Phase 4 Deliverables

- ✅ Base adapter interface
- ✅ Polymarket adapter (REST + WebSocket)
- ✅ Manifold adapter
- ✅ Kalshi adapter
- ✅ Simulator adapter
- ✅ Integration tests (mock API responses)

**Estimated time**: 2 weeks (most time-consuming phase)

---

## Phase 5: Build Risk Management and Agent Loop (Week 7)

### Goal
Implement portfolio-level risk management and stateful agent loop.

### Tasks

#### 5.1. Create TradingContext (`agents/context.py`)

**Code**: See ARCHITECTURE_PROPOSAL.md section 2.3.

#### 5.2. Create RiskManager (`live/risk.py`)

**Code**: See ARCHITECTURE_PROPOSAL.md section 2.4.

#### 5.3. Create TradingAgent (`agents/trading_agent.py`)

**Code**: See ARCHITECTURE_PROPOSAL.md section 3.

#### 5.4. Create Live Executor (`live/executor.py`)

```python
"""Live order execution with tracking."""

from typing import Dict, List
import asyncio
from autopredict.markets.base import OrderExecutionAdapter
from autopredict.utils.logging import logger

class LiveExecutor:
    """Manages live order execution and tracking."""

    def __init__(self, adapter: OrderExecutionAdapter):
        self.adapter = adapter
        self.pending_orders: Dict[str, Order] = {}

    async def submit_and_track(self, proposal: ProposedOrder) -> str:
        """Submit order and start tracking."""
        try:
            confirmation = await self.adapter.submit_order(
                market_id=proposal.market_id,
                side=proposal.side,
                size=proposal.size,
                order_type=proposal.order_type,
                limit_price=proposal.limit_price
            )

            order_id = confirmation["order_id"]
            self.pending_orders[order_id] = confirmation

            # Start background task to monitor fills
            asyncio.create_task(self._monitor_order(order_id))

            return order_id

        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            raise

    async def _monitor_order(self, order_id: str):
        """Monitor order status until filled or cancelled."""
        while order_id in self.pending_orders:
            await asyncio.sleep(5)  # Poll every 5 seconds

            try:
                status = await self.adapter.get_order_status(order_id)

                if status["status"] == "filled":
                    logger.info(f"Order {order_id} filled")
                    del self.pending_orders[order_id]

                elif status["status"] == "cancelled":
                    logger.info(f"Order {order_id} cancelled")
                    del self.pending_orders[order_id]

            except Exception as e:
                logger.error(f"Failed to check order status: {e}")
```

#### 5.5. Update CLI for Live Trading

```python
def command_live(args: argparse.Namespace) -> None:
    """Run live trading."""
    config = load_config(args.config)

    # Create market adapter
    if config.venue == "polymarket":
        adapter = PolymarketAdapter(api_key=config.api_key)
    elif config.venue == "manifold":
        adapter = ManifoldAdapter(api_key=config.api_key)
    else:
        raise ValueError(f"Unknown venue: {config.venue}")

    # Create strategy
    strategy = StrategyRegistry.create(config.strategy, config.agent)

    # Create risk manager
    risk_manager = RiskManager(config.risk)

    # Create agent
    context = TradingContext(bankroll=config.starting_bankroll, positions={}, pending_orders={})
    agent = TradingAgent(adapter, adapter, strategy, risk_manager, context)

    # Run agent loop
    asyncio.run(agent.run_loop())
```

### Phase 5 Deliverables

- ✅ TradingContext
- ✅ RiskManager
- ✅ TradingAgent
- ✅ LiveExecutor
- ✅ Updated CLI for live trading
- ✅ Tests for risk checks
- ✅ Integration tests for agent loop

**Estimated time**: 5-7 days

---

## Phase 6: Build Self-Improvement Loop (Week 8+)

### Goal
Autonomous hyperparameter optimization and strategy evolution.

### Tasks

#### 6.1. Install Optimization Libraries

```bash
pip install optuna scikit-optimize
```

#### 6.2. Implement Bayesian Optimizer (`learning/optimizer.py`)

**Code**: See ARCHITECTURE_PROPOSAL.md section 2.6.

#### 6.3. Implement Evolutionary Optimizer (`learning/evolution.py`)

**Code**: See ARCHITECTURE_PROPOSAL.md section 2.6.

#### 6.4. Create Experiment Tracker (`learning/experiment.py`)

**Option 1: MLflow** (recommended)

```bash
pip install mlflow
```

```python
"""Experiment tracking with MLflow."""

import mlflow
from typing import Dict, Any

class ExperimentTracker:
    """Track experiments with MLflow."""

    def __init__(self, experiment_name: str):
        mlflow.set_experiment(experiment_name)

    def log_backtest(self, strategy_name: str, config: Dict[str, Any], metrics: BacktestMetrics):
        """Log a backtest run."""
        with mlflow.start_run(run_name=strategy_name):
            # Log parameters
            for key, value in config.items():
                mlflow.log_param(key, value)

            # Log metrics
            mlflow.log_metric("sharpe", metrics.sharpe)
            mlflow.log_metric("brier_score", metrics.brier_score)
            mlflow.log_metric("total_pnl", metrics.total_pnl)
            mlflow.log_metric("max_drawdown", metrics.max_drawdown)
            mlflow.log_metric("avg_slippage_bps", metrics.avg_slippage_bps)

            # Log artifacts (e.g., plots)
            # mlflow.log_artifact("backtest_report.html")
```

**Option 2: Weights & Biases**

```bash
pip install wandb
```

Similar interface to MLflow.

#### 6.5. Create CLI Command for Optimization

```bash
python -m autopredict.cli optimize --strategy autopredict --dataset datasets/sample_markets_100.json --n-trials 50
```

**CLI implementation**:

```python
def command_optimize(args: argparse.Namespace) -> None:
    """Run hyperparameter optimization."""
    # Load dataset
    dataset = load_json(args.dataset)

    # Create backtest engine
    engine = BacktestEngine(...)

    # Create optimizer
    optimizer = BayesianOptimizer(engine, dataset, objective_metric="sharpe")

    # Define parameter space
    param_space = {
        "min_edge": (0.01, 0.15),
        "aggressive_edge": (0.05, 0.25),
        "max_risk_fraction": (0.01, 0.05),
        "max_position_notional": (10.0, 50.0)
    }

    # Run optimization
    best_params = optimizer.optimize(
        strategy_class=AutoPredictStrategy,
        param_space=param_space,
        n_trials=args.n_trials
    )

    logger.info(f"Best parameters: {best_params}")

    # Save best config
    with open("config/optimized.json", "w") as f:
        json.dump(best_params, f, indent=2)
```

### Phase 6 Deliverables

- ✅ Bayesian optimizer
- ✅ Evolutionary optimizer
- ✅ Experiment tracker (MLflow or W&B)
- ✅ CLI optimize command
- ✅ Documentation for optimization workflow

**Estimated time**: 1-2 weeks

---

## Testing Strategy

### Unit Tests
For each new module, write unit tests:

```bash
# Example: Test risk manager
pytest tests/test_risk_manager.py -v
```

**Test coverage targets**:
- Core modules: 90%+
- Risk-critical code: 100% (RiskManager, OrderExecutor)
- Adapters: 70%+ (hard to test without real APIs)

### Integration Tests
End-to-end tests:

```bash
# Test full backtest
pytest tests/integration/test_backtest_flow.py

# Test live trading (with mocked adapters)
pytest tests/integration/test_live_trading.py
```

### Regression Tests
Save baseline results, detect performance degradation:

```bash
# Run regression test
python scripts/run_regression_test.py

# Compare to baseline
python scripts/compare_to_baseline.py
```

---

## Deployment Checklist

### Before Going Live

- [ ] All tests passing (unit + integration)
- [ ] Logging configured (JSON format for production)
- [ ] Error handling comprehensive (no uncaught exceptions)
- [ ] Risk limits tested (submit oversized order → should reject)
- [ ] API credentials in environment variables (not hardcoded)
- [ ] Monitoring dashboard (Grafana + Prometheus)
- [ ] Alerts configured (PagerDuty / Slack)
- [ ] Dry-run on paper trading for 1 week
- [ ] Review all trades manually
- [ ] Backtest on out-of-sample data (last 3 months)
- [ ] Document runbooks (what to do if X goes wrong)

### Production Monitoring

**Metrics to track**:
- Trades per hour
- Fill rate
- Slippage (vs expected)
- Current exposure (total, by sector)
- Daily PnL
- API error rate
- Risk limit violations

**Alerts**:
- Daily loss > $500
- API error rate > 5%
- Risk limit violated
- No trades for 6 hours (system stuck?)

---

## Timeline Summary

| Phase | Task | Duration | Deliverables |
|-------|------|----------|--------------|
| 1 | Reorganize packages | 3-5 days | Clean structure, logging, errors |
| 2 | Data layer + backtesting | 1.5-2 weeks | BacktestEngine, train/test split, stats |
| 3 | Strategy abstraction | 5-7 days | Strategy protocol, registry, examples |
| 4 | Market adapters | 2 weeks | Polymarket, Manifold, Kalshi adapters |
| 5 | Risk + agent loop | 5-7 days | RiskManager, TradingAgent, LiveExecutor |
| 6 | Self-improvement | 1-2 weeks | Bayesian optimizer, experiment tracker |

**Total**: 6-8 weeks (assuming 1 developer, full-time)

---

## Risk Mitigation

### What Could Go Wrong?

1. **API rate limits**: Polymarket may throttle requests
   - **Mitigation**: Add rate limiting, request queuing

2. **WebSocket disconnections**: Network issues
   - **Mitigation**: Auto-reconnect with exponential backoff

3. **Order submission failures**: API errors
   - **Mitigation**: Retry logic, fallback to other venues

4. **Overfitting in optimization**: Bayesian optimizer finds overfit params
   - **Mitigation**: Always validate on out-of-sample data, use regularization

5. **Risk limits too tight**: Agent can't trade
   - **Mitigation**: Tune limits in paper trading first

---

## Final Notes

This migration plan is designed to be **incremental and testable**. Each phase is self-contained - you can stop at any phase and have a working system.

**Recommended order**:
1. Phase 1 (reorganization) - foundational
2. Phase 2 (backtesting) - enables proper evaluation
3. Phase 3 (strategies) - enables experimentation
4. Phase 4 (adapters) - enables live trading
5. Phase 5 (risk + agent loop) - production-ready
6. Phase 6 (self-improvement) - autonomous optimization

**Questions? Contact**:
- Agent 6 (Software Architect) for architecture questions
- Agent 5 (Data/ML Engineer) for optimization and backtesting questions
