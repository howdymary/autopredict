# AutoPredict Learning Module

The learning module provides tools for continuous self-improvement through automated performance analysis and parameter tuning.

## Quick Start

```python
from pathlib import Path
from autopredict.learning.logger import TradeLog, TradeLogger
from autopredict.learning.analyzer import PerformanceAnalyzer
from autopredict.learning.tuner import GridSearchTuner, ParameterGrid

# 1. Log trades
logger = TradeLogger(Path("state/trades"))
logger.append(trade_log)

# 2. Analyze performance
logs = logger.load_recent(days=30)
analyzer = PerformanceAnalyzer(logs)
report = analyzer.generate_report()

print(f"Win rate: {report.win_rate:.2%}")
print(f"Sharpe: {report.sharpe_ratio:.3f}")

# 3. Tune parameters
param_grid = ParameterGrid({
    "min_edge": [0.03, 0.05, 0.08],
    "aggressive_edge": [0.10, 0.12, 0.15],
})

tuner = GridSearchTuner(param_grid, backtest_fn)
best_params, best_result = tuner.tune()
```

## CLI Commands

```bash
# Analyze recent performance
python -m autopredict.cli learn analyze --log-dir state/trades --days 7

# Tune parameters
python scripts/learn_and_improve.py tune --config configs/strategy.json

# Full improvement loop
python scripts/learn_and_improve.py improve \
  --config configs/strategy.json \
  --auto-save
```

## Module Structure

- **logger.py**: Structured trade logging (JSONL format)
- **analyzer.py**: Performance analysis and failure detection
- **tuner.py**: Grid search parameter optimization

## Key Features

- **Structured Logging**: Complete decision context in JSONL format
- **Multi-Dimensional Analysis**: By market, category, feature
- **Failure Regime Detection**: Automatic identification of systematic losses
- **Actionable Recommendations**: Data-driven parameter suggestions
- **Grid Search Tuning**: Automated parameter optimization
- **Extensible Design**: Easy to add custom analyzers and tuners

## Documentation

See [SELF_IMPROVEMENT.md](/SELF_IMPROVEMENT.md) for complete documentation.

## Example

Run the demo:
```bash
python examples/learning_demo.py
```

## Tests

```bash
pytest tests/test_learning.py -v
```
