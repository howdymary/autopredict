# AutoPredict

AutoPredict is a framework for iteratively improving prediction market trading agents.

It keeps the market simulator fixed, the trading logic mutable, and the iteration loop tight:

1. run a backtest
2. inspect forecast, PnL, and execution metrics
3. change one config or strategy decision
4. rerun and compare

## What makes it useful

- Fixed evaluation environment: order book simulation, execution quality, and scoring stay stable across experiments.
- Mutable strategy surface: you can evolve the agent through `agent.py` and `strategy_configs/*.json`.
- Execution-aware metrics: the framework treats slippage, fill rate, and market impact as first-class, not afterthoughts.
- Lightweight local workflow: no runtime dependencies beyond the Python standard library.

## Quick start

```bash
git clone https://github.com/howdymary/autopredict.git
cd autopredict
python -m pip install -e .

python -m autopredict.cli backtest
python -m autopredict.cli score-latest
```

Example output:

```json
{
  "total_pnl": 23.848357929641246,
  "sharpe": 7.667475056377162,
  "brier_score": 0.25475000000000003,
  "fill_rate": 0.4420699362191731,
  "num_trades": 4.0,
  "agent_feedback": {
    "weakness": "calibration",
    "hypothesis": "Forecasts are too confident relative to realized outcomes."
  }
}
```

To run your first full iteration, start with [QUICKSTART.md](QUICKSTART.md).

## Core pieces

- [market_env.py](market_env.py): order books, execution simulation, and evaluation metrics
- [agent.py](agent.py): the mutable baseline agent
- [run_experiment.py](run_experiment.py): the backtest loop
- [autopredict/cli.py](autopredict/cli.py): packaged command-line entrypoint
- [strategy_configs](strategy_configs): tunable strategy parameters
- [datasets](datasets): sample market snapshots
- [tests](tests): automated regression coverage

## What it measures

AutoPredict reports three groups of metrics:

- Epistemic: `brier_score`, `calibration_by_bucket`
- Financial: `total_pnl`, `sharpe`, `max_drawdown`, `win_rate`
- Execution: `avg_slippage_bps`, `fill_rate`, `market_impact_bps`, `implementation_shortfall_bps`

The framework also returns `agent_feedback`, a short diagnosis of the current bottleneck:

- `execution_quality`
- `limit_fill_quality`
- `calibration`
- `risk`
- `selection`

## Documentation

Start here:

- [QUICKSTART.md](QUICKSTART.md)
- [docs/README.md](docs/README.md)

Most useful guides:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/STRATEGIES.md](docs/STRATEGIES.md)
- [docs/BACKTESTING.md](docs/BACKTESTING.md)
- [docs/METRICS.md](docs/METRICS.md)
- [docs/LEARNING.md](docs/LEARNING.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/fair_prob_guidelines.md](docs/fair_prob_guidelines.md)

Historical design notes, phase summaries, and internal reports live under [docs/archive](docs/archive).

## Scope today

Good today:

- local backtesting
- strategy and config iteration
- packaged CLI from a repo checkout or installed wheel
- execution-aware metrics
- test coverage for core components

Intentionally limited today:

- live trading is disabled by default
- exchange integrations are still scaffolding
- autonomous self-editing is not part of the runtime

## License

MIT. See [LICENSE](LICENSE).
