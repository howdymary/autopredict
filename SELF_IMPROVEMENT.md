# Self-Improvement Loop Documentation

## Overview

The AutoPredict self-improvement system provides automated tools for analyzing trading performance, identifying systematic failures, and tuning strategy parameters through backtesting. The system learns from historical decisions to continuously improve strategy performance.

## Architecture

### Core Components

1. **Trade Logger** (`autopredict/learning/logger.py`)
   - Structured logging of all trading decisions
   - JSONL format for efficient streaming analysis
   - Tracks decision context, execution, and outcomes

2. **Performance Analyzer** (`autopredict/learning/analyzer.py`)
   - Analyzes trade logs to identify patterns
   - Detects systematic failure regimes
   - Generates actionable recommendations

3. **Parameter Tuner** (`autopredict/learning/tuner.py`)
   - Grid search over parameter combinations
   - Backtest-based validation
   - Automated best-parameter selection

4. **Learning Workflow** (`scripts/learn_and_improve.py`)
   - Orchestrates the complete improvement loop
   - Integrates analysis, tuning, and validation
   - Saves improved configurations

## Trade Logging

### TradeLog Structure

Every trading decision is logged with full context:

```python
from autopredict.learning.logger import TradeLog, TradeLogger
from datetime import datetime, timezone

log = TradeLog(
    timestamp=datetime.now(timezone.utc),
    market_id="politics-2025-election",
    market_prob=0.45,        # Market's implied probability
    model_prob=0.65,         # Our model's forecast
    edge=0.20,               # Absolute edge
    decision="buy",          # "buy", "sell", or "pass"
    size=20.0,               # Position size
    execution_price=0.46,    # Actual fill price
    outcome=None,            # Filled in when market resolves
    pnl=None,                # Calculated after outcome known
    rationale={              # Full decision context
        "order_type": "limit",
        "spread_pct": 0.02,
        "liquidity_depth": 200.0,
        "time_to_expiry_hours": 48.0,
        "category": "politics",
        "min_edge_threshold": 0.05,
    }
)
```

### Using the Logger

```python
from pathlib import Path
from autopredict.learning.logger import TradeLogger

# Initialize logger
logger = TradeLogger(Path("state/trades"))

# Log a single trade
logger.append(log)

# Log multiple trades efficiently
logger.append_batch([log1, log2, log3])

# Load logs for analysis
all_logs = logger.load_all()
recent_logs = logger.load_recent(days=7)
market_logs = logger.load_by_market("politics-2025-election")

# Update outcomes when markets resolve
market_outcomes = {
    "politics-2025-election": 1,  # Resolved YES
    "sports-2025-superbowl": 0,   # Resolved NO
}
updated_count = logger.update_outcomes(market_outcomes)
```

### Log File Format

Logs are stored in daily JSONL files: `state/trades/trades_YYYYMMDD.jsonl`

Each line is a complete JSON object:
```json
{"timestamp": "2025-03-26T10:30:00Z", "market_id": "politics-2025-election", "market_prob": 0.45, ...}
{"timestamp": "2025-03-26T11:15:00Z", "market_id": "sports-2025-superbowl", "market_prob": 0.52, ...}
```

This format enables:
- Efficient streaming analysis of large log files
- Easy incremental processing (process one line at a time)
- Simple append-only writes (no file locking issues)

## Performance Analysis

### Basic Analysis

```python
from autopredict.learning.analyzer import PerformanceAnalyzer

# Load logs and analyze
logs = logger.load_recent(days=30)
analyzer = PerformanceAnalyzer(logs)
report = analyzer.generate_report()

# Print summary
print(f"Total trades: {report.total_trades}")
print(f"Total PnL: ${report.total_pnl:.2f}")
print(f"Win rate: {report.win_rate:.2%}")
print(f"Sharpe ratio: {report.sharpe_ratio:.3f}")
print(f"Calibration error: {report.calibration_error:.3f}")
print(f"Edge capture rate: {report.edge_capture_rate:.2%}")
```

### Dimensional Analysis

Analyze performance across different dimensions:

```python
# Performance by individual market
market_stats = analyzer.analyze_by_market()
for market_id, stats in market_stats.items():
    print(f"{market_id}: {stats['trades']} trades, ${stats['pnl']:.2f} PnL")

# Performance by category
category_stats = analyzer.analyze_by_category("category")
for category, stats in category_stats.items():
    print(f"{category}: {stats['win_rate']:.1%} win rate")

# Performance by any feature in rationale
liquidity_stats = analyzer.analyze_by_category("liquidity_depth")
```

### Failure Regime Identification

The analyzer automatically identifies systematic failure patterns:

```python
failures = analyzer.identify_failure_regimes()
for regime in failures:
    print(f"⚠️  {regime}")

# Example output:
# ⚠️  Wide spreads (>5%): -$15.2 PnL over 8 trades
# ⚠️  Low liquidity (<50): -$8.4 PnL over 5 trades
# ⚠️  Sports category: calibration error 0.18 over 12 trades
```

### Recommendations

Get actionable recommendations for parameter tuning:

```python
recommendations = analyzer.generate_recommendations()
for rec in recommendations:
    print(f"💡 {rec}")

# Example output:
# 💡 Reduce max_spread_pct threshold (currently allowing spreads that hurt performance)
# 💡 Increase min_book_liquidity threshold (thin order books causing losses)
# 💡 Model calibration error high (16.2%). Consider increasing min_edge threshold.
```

## Parameter Tuning

### Grid Search

Define a parameter grid and search for optimal configuration:

```python
from autopredict.learning.tuner import ParameterGrid, GridSearchTuner, BacktestResult

# Define parameter grid
param_grid = ParameterGrid({
    "min_edge": [0.03, 0.05, 0.08, 0.10],
    "aggressive_edge": [0.10, 0.12, 0.15],
    "max_risk_fraction": [0.01, 0.02, 0.03],
})

# This grid has 4 × 3 × 3 = 36 configurations

# Define backtest function
def backtest_with_params(params: dict) -> BacktestResult:
    """Run backtest with given parameters and return result."""
    # 1. Create strategy config with params
    # 2. Run backtest on validation dataset
    # 3. Collect metrics
    # 4. Return BacktestResult

    # Example:
    from autopredict.backtest import BacktestEngine
    engine = BacktestEngine(strategy_params=params, ...)
    metrics = engine.run(validation_data)

    return BacktestResult(
        params=params,
        total_pnl=metrics["total_pnl"],
        sharpe_ratio=metrics["sharpe_ratio"],
        win_rate=metrics["win_rate"],
        total_trades=metrics["total_trades"],
        calibration_error=metrics["calibration_error"],
        edge_capture_rate=metrics["edge_capture_rate"],
    )

# Run grid search
tuner = GridSearchTuner(
    param_grid=param_grid,
    backtest_fn=backtest_with_params,
    verbose=True,
)

best_params, best_result = tuner.tune()

print(f"Best parameters: {best_params}")
print(f"Expected Sharpe: {best_result.sharpe_ratio:.3f}")

# Get top N configurations
top_5 = tuner.get_top_n(5)
for i, (params, result) in enumerate(top_5, 1):
    print(f"{i}. Score: {result.score():.4f}, Params: {params}")

# Save results
tuner.save_results(Path("tuning_results.json"))
```

### Auto-Generated Grids

Create a grid centered on current parameters:

```python
from autopredict.learning.tuner import create_param_grid_from_current

current_params = {
    "min_edge": 0.05,
    "aggressive_edge": 0.12,
    "max_risk_fraction": 0.02,
}

# Create grid with ±30% perturbation, 3 steps above/below
param_grid = create_param_grid_from_current(
    current_params,
    perturbation_factor=0.3,
    n_steps=3,
)

# This creates a grid around current values:
# min_edge: [0.035, 0.0425, 0.05, 0.0575, 0.065]
# aggressive_edge: [0.084, 0.102, 0.12, 0.138, 0.156]
# max_risk_fraction: [0.014, 0.017, 0.02, 0.023, 0.026]
```

### Custom Scoring Functions

Define how to score backtest results:

```python
def sharpe_focused_scoring(result: BacktestResult) -> float:
    """Prioritize Sharpe ratio with calibration bonus."""
    if result.sharpe_ratio is None or result.total_trades < 20:
        return -1000.0  # Need minimum trades

    # Bonus for good calibration
    calibration_bonus = max(0, 1.0 - result.calibration_error)
    return result.sharpe_ratio * (1.0 + calibration_bonus * 0.2)

tuner = GridSearchTuner(
    param_grid=param_grid,
    backtest_fn=backtest_with_params,
    scoring_fn=sharpe_focused_scoring,
)
```

## CLI Commands

### Analyze Recent Performance

```bash
# Analyze all logs
python -m autopredict.cli learn analyze --log-dir state/trades

# Analyze last 7 days
python -m autopredict.cli learn analyze --log-dir state/trades --days 7

# Save full report to JSON
python -m autopredict.cli learn analyze \
  --log-dir state/trades \
  --output reports/performance_2025-03-26.json
```

### Tune Strategy Parameters

For advanced parameter tuning, use the standalone script:

```bash
# Tune with auto-generated grid
python scripts/learn_and_improve.py tune \
  --config strategy_configs/default.json \
  --perturbation 0.2 \
  --steps 3 \
  --output configs/strategy_tuned.json

# Tune with custom grid
python scripts/learn_and_improve.py tune \
  --config strategy_configs/default.json \
  --grid-config tuning/custom_grid.json \
  --output configs/strategy_tuned.json
```

Custom grid format (`tuning/custom_grid.json`):
```json
{
  "min_edge": [0.03, 0.05, 0.08, 0.10],
  "aggressive_edge": [0.10, 0.12, 0.15],
  "max_risk_fraction": [0.01, 0.02, 0.03]
}
```

### Run Full Improvement Loop

```bash
# Analyze recent performance, tune parameters, and save if improved
python scripts/learn_and_improve.py improve \
  --config strategy_configs/default.json \
  --log-dir state/trades \
  --days 30 \
  --perturbation 0.2 \
  --steps 3 \
  --min-improvement 0.05 \
  --auto-save
```

Parameters:
- `--config`: Current strategy configuration
- `--log-dir`: Directory with trade logs
- `--days`: Days of history to analyze
- `--perturbation`: Parameter variation (0.2 = ±20%)
- `--steps`: Grid search granularity
- `--min-improvement`: Minimum Sharpe improvement to save
- `--auto-save`: Automatically save if improvement found

## Learning Loop Workflow

### Complete Self-Improvement Cycle

```python
from pathlib import Path
from autopredict.learning.logger import TradeLogger
from autopredict.learning.analyzer import PerformanceAnalyzer
from autopredict.learning.tuner import GridSearchTuner, create_param_grid_from_current

# Step 1: Load recent trade logs
logger = TradeLogger(Path("state/trades"))
logs = logger.load_recent(days=30)

# Step 2: Analyze performance
analyzer = PerformanceAnalyzer(logs)
report = analyzer.generate_report()

print(f"Current performance: ${report.total_pnl:.2f} PnL, "
      f"{report.win_rate:.1%} win rate")

# Step 3: Identify weak spots
failures = analyzer.identify_failure_regimes()
for regime in failures:
    print(f"⚠️  {regime}")

recommendations = analyzer.generate_recommendations()
for rec in recommendations:
    print(f"💡 {rec}")

# Step 4: Propose parameter updates
current_config = load_config("configs/strategy.json")
param_grid = create_param_grid_from_current(
    current_config,
    perturbation_factor=0.2,
    n_steps=3,
)

tuner = GridSearchTuner(param_grid, backtest_fn=run_backtest)
new_params, new_result = tuner.tune()

# Step 5: Validate on holdout
current_sharpe = report.sharpe_ratio or 0.0
new_sharpe = new_result.sharpe_ratio or 0.0
improvement = new_sharpe - current_sharpe

# Step 6: If better, update config
if improvement > 0.05:  # 0.05 Sharpe improvement threshold
    save_config("configs/strategy_improved.json", new_params)
    print(f"✅ Improvement found! +{improvement:.3f} Sharpe")
    print(f"New config saved. To activate:")
    print(f"  mv configs/strategy_improved.json configs/strategy.json")
else:
    print(f"ℹ️  No significant improvement ({improvement:.3f} Sharpe change)")
    print(f"Current configuration is already well-tuned.")
```

## Integration with Backtest Engine

The learning system integrates with the backtest engine to validate parameter changes:

```python
def run_backtest_with_params(params: dict) -> BacktestResult:
    """Run backtest with given parameters."""
    from autopredict.backtest import BacktestEngine
    from autopredict.agent import AgentConfig

    # Create agent config with new parameters
    agent_config = AgentConfig(**params)

    # Run backtest on validation dataset
    engine = BacktestEngine(
        agent_config=agent_config,
        dataset=validation_data,
        starting_bankroll=1000.0,
    )

    result = engine.run()

    # Convert to BacktestResult for tuner
    return BacktestResult(
        params=params,
        total_pnl=result.final_pnl,
        sharpe_ratio=result.sharpe_ratio,
        win_rate=result.win_rate,
        total_trades=len(result.trades),
        calibration_error=result.calibration_error,
        edge_capture_rate=result.edge_capture / result.predicted_edge,
    )
```

## Best Practices

### 1. Regular Analysis

Run performance analysis weekly:
```bash
# Weekly performance review
python -m autopredict.cli learn analyze \
  --log-dir state/trades \
  --days 7 \
  --output reports/weekly_$(date +%Y%m%d).json
```

### 2. Incremental Tuning

Don't make large parameter changes all at once:
- Use `perturbation_factor=0.1` to `0.2` for safe exploration
- Increase `n_steps` for finer granularity
- Validate on holdout data before deploying

### 3. Track Configuration History

Version your strategy configurations:
```bash
configs/
  strategy_20250301.json  # March 1 version
  strategy_20250315.json  # March 15 version (tuned)
  strategy_20250326.json  # March 26 version (current)
```

### 4. Monitor Key Metrics

Track these metrics over time:
- **Sharpe Ratio**: Risk-adjusted returns
- **Calibration Error**: Model accuracy
- **Edge Capture Rate**: Execution quality
- **Win Rate**: Success percentage

### 5. Failure Regime Response

When failure regimes are identified:
1. Analyze the specific markets/conditions
2. Adjust thresholds to avoid those regimes
3. Re-run backtest to validate improvement
4. Consider adding explicit filters

Example: If "Wide spreads (>5%)" causes losses:
```python
# Before:
config = {"max_spread_pct": 0.06}

# After tuning:
config = {"max_spread_pct": 0.04}  # Stricter threshold
```

## Advanced Topics

### Custom Analyzers

Extend `PerformanceAnalyzer` for domain-specific analysis:

```python
class CustomAnalyzer(PerformanceAnalyzer):
    def analyze_by_time_of_day(self) -> dict:
        """Analyze performance by hour of day."""
        hourly_stats = defaultdict(lambda: {"trades": 0, "pnl": 0.0})

        for log in self.resolved_logs:
            hour = log.timestamp.hour
            hourly_stats[hour]["trades"] += 1
            if log.pnl:
                hourly_stats[hour]["pnl"] += log.pnl

        return dict(hourly_stats)
```

### Bayesian Optimization (Future)

Placeholder for more efficient parameter search:

```python
from autopredict.learning.tuner import BayesianTuner

# Future implementation with Optuna
tuner = BayesianTuner(
    param_space={
        "min_edge": (0.01, 0.20),  # Continuous ranges
        "aggressive_edge": (0.05, 0.30),
        "max_risk_fraction": (0.005, 0.05),
    },
    backtest_fn=run_backtest_with_params,
    n_trials=100,  # Much more efficient than grid search
)

best_params = tuner.tune()
```

### Reinforcement Learning (Future)

The logging infrastructure supports RL-based learning:

```python
# Trade logs provide (state, action, reward) tuples
for log in logs:
    state = {
        "market_prob": log.market_prob,
        "model_prob": log.model_prob,
        "spread_pct": log.rationale["spread_pct"],
        "liquidity_depth": log.rationale["liquidity_depth"],
    }
    action = log.decision  # "buy", "sell", "pass"
    reward = log.pnl or 0.0

    # Feed to RL agent for policy learning
    rl_agent.observe(state, action, reward)
```

## Troubleshooting

### No Trade Logs Found

If analysis shows no logs:
1. Check log directory: `ls -la state/trades/`
2. Ensure backtests are generating logs
3. Verify logger is initialized in backtest code

### Grid Search Too Slow

If grid search takes too long:
1. Reduce grid size: fewer parameter values
2. Use `perturbation_factor=0.1` and `n_steps=2`
3. Parallelize backtest runs (future enhancement)
4. Consider Bayesian optimization (future)

### Poor Calibration

If calibration error is consistently high:
1. Review model probability generation
2. Check if model is overfitting
3. Increase `min_edge` threshold
4. Consider ensemble forecasts

### Low Edge Capture

If edge capture rate is low:
1. Increase use of limit orders (reduce `aggressive_edge`)
2. Avoid wide spreads (reduce `max_spread_pct`)
3. Check for slippage in backtests
4. Analyze execution prices vs. market prices

## Next Steps

After implementing the self-improvement loop:

1. **Run Initial Analysis**
   ```bash
   python -m autopredict.cli learn analyze --log-dir state/trades
   ```

2. **Tune Parameters**
   ```bash
   python scripts/learn_and_improve.py tune --config configs/default.json
   ```

3. **Set Up Automated Improvement**
   - Run weekly: `learn_and_improve.py improve`
   - Track configuration changes
   - Monitor Sharpe ratio trends

4. **Extend the System**
   - Add custom analyzers for your domain
   - Implement Bayesian optimization
   - Build RL-based learners
   - Create ensemble strategies

## Resources

- **Code**: `/autopredict/learning/`
- **Scripts**: `/scripts/learn_and_improve.py`
- **Examples**: See test files in `/tests/`
- **Configs**: `/configs/` and `/strategy_configs/`

## Summary

The self-improvement loop enables AutoPredict to:
- ✅ Log all trading decisions with full context
- ✅ Analyze performance across multiple dimensions
- ✅ Identify systematic failure patterns
- ✅ Generate actionable recommendations
- ✅ Tune parameters via grid search
- ✅ Validate improvements on holdout data
- ✅ Automatically save better configurations

**Key principle**: Start with simple grid search. The infrastructure is designed to easily plug in more advanced learners (Bayesian optimization, RL, LLMs) later.
