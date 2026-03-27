# AutoPredict

A minimal framework for self-improving prediction market agents. Split into a fixed evaluation environment and a mutable agent strategy that evolves through iterative experimentation.

## Structure

The codebase is deliberately minimal:

- `market_env.py` - Fixed prediction market simulator with order book execution and metrics
- `agent.py` - Mutable trading strategy that agents can modify
- `run_experiment.py` - Backtest harness
- `cli.py` - Command interface

Total core: ~1500 lines.

## How it works

The framework separates what stays fixed (market simulation, metrics) from what evolves (trading logic). Agents trade on prediction market snapshots, get scored on three dimensions (forecast quality, financial performance, execution efficiency), and propose modifications to improve.

```
market snapshot → agent decision → execution → metrics → iterate
```

Evaluation combines:
- Epistemic metrics: Brier score, calibration curves
- Financial metrics: Sharpe ratio, PnL, drawdown
- Execution metrics: slippage, fill rate, market impact

## Running

```bash
# backtest on sample data
python -m autopredict.cli backtest

# view results
python -m autopredict.cli score-latest
```

Backtests process market snapshots from `datasets/sample_markets.json`. Each snapshot includes fair probability estimate, market price, order book state, and eventual outcome.

## Configuration

Agent behavior is controlled by `strategy_configs/baseline.json`:

```json
{
  "min_edge": 0.05,              // minimum edge to trade
  "aggressive_edge": 0.14,       // threshold for market orders
  "max_risk_fraction": 0.02,     // position size cap
  "min_book_liquidity": 60.0,    // minimum depth required
  "max_spread_pct": 0.06         // maximum acceptable spread
}
```

Changes to config or `agent.py` can be tested immediately via backtest.

## Metrics

Output includes:

**Financial:**
- `total_pnl` - realized profit/loss
- `sharpe` - risk-adjusted return
- `max_drawdown` - largest peak-to-trough decline

**Epistemic:**
- `brier_score` - forecast accuracy (lower is better)
- `calibration_by_bucket` - probability alignment

**Execution:**
- `avg_slippage_bps` - execution cost vs mid price
- `fill_rate` - percentage of orders filled
- `market_impact_bps` - price movement caused by trades

## Architecture

The split between fixed and mutable is strict:

**Fixed (`market_env.py`):**
- OrderBook class with depth-aware execution
- ExecutionEngine simulating market and limit orders
- Metrics computation (epistemic, financial, execution)

Never modified during experiments. Guarantees fair comparison.

**Mutable (`agent.py`):**
- ExecutionStrategy (order type selection, sizing)
- AutoPredictAgent (market evaluation, filtering)
- AgentConfig (tunable parameters)

This is the surface area for improvement.

## Dataset format

Markets are JSON arrays:

```json
[
  {
    "market_id": "us-election-2028",
    "market_prob": 0.45,
    "fair_prob": 0.53,
    "outcome": 1,
    "time_to_expiry_hours": 168.0,
    "order_book": {
      "bids": [[0.44, 100.0], [0.43, 150.0]],
      "asks": [[0.46, 100.0], [0.47, 150.0]]
    }
  }
]
```

The `scripts/generate_dataset.py` tool can create synthetic datasets with realistic characteristics.

## Testing

```bash
python -m pytest tests/ -v
```

Test suite covers order book operations, execution simulation, agent logic, and validation. 65 tests, 80%+ coverage.

## Extension points

To modify strategy:
1. Edit `agent.py` execution logic or `strategy_configs/baseline.json`
2. Run backtest
3. Compare metrics
4. Keep or revert

To add metrics:
- Extend `market_env.evaluate_all()`
- Metrics automatically appear in output

To use different markets:
- Provide dataset via `--dataset path/to/markets.json`

## Dependencies

Python 3.10+. No external packages required for core functionality (uses stdlib only).

Optional:
- `pytest` for running tests
- `anthropic` for meta-agent autonomous improvement

## Files

Core implementation:
- `agent.py` (400 lines)
- `market_env.py` (700 lines)
- `run_experiment.py` (150 lines)
- `cli.py` (100 lines)

Infrastructure:
- `scripts/generate_dataset.py` - synthetic market generation
- `validation/validator.py` - dataset validation
- `tests/` - test suite

Documentation:
- `ARCHITECTURE.md` - technical details
- `QUICKSTART.md` - tutorial
- `METRICS.md` - metric reference

## Design philosophy

Keep the evaluation layer frozen. Keep the strategy layer small and mutable. Make changes testable in seconds. Track what works via git commits.

The framework is deliberately not batteries-included. It provides structure for experimentation, not a complete trading system.

## Baseline results

6-market sample:
- Sharpe: 7.67 (high due to small sample)
- Brier: 0.255 (mediocre calibration)
- Slippage: 55 bps (acceptable)
- 4 trades executed

100-market test:
- Sharpe: 2.44 (more reliable with larger sample)
- Brier: 0.189 (good calibration)
- Slippage: 55 bps
- 59 trades executed

Performance varies by dataset quality and fair probability estimates.

## Related work

Inspired by [autoresearch](https://github.com/karpathy/autoresearch) - same pattern of fixed environment + mutable model + iterative improvement, applied to trading agents instead of neural networks.
