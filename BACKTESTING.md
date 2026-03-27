# Backtesting Guide

Comprehensive guide to running, interpreting, and optimizing backtests in AutoPredict.

## Table of Contents

1. [Overview](#overview)
2. [Running Backtests](#running-backtests)
3. [Interpreting Results](#interpreting-results)
4. [Avoiding Common Pitfalls](#avoiding-common-pitfalls)
5. [Walk-Forward Testing](#walk-forward-testing)
6. [Advanced Techniques](#advanced-techniques)

## Overview

Backtesting is the process of simulating your trading strategy on historical market data to evaluate its performance **before** risking real capital. AutoPredict provides a rigorous backtesting framework that:

- Simulates realistic order execution (market impact, slippage, partial fills)
- Tracks comprehensive metrics (epistemic, financial, execution)
- Prevents look-ahead bias (decisions use only past information)
- Enables rapid iteration (backtest completes in seconds)

### What Backtesting Can Tell You

**Backtesting answers**:
- Would this strategy have been profitable?
- What is the expected risk-adjusted return (Sharpe ratio)?
- How accurate are my probability forecasts (Brier score)?
- What are typical execution costs (slippage, fill rate)?
- What is the worst-case drawdown?

**Backtesting does NOT guarantee**:
- Future performance (markets change)
- Live trading results (execution differs)
- Profitability on different data

### Backtesting Philosophy

In AutoPredict, backtesting is:

1. **Fast**: Run in seconds, iterate quickly
2. **Realistic**: Simulates order book execution, not mid-price fills
3. **Comprehensive**: Evaluates 3 dimensions (epistemic, financial, execution)
4. **Reproducible**: Same config + data = same results

## Running Backtests

### Basic Backtest

Run with default settings:

```bash
python -m autopredict.cli backtest
```

This uses:
- Config: `strategy_configs/baseline.json`
- Dataset: `datasets/sample_markets.json`
- Bankroll: `1000.0` (from `config.json`)

### Custom Config

Test a specific strategy:

```bash
python -m autopredict.cli backtest --config strategy_configs/aggressive.json
```

### Custom Dataset

Test on different markets:

```bash
python -m autopredict.cli backtest --dataset datasets/test_markets.json
```

### Both Custom Config and Dataset

```bash
python -m autopredict.cli backtest \
  --config strategy_configs/mispriced_v2.json \
  --dataset datasets/large_sample.json
```

### Programmatic Backtest

For advanced use cases, run programmatically:

```python
from autopredict.cli import run_backtest
from autopredict.agent import AgentConfig, AutoPredictAgent

# Load config
config = AgentConfig(
    min_edge=0.08,
    aggressive_edge=0.15,
    max_risk_fraction=0.015
)

# Run backtest
metrics = run_backtest(
    config=config,
    dataset_path="datasets/sample_markets.json",
    starting_bankroll=1000.0
)

print(f"Sharpe: {metrics['sharpe']:.2f}")
print(f"Brier: {metrics['brier_score']:.3f}")
```

## Interpreting Results

### Output Format

Backtests output JSON with all metrics:

```json
{
  "total_pnl": 45.23,
  "sharpe": 2.44,
  "max_drawdown": 18.5,
  "win_rate": 0.627,
  "num_trades": 59,
  "brier_score": 0.189,
  "avg_slippage_bps": 55.2,
  "fill_rate": 0.78,
  "market_impact_bps": 42.1,
  "spread_capture_bps": 8.3,
  "implementation_shortfall_bps": 63.5,
  "adverse_selection_rate": 0.18,
  "calibration_by_bucket": {...},
  "agent_feedback": {
    "dominant_weakness": "execution_quality",
    "weakness_score": 0.65,
    "hypothesis": "Slippage is high - consider more limit orders"
  }
}
```

### Metric Interpretation

#### Financial Metrics

**Total PnL** (`total_pnl`)
- Sum of all realized gains/losses
- Positive = profitable, negative = losing
- **Caveat**: Raw PnL doesn't account for risk

**Sharpe Ratio** (`sharpe`)
- Risk-adjusted returns: `mean(returns) / std(returns) * sqrt(N)`
- **> 2.0**: Excellent
- **1.0-2.0**: Good
- **0.5-1.0**: Acceptable
- **< 0.5**: Poor (high risk for returns)
- **Caveat**: Sample size matters (need 30+ trades for reliability)

**Max Drawdown** (`max_drawdown`)
- Largest peak-to-trough decline
- Measures worst-case scenario
- **< 20%**: Excellent
- **20-35%**: Good
- **35-50%**: Acceptable
- **> 50%**: High risk (review position sizing)

**Win Rate** (`win_rate`)
- Fraction of trades with positive PnL
- **> 60%**: Excellent
- **50-60%**: Good
- **45-50%**: Acceptable (can still be profitable if winners > losers)
- **< 45%**: Review strategy logic

**Number of Trades** (`num_trades`)
- More trades = more reliable statistics
- **< 10**: Results highly uncertain
- **10-30**: Moderate confidence
- **30-100**: Good sample size
- **> 100**: High confidence

#### Epistemic Metrics

**Brier Score** (`brier_score`)
- Forecast accuracy: `mean((forecast - outcome)^2)`
- **< 0.15**: Excellent (expert-level)
- **0.15-0.20**: Good
- **0.20-0.25**: Acceptable
- **> 0.25**: Poor (review probability estimates)

**Calibration by Bucket** (`calibration_by_bucket`)
- Shows if forecasts are well-calibrated
- Example: Markets you predicted at 60% should resolve YES ~60% of the time

```json
{
  "0.0-0.1": {"forecast": 0.05, "actual": 0.0, "count": 2},
  "0.5-0.6": {"forecast": 0.55, "actual": 0.60, "count": 10},
  "0.9-1.0": {"forecast": 0.95, "actual": 0.89, "count": 9}
}
```

**Interpretation**:
- `forecast` close to `actual` = well-calibrated
- `forecast > actual` = overconfident
- `forecast < actual` = underconfident

#### Execution Metrics

**Average Slippage** (`avg_slippage_bps`)
- Cost vs mid price in basis points (1 bp = 0.01%)
- **< 10 bps**: Excellent
- **10-30 bps**: Good
- **30-60 bps**: Acceptable
- **> 60 bps**: High cost (review order type selection)

**Fill Rate** (`fill_rate`)
- Fraction of requested size that filled
- **0.8-1.0**: Excellent (mostly market orders)
- **0.5-0.8**: Good (mix of market and limit)
- **0.3-0.5**: Acceptable (mostly limit orders)
- **< 0.3**: Low (orders too passive or markets too thin)

**Market Impact** (`market_impact_bps`)
- How much mid price moved after your trade
- **< 20 bps**: Excellent (small footprint)
- **20-50 bps**: Good
- **50-100 bps**: Acceptable
- **> 100 bps**: High impact (reduce `max_depth_fraction`)

**Spread Capture** (`spread_capture_bps`)
- Value captured from limit orders
- **> 20 bps**: Excellent (profitable passive orders)
- **10-20 bps**: Good
- **0-10 bps**: Acceptable
- **< 0**: Poor (limit orders filling at bad prices)

**Implementation Shortfall** (`implementation_shortfall_bps`)
- Total execution cost (slippage + fees + impact)
- **< 30 bps**: Excellent
- **30-60 bps**: Good
- **60-100 bps**: Acceptable
- **> 100 bps**: High cost (review execution strategy)

**Adverse Selection Rate** (`adverse_selection_rate`)
- Fraction of passive orders that moved against you after fill
- **< 10%**: Excellent (good timing)
- **10-20%**: Good
- **20-30%**: Acceptable
- **> 30%**: Poor (limit orders filling on wrong side)

### Agent Feedback

The `agent_feedback` field identifies the dominant weakness:

```json
{
  "dominant_weakness": "execution_quality",
  "weakness_score": 0.65,
  "hypothesis": "Slippage is high - consider more limit orders"
}
```

**Weakness Types**:
- `execution_quality`: High slippage or low fill rate
- `limit_fill_quality`: Passive orders not filling or adversely selected
- `calibration`: Forecasts poorly calibrated
- `risk`: Position sizing too large (high drawdown)
- `selection`: Trading low-quality edges

**How to use**: Focus on the dominant weakness first. Fix it, re-run backtest, and see if overall performance improves.

## Avoiding Common Pitfalls

### Pitfall 1: Overfitting to Sample Data

**Symptom**: Great performance on `sample_markets.json`, poor on new data

**Causes**:
- Tuning parameters to fit specific markets
- Cherry-picking markets that worked
- Too many parameters relative to sample size

**Solutions**:
1. Test on multiple datasets
2. Use walk-forward testing (see below)
3. Keep parameter count low (< 10)
4. Avoid tuning to specific market_ids

```bash
# Generate new test set
python scripts/generate_dataset.py --num-markets 100 --output datasets/test_set.json

# Test on both
python -m autopredict.cli backtest --dataset datasets/sample_markets.json
python -m autopredict.cli backtest --dataset datasets/test_set.json

# Performance should be similar
```

### Pitfall 2: Look-Ahead Bias

**Symptom**: Backtest uses information not available at decision time

**Examples**:
- Using `outcome` field to make decisions (leaked future info)
- Using market_prob from future snapshots
- Calculating statistics across entire dataset before trading

**Solutions**:
- AutoPredict prevents this by design (agent receives one snapshot at a time)
- Never access `outcome` in `evaluate_market()`
- Don't pre-compute statistics on full dataset

**Correct**:
```python
def evaluate_market(self, market, bankroll):
    edge = market.fair_prob - market.market_prob
    # Use only current market state
```

**Incorrect (NEVER DO THIS)**:
```python
def evaluate_market(self, market, bankroll):
    # WRONG: outcome not known at decision time!
    if market.outcome == 1:
        return ProposedOrder(...)
```

### Pitfall 3: Survivorship Bias

**Symptom**: Dataset only includes markets that resolved (no cancelled markets)

**Impact**: Overestimates performance

**Solutions**:
- Include cancelled markets in test data
- Add edge cases (no liquidity, extreme spreads)
- Test on real historical data if available

### Pitfall 4: Ignoring Transaction Costs

**Symptom**: Strategy looks profitable but loses money after slippage/fees

**Impact**: Overestimates net returns

**Solutions**:
- Monitor `avg_slippage_bps` and `implementation_shortfall_bps`
- Ensure `total_pnl` is positive AFTER execution costs
- Use realistic execution simulation (AutoPredict does this)

### Pitfall 5: Insufficient Sample Size

**Symptom**: Sharpe ratio 5.0 with only 8 trades

**Impact**: Results are noise, not signal

**Solutions**:
- Aim for 30+ trades minimum
- Test on larger datasets
- Lower `min_edge` threshold to capture more opportunities
- Use confidence intervals for metrics

```python
import statistics

# Example: Calculate confidence interval for Sharpe
pnls = [trade.pnl for trade in trades]
mean_pnl = statistics.mean(pnls)
std_pnl = statistics.stdev(pnls)
n = len(pnls)

# 95% confidence interval
margin = 1.96 * std_pnl / (n ** 0.5)
ci_low = mean_pnl - margin
ci_high = mean_pnl + margin

print(f"Mean PnL: {mean_pnl:.2f} [{ci_low:.2f}, {ci_high:.2f}]")
```

### Pitfall 6: Parameter Tuning Without Validation

**Symptom**: Adjusted 20 parameters to maximize Sharpe on sample data

**Impact**: Overfit model that won't generalize

**Solutions**:
- Use train/validation/test split
- Limit parameter changes per iteration
- Validate on out-of-sample data
- Use walk-forward testing (below)

## Walk-Forward Testing

Walk-forward testing prevents overfitting by simulating realistic strategy development.

### How It Works

1. Split data into multiple time periods
2. Train on period 1, test on period 2
3. Train on period 1-2, test on period 3
4. Continue rolling forward

This simulates real-world scenario: develop strategy on past data, deploy on future data.

### Implementation

**Step 1: Split Dataset**

```python
import json

# Load full dataset
with open("datasets/full_markets.json") as f:
    markets = json.load(f)

# Split into 5 periods (20% each)
n = len(markets)
period_size = n // 5

periods = [
    markets[i*period_size:(i+1)*period_size]
    for i in range(5)
]

# Save periods
for i, period in enumerate(periods):
    with open(f"datasets/period_{i+1}.json", "w") as f:
        json.dump(period, f)
```

**Step 2: Walk-Forward Loop**

```bash
# Train on period 1, test on period 2
python -m autopredict.cli backtest --dataset datasets/period_1.json
# Tune strategy based on results
python -m autopredict.cli backtest --dataset datasets/period_2.json
# Record performance

# Train on period 1-2, test on period 3
cat datasets/period_1.json datasets/period_2.json > datasets/period_1_2.json
python -m autopredict.cli backtest --dataset datasets/period_1_2.json
# Tune strategy
python -m autopredict.cli backtest --dataset datasets/period_3.json
# Record performance

# Continue...
```

**Step 3: Aggregate Results**

```python
# Collect out-of-sample results
oos_sharpes = [1.2, 1.5, 1.8, 1.3, 1.6]  # From periods 2-5

# Average performance
avg_sharpe = sum(oos_sharpes) / len(oos_sharpes)
print(f"Walk-forward Sharpe: {avg_sharpe:.2f}")

# Compare to in-sample
in_sample_sharpe = 2.8  # Optimized on full dataset
print(f"Degradation: {(in_sample_sharpe - avg_sharpe) / in_sample_sharpe * 100:.1f}%")
```

**Interpretation**:
- **< 20% degradation**: Good (strategy generalizes well)
- **20-40% degradation**: Acceptable (some overfitting)
- **> 40% degradation**: Poor (overfitted, won't work live)

### Automated Walk-Forward Script

Create `scripts/walk_forward.py`:

```python
"""Walk-forward testing script."""
import json
import subprocess
from pathlib import Path

def walk_forward_test(dataset_path, num_folds=5):
    """Run walk-forward test on dataset."""

    # Load data
    with open(dataset_path) as f:
        markets = json.load(f)

    # Split into folds
    fold_size = len(markets) // num_folds
    results = []

    for test_fold in range(1, num_folds):
        # Training set: folds 0 to test_fold-1
        train_markets = markets[:test_fold * fold_size]

        # Test set: test_fold
        test_markets = markets[test_fold * fold_size:(test_fold + 1) * fold_size]

        # Save splits
        train_path = f"datasets/train_fold_{test_fold}.json"
        test_path = f"datasets/test_fold_{test_fold}.json"

        with open(train_path, "w") as f:
            json.dump(train_markets, f)
        with open(test_path, "w") as f:
            json.dump(test_markets, f)

        # Run backtest on test set
        result = subprocess.run(
            ["python", "-m", "autopredict.cli", "backtest", "--dataset", test_path],
            capture_output=True,
            text=True
        )

        # Parse metrics
        metrics = json.loads(result.stdout)
        results.append({
            "fold": test_fold,
            "sharpe": metrics["sharpe"],
            "brier": metrics["brier_score"],
            "num_trades": metrics["num_trades"]
        })

        print(f"Fold {test_fold}: Sharpe={metrics['sharpe']:.2f}, Brier={metrics['brier_score']:.3f}")

    # Summary
    avg_sharpe = sum(r["sharpe"] for r in results) / len(results)
    avg_brier = sum(r["brier"] for r in results) / len(results)

    print(f"\nWalk-Forward Results:")
    print(f"  Average Sharpe: {avg_sharpe:.2f}")
    print(f"  Average Brier: {avg_brier:.3f}")

    return results

if __name__ == "__main__":
    walk_forward_test("datasets/full_markets.json")
```

**Run it**:
```bash
python scripts/walk_forward.py
```

## Advanced Techniques

### Monte Carlo Simulation

Assess variability in results:

```python
import random
import statistics

def monte_carlo_backtest(markets, num_simulations=100):
    """Run backtest on random subsamples."""

    sharpes = []

    for _ in range(num_simulations):
        # Random subsample (80% of data)
        sample = random.sample(markets, int(len(markets) * 0.8))

        # Run backtest
        metrics = run_backtest(sample)
        sharpes.append(metrics["sharpe"])

    # Statistics
    mean_sharpe = statistics.mean(sharpes)
    std_sharpe = statistics.stdev(sharpes)
    ci_95 = 1.96 * std_sharpe

    print(f"Mean Sharpe: {mean_sharpe:.2f} ± {ci_95:.2f}")
    print(f"Range: [{min(sharpes):.2f}, {max(sharpes):.2f}]")

    return sharpes
```

### Sensitivity Analysis

Test robustness to parameter changes:

```python
def sensitivity_analysis(base_config):
    """Test sensitivity to parameter changes."""

    parameters = ["min_edge", "aggressive_edge", "max_risk_fraction"]
    ranges = {
        "min_edge": [0.03, 0.05, 0.07, 0.10],
        "aggressive_edge": [0.10, 0.12, 0.15, 0.20],
        "max_risk_fraction": [0.01, 0.015, 0.02, 0.03]
    }

    results = {}

    for param in parameters:
        param_results = []

        for value in ranges[param]:
            # Create config with this parameter value
            config = base_config.copy()
            config[param] = value

            # Run backtest
            metrics = run_backtest(config)

            param_results.append({
                "value": value,
                "sharpe": metrics["sharpe"],
                "brier": metrics["brier_score"]
            })

        results[param] = param_results

        # Print
        print(f"\n{param} sensitivity:")
        for r in param_results:
            print(f"  {r['value']}: Sharpe={r['sharpe']:.2f}")

    return results
```

### Bootstrap Confidence Intervals

Estimate uncertainty in metrics:

```python
import random

def bootstrap_sharpe(trades, num_bootstrap=1000):
    """Bootstrap confidence interval for Sharpe ratio."""

    pnls = [trade.pnl for trade in trades]
    n = len(pnls)

    sharpes = []

    for _ in range(num_bootstrap):
        # Resample with replacement
        sample = [random.choice(pnls) for _ in range(n)]

        # Calculate Sharpe
        mean_pnl = sum(sample) / n
        std_pnl = statistics.stdev(sample)
        sharpe = mean_pnl / std_pnl * (n ** 0.5)

        sharpes.append(sharpe)

    # 95% confidence interval
    sharpes.sort()
    ci_low = sharpes[int(0.025 * num_bootstrap)]
    ci_high = sharpes[int(0.975 * num_bootstrap)]

    print(f"Sharpe 95% CI: [{ci_low:.2f}, {ci_high:.2f}]")

    return (ci_low, ci_high)
```

## Backtest Checklist

Before trusting backtest results:

- [ ] Sample size: At least 30 trades
- [ ] Out-of-sample testing: Tested on data not used for tuning
- [ ] Walk-forward: Validated using walk-forward methodology
- [ ] Execution costs: Slippage and impact included in PnL
- [ ] No look-ahead bias: Only past data used for decisions
- [ ] Multiple datasets: Tested on at least 2 different datasets
- [ ] Sensitivity: Results stable across parameter variations
- [ ] Drawdown: Max drawdown acceptable (<50%)
- [ ] Sharpe ratio: >1.0 on out-of-sample data
- [ ] Calibration: Brier score <0.25

## Next Steps

- Read **DEPLOYMENT.md** to prepare for paper trading
- Read **LEARNING.md** to understand how to improve strategies iteratively
- Read **STRATEGIES.md** for strategy development patterns
- Explore **notebooks/03_performance_analysis.ipynb** for deep-dive analysis

## Further Reading

- [Advances in Financial Machine Learning](https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086) by Marcos López de Prado
- [Evidence-Based Technical Analysis](http://www.evidencebasedta.com/) by David Aronson
- [The Evaluation and Optimization of Trading Strategies](https://www.wiley.com/en-us/The+Evaluation+and+Optimization+of+Trading+Strategies%2C+2nd+Edition-p-9780470128015) by Robert Pardo
