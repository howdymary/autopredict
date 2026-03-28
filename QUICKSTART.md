# AutoPredict Quick Start

This walkthrough gets you from clone to your first strategy iteration.

## 1. Install

```bash
git clone https://github.com/howdymary/autopredict.git
cd autopredict
python -m pip install -e .
```

Editable install is recommended so package imports and CLI behavior match what you see in the repo. It also installs the small runtime dependency set, including `PyYAML` for config loading.

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
  "sharpe": 4.426818787804096,
  "brier_score": 0.25475000000000003,
  "fill_rate": 0.4420699362191731,
  "num_trades": 4.0,
  "forecast_source": "dataset_fair_prob",
  "agent_feedback": {
    "weakness": "forecast_input_quality",
    "hypothesis": "The supplied fair_prob inputs appear poorly calibrated; improve the upstream forecast source before blaming execution logic."
  }
}
```

## 3. Read the key fields

Use these as your first pass:

- `sharpe`: unannualized per-trade return quality relative to volatility
- `brier_score`: quality of the supplied forecast calibration on the legacy dataset-driven loop
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

## 7. Run the forecast-owned ratchet

The legacy backtest loop still reports `forecast_source: "dataset_fair_prob"`. If you want the agent to own forecast generation instead of inheriting that column, use the package-native ratchet:

```bash
python -m autopredict.cli learn improve --dataset datasets/sample_markets.json
```

This path converts the resolved dataset into scaffold snapshots, routes each market through question-conditioned specialist models, and then runs the walk-forward mutation and promotion loop on those agent-generated forecasts.

## Smoke checks

Install the dev extras first if you want to run the repo test suite:

```bash
python -m pip install -e ".[dev]"
pytest -q
python -m autopredict.cli backtest
python -m autopredict.cli score-latest
```

If you want the broader map of the project after this, open [docs/README.md](docs/README.md).
