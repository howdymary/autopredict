# AutoPredict Quick Start

Get your first prediction market agent running in 10 minutes.

## Prerequisites

- Python 3.9+
- Basic understanding of prediction markets (buy/sell YES/NO)
- Edge: `fair_probability - market_probability` (can be positive or negative)

## Installation

```bash
# Clone or navigate to the project
cd /path/to/autopredict

# Verify structure
ls -la
# Should show: agent.py, market_env.py, cli.py, config.json, etc.

# Optional: Create a virtual environment
python -m venv venv
source venv/bin/activate  # or 'venv\Scripts\activate' on Windows
```

No external package dependencies - AutoPredict uses only Python stdlib.

## 10-Minute Tutorial

### Step 1: Run the Baseline Backtest (2 min)

```bash
python -m autopredict.cli backtest
```

This runs a complete backtest on sample markets using the default strategy config.

**What happens**:
1. Loads `strategy_configs/baseline.json` (AgentConfig)
2. Loads `datasets/sample_markets.json` (6 sample markets)
3. Simulates trading each market snapshot
4. Calculates epistemic, financial, and execution metrics
5. Prints results to stdout

**Expected output** (JSON metrics):

```json
{
  "avg_slippage_bps": 8.5,
  "brier_score": 0.255,
  "fill_rate": 0.62,
  "max_drawdown": 15.0,
  "sharpe": 1.23,
  "total_pnl": 12.45,
  "win_rate": 0.67,
  "agent_feedback": {
    "weakness": "...",
    "hypothesis": "..."
  }
}
```

### Step 2: Understand the Output (3 min)

Key metrics to watch:

| Metric | Meaning | Good Range |
|--------|---------|------------|
| `brier_score` | Forecast accuracy | < 0.20 |
| `sharpe` | Risk-adjusted returns | > 1.0 |
| `max_drawdown` | Largest peak-to-trough loss | < 50% |
| `fill_rate` | Percent of orders that executed | 0.5-1.0 |
| `avg_slippage_bps` | Execution cost in basis points | < 20 |
| `total_pnl` | Total profit/loss | Positive is good |
| `win_rate` | Percent winning trades | > 50% |

The `agent_feedback` field identifies the dominant weakness:
- `execution_quality`: Slippage is too high
- `limit_fill_quality`: Passive orders aren't filling
- `calibration`: Forecasts too confident
- `risk`: Position sizing too large
- `selection`: Trading low-quality edges

### Step 3: Retrieve Your Latest Results (1 min)

```bash
python -m autopredict.cli score-latest
```

This loads the metrics from your most recent backtest run and prints them.

**Behind the scenes**:
- Finds the newest timestamped directory in `state/backtests/`
- Loads `metrics.json` from that run

### Step 4: Modify the Strategy Config (2 min)

Open `strategy_configs/baseline.json` and try changing a parameter:

```json
{
  "name": "experiment_tighter_edge",
  "min_edge": 0.08,  # Increased from 0.05
  "aggressive_edge": 0.15,
  "max_risk_fraction": 0.01,  # Decreased from 0.02
  ...
}
```

Run the backtest again:

```bash
python -m autopredict.cli backtest --config strategy_configs/baseline.json
```

**What changed**:
- Fewer trades (higher edge threshold)
- Smaller position sizes (lower risk fraction)
- Better Sharpe ratio (less churn) or worse (missing opportunities)

This is the core iteration loop: adjust config → backtest → measure → repeat.

### Step 5: Understand Your Sample Dataset (2 min)

Look at `datasets/sample_markets.json`:

```json
[
  {
    "market_id": "politics-2025-03",
    "market_prob": 0.58,
    "fair_prob": 0.63,
    "time_to_expiry_hours": 72.0,
    "outcome": 1,
    "order_book": {
      "bids": [[0.55, 100.0], [0.50, 50.0]],
      "asks": [[0.60, 75.0], [0.65, 25.0]]
    }
  },
  ...
]
```

**Key fields**:
- `market_prob`: Current market price (0-1, binary outcome)
- `fair_prob`: Your forecast (0-1)
- `edge = fair_prob - market_prob` (can be ± for short/long)
- `order_book`: Available liquidity at different prices
- `outcome`: Realized result (0 or 1) after market closes

The agent:
1. Compares fair_prob vs market_prob
2. If edge is large enough and liquidity is good, proposes a trade
3. Simulates execution against the order book
4. Calculates PnL based on actual outcome

## Next Steps

### To Improve Forecast Accuracy

Read `CALIBRATION_SUMMARY.md` - your fair_prob estimates have edge over market prices (+19%), but some categories need work.

### To Improve Execution Quality

Read `WORKFLOW.md` - walkthrough of the agent decision loop and where to apply improvements.

### To Understand the Full System

Read `ARCHITECTURE.md` for component diagrams, data flows, and extension points.

### To Debug a Specific Issue

Read `TROUBLESHOOTING.md` for common problems and validation checks.

### To Learn All Metrics

Read `METRICS.md` for detailed interpretation of each number.

## Common Tweaks

### Experiment 1: Be More Aggressive

```json
{
  "min_edge": 0.03,
  "aggressive_edge": 0.08,
  "max_risk_fraction": 0.03
}
```

**Result**: More trades, higher returns, higher risk.

### Experiment 2: Focus on Quality

```json
{
  "min_edge": 0.10,
  "aggressive_edge": 0.20,
  "max_risk_fraction": 0.01
}
```

**Result**: Fewer trades, higher Sharpe, lower max drawdown.

### Experiment 3: Passive Trading

```json
{
  "max_spread_pct": 0.02,
  "max_depth_fraction": 0.10
}
```

**Result**: Only limit orders, better fill pricing, lower fill rate.

### Experiment 4: Liquidity Filter

```json
{
  "min_book_liquidity": 150.0
}
```

**Result**: Only trade deep books, avoid thin markets.

## Validation

Before running live trading, validate your setup:

```bash
# Check dataset loads correctly
python3 -c "
import json
with open('datasets/sample_markets.json') as f:
    data = json.load(f)
print(f'Loaded {len(data)} markets')
print(f'Sample: {data[0][\"market_id\"]} edge={data[0][\"fair_prob\"] - data[0][\"market_prob\"]:.3f}')
"

# Check config is valid
python3 -c "
import json
with open('strategy_configs/baseline.json') as f:
    config = json.load(f)
print(f'Config: {config[\"name\"]}')
print(f'Min edge: {config[\"min_edge\"]}')
"

# Run a quick backtest
python -m autopredict.cli backtest
```

## Troubleshooting

**Q: No orders executed?**
- Check `min_edge` is reasonable (0.02-0.10)
- Check `min_book_liquidity` isn't too high
- Verify `fair_prob` in dataset is different from `market_prob`

**Q: All orders are limit orders?**
- `aggressive_edge` threshold is too high
- Edge in markets is usually 2-8%

**Q: Fill rate is very low?**
- Limit orders in thin books won't fill (expected)
- Try increasing `aggressive_edge` to use more market orders
- Check order spread isn't wider than config limits

**Q: High slippage?**
- Using too many market orders on thin books
- Try increasing `max_spread_pct` threshold
- Try decreasing `max_depth_fraction` to trade less per order

## Files Reference

### Core Logic
- `agent.py`: Decision making (when + how to trade)
- `market_env.py`: Simulation primitives (execution, metrics)
- `run_experiment.py`: Backtest loop

### Configuration
- `config.json`: Experiment harness (paths, bankroll)
- `strategy_configs/baseline.json`: Agent tuning knobs
- `strategy.md`: Human guidance for agents

### Data
- `datasets/sample_markets.json`: 6 sample markets for testing

### Documentation
- `README.md`: Overview
- `QUICKSTART.md`: This file
- `ARCHITECTURE.md`: System design + data flows
- `WORKFLOW.md`: Agent decision loop + improvement patterns
- `TROUBLESHOOTING.md`: Common issues + solutions
- `METRICS.md`: Detailed metric reference
- `CALIBRATION_SUMMARY.md`: Forecast quality analysis

## Success Criteria

You've completed the tutorial successfully if you can:

1. ✅ Run `python -m autopredict.cli backtest` and see JSON output
2. ✅ Understand what each top-level metric means
3. ✅ Modify a config parameter and see different results
4. ✅ Retrieve your latest metrics with `score-latest`
5. ✅ Identify the dominant weakness from `agent_feedback`

## Next Checkpoint

Once you're comfortable with this tutorial, read `WORKFLOW.md` to understand:
- How the agent makes decisions
- Where to find and fix the dominant weakness
- How to propose iterative improvements
- Manual vs autonomous improvement loops
