# AutoPredict

AutoPredict is a framework for prediction market trading agents. It connects to live Polymarket data, lets you supply your own probability estimates, and evaluates trade opportunities with execution-aware metrics.

## Quick start

```bash
git clone https://github.com/howdymary/autopredict.git
cd autopredict
python -m pip install -e .

# Scan live markets
python predict.py

# Find structural edges in multi-outcome events
python predict.py --events

# Test your own prediction on a specific market
python predict.py --fair 0.60 <condition_id>
```

See [QUICKSTART.md](QUICKSTART.md) for a full walkthrough.

## What it does

- **Live market scanning**: Fetches active markets and real order books from Polymarket (no auth needed for reads)
- **Event-level analysis**: Finds multi-outcome events where sibling prices don't sum to 1.0 (structural mispricing)
- **Execution-aware agent**: Given your `fair_prob`, evaluates edge, spread, liquidity, and book depth before recommending a trade
- **Configurable strategy**: All agent parameters are JSON-tunable (edge thresholds, risk limits, sizing)
- **Backtesting engine**: Test strategy changes against market data with slippage and fill rate simulation

## Core pieces

- [predict.py](predict.py): Live market scanner and agent runner — the main entry point
- [agent.py](agent.py): The mutable trading agent
- [market_env.py](market_env.py): Order book simulation and execution metrics
- [autopredict/markets/polymarket.py](autopredict/markets/polymarket.py): Polymarket API adapter (Gamma + CLOB)
- [strategy_configs](strategy_configs): Tunable strategy parameters
- [run_experiment.py](run_experiment.py): Backtest loop for offline evaluation

## What it measures

Three groups of metrics:

- **Epistemic**: `brier_score`, `calibration_by_bucket`
- **Financial**: `total_pnl`, `sharpe`, `max_drawdown`, `win_rate`
- **Execution**: `avg_slippage_bps`, `fill_rate`, `market_impact_bps`, `implementation_shortfall_bps`

## Documentation

- [QUICKSTART.md](QUICKSTART.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/STRATEGIES.md](docs/STRATEGIES.md)
- [docs/BACKTESTING.md](docs/BACKTESTING.md)
- [docs/METRICS.md](docs/METRICS.md)
- [docs/fair_prob_guidelines.md](docs/fair_prob_guidelines.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Design philosophy

The agent does NOT generate predictions. It optimizes execution given your forecast. If you think a market is at 54% and should be at 60%, the agent decides whether to trade, how much, and what order type — based on spread, depth, and your risk limits.

The forecasting is your job. The execution is the agent's job.

## License

MIT. See [LICENSE](LICENSE).
