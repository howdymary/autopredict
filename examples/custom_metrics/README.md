# Custom Metrics Example

This example demonstrates how to add custom performance metrics to AutoPredict.

## Profit Factor Metric

Profit Factor = Gross Profit / Gross Loss

This metric shows how much you make on winning trades vs lose on losing trades.
- Profit Factor > 1.0: Winners bigger than losers (good)
- Profit Factor < 1.0: Losers bigger than winners (bad)
- Profit Factor = 1.5: You make $1.50 for every $1.00 you lose

## Other Custom Metrics

This example also adds:
- **Consecutive Wins/Losses**: Longest winning and losing streaks
- **Average Win/Loss Size**: How big are typical wins vs losses
- **Win/Loss Ratio**: Ratio of average win to average loss

## Running the Example

```bash
cd "/Users/howdymary/Documents/New project/autopredict"
python3 examples/custom_metrics/run_with_custom_metrics.py
```

## Integration Approach

Two methods to add custom metrics:

### Method 1: Extend evaluate_all() (Recommended)

Create a wrapper function that calls the original and adds your metrics:

```python
from autopredict.market_env import evaluate_all as original_evaluate_all

def evaluate_all_extended(forecasts, trades):
    metrics = original_evaluate_all(forecasts, trades)
    metrics.update(calculate_custom_metrics(trades))
    return metrics
```

### Method 2: Post-Process Metrics

Calculate custom metrics after the backtest:

```python
metrics = run_backtest(...)
custom_metrics = calculate_custom_metrics(trades)
metrics.update(custom_metrics)
```

This example uses Method 1 for cleaner integration.
