# AutoPredict Quick Start

This walkthrough gets you from clone to your first strategy iteration.

## 1. Install

```bash
git clone https://github.com/howdymary/autopredict.git
cd autopredict
python -m pip install -e .
```

Editable install is recommended so package imports and CLI behavior match what you see in the repo.

## 2. Run the baseline backtest

```bash
python -m autopredict.cli backtest
```

This command uses:

- `strategy_configs/baseline.json`
- `datasets/sample_markets.json`
- `strategy.md`

It simulates the sample markets, prints the metrics, and saves a timestamped `metrics.json` under `state/backtests/`.

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

## 3. Read the key fields

Use these as your first pass:

- `sharpe`: quality of returns relative to volatility
- `brier_score`: quality of forecast calibration
- `avg_slippage_bps`: execution cost
- `fill_rate`: how much of requested size actually filled
- `agent_feedback`: the framework’s best guess at the next improvement target

## 4. Inspect the latest run

```bash
python -m autopredict.cli score-latest
```

This loads the newest `metrics.json` from `state/backtests/`.

## 5. Make one change

Open `strategy_configs/baseline.json` and change one parameter only.

Example:

```json
{
  "name": "baseline_execution_aware",
  "min_edge": 0.08,
  "aggressive_edge": 0.16,
  "max_risk_fraction": 0.015
}
```

Then rerun:

```bash
python -m autopredict.cli backtest --config strategy_configs/baseline.json
```

That is the core loop:

1. change one thing
2. rerun
3. compare metrics
4. keep or revert

## 6. Pick the next guide

- Forecast quality looks weak: [docs/fair_prob_guidelines.md](docs/fair_prob_guidelines.md)
- Execution looks weak: [docs/BACKTESTING.md](docs/BACKTESTING.md)
- Sizing or stability looks weak: [docs/METRICS.md](docs/METRICS.md)
- You want strategy ideas: [docs/STRATEGIES.md](docs/STRATEGIES.md)
- You want the system overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Something broke: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Smoke checks

```bash
pytest -q
python -m autopredict.cli backtest
python -m autopredict.cli score-latest
```

If you want the broader map of the project after this, open [docs/README.md](docs/README.md).
