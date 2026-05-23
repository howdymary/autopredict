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

## 3. Run A Backtest

Prepare a resolved-market JSON file from real historical data, then run:

```bash
python -m autopredict.cli backtest --dataset /path/to/resolved_markets.json
```

The command prints metrics and writes the latest run under `state/backtests/`.

## 4. Inspect The Latest Run

```bash
python -m autopredict.cli score-latest
```

Useful first-pass fields:

- `brier_score`: calibration quality for the forecast source being scored
- `total_pnl`: simulated realized PnL
- `fill_rate`: how much requested size filled
- `avg_slippage_bps`: execution cost
- `agent_feedback`: the framework's diagnosis of the current bottleneck

## 5. Improve Offline

Run the forecast-owned ratchet on the same explicit dataset:

```bash
python -m autopredict.cli learn improve \
  --dataset /path/to/resolved_markets.json \
  --archive-dir state/meta_harness/archives \
  --frontier-path state/meta_harness/frontier.json
```

The archive records provenance and dataset identity. The frontier only promotes a run when it improves the selected score for the same dataset hash, split mode, and strategy kind.

## 6. Run Tests

```bash
python -m pip install -e ".[dev]"
pytest -q
```

Next guides:

- [docs/BACKTESTING.md](docs/BACKTESTING.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/LEARNING.md](docs/LEARNING.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
