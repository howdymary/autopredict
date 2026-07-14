# AutoPredict Quick Start

This walkthrough gets you from clone to a production-safe first run. AutoPredict does not ship sample market datasets; bring real resolved data for backtests, or use the live scanner for read-only market inspection.

## 1. Install

```bash
git clone https://github.com/howdymary/autopredict.git
cd autopredict
python -m pip install -e .
```

## 2. Inspect Live Markets

```bash
python -m autopredict.cli scan-live --limit 20 --top 5
```

For event sibling price sums:

```bash
python -m autopredict.cli scan-live --events --limit 20 --top 5
```

This is read-only. It reports observed public Polymarket data and never creates forecasts, recommendations, or orders.

Run the local safety audit before wiring live execution:

```bash
python -m autopredict.cli safety-audit --config /path/to/your/live_trading.yaml
```

## 3. Validate Point-In-Time Data

Prepare a v1 JSON manifest and canonical JSONL records from real historical data,
then validate their schema, timestamps, book ordering, resolution joins, and hashes:

```bash
python -m autopredict.cli validate --dataset /path/to/dataset/manifest.json
```

See [docs/DATASETS.md](docs/DATASETS.md) for the exact contract.

## 4. Evaluate The Market Baseline

```bash
python -m autopredict.cli evaluate \
  --dataset /path/to/dataset/manifest.json \
  --provider market-baseline \
  --output evaluation-report.json
```

Useful first-pass fields:

- `candidate` and `baseline`: proper scoring and calibration reports
- `skill`: paired Brier and log-score improvement over the market
- `rows`: point-in-time forecast rows with independent event IDs
- `dataset` and `provider`: hashes and versioned provenance

## 5. Run Tests

```bash
python -m pip install -e ".[dev]"
pytest -q
```

Next guides:

- [docs/BACKTESTING.md](docs/BACKTESTING.md)
- [docs/DATASETS.md](docs/DATASETS.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/LEARNING.md](docs/LEARNING.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
