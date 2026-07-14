# Backtesting

AutoPredict backtests run only on explicit resolved-market data. The package no longer ships default market snapshots, generated datasets, or hidden fallback examples.

## Canonical CLI

```bash
python -m autopredict.cli validate --dataset /path/to/dataset/manifest.json
python -m autopredict.cli evaluate \
  --dataset /path/to/dataset/manifest.json \
  --provider market-baseline \
  --output /path/to/report.json
```

`backtest` is a deprecated alias for the same canonical baseline evaluator. It
writes the latest deterministic report for compatibility with `score-latest`:

```bash
python -m autopredict.cli backtest --dataset /path/to/dataset/manifest.json
python -m autopredict.cli score-latest
```

## Data Expectations

Use the single `autopredict.dataset.v1` contract in [DATASETS.md](DATASETS.md).
Forecast-safe observations contain point-in-time market probability and book data
but never outcomes. Resolution records are joined only inside evaluation. Record
hashes, UTC timestamps, ordered books, unique IDs, and completeness are validated
before any score is produced.

## Interpreting Results

- `candidate` and `baseline` contain proper scoring and calibration reports.
- `skill.brier_skill` is baseline Brier minus candidate Brier; positive is better.
- `skill.log_skill` is candidate log score minus baseline log score; positive is better.
- `rows` preserve independent event IDs for later uncertainty and promotion checks.

The v1 evaluator does not claim execution PnL or fills. Those require deterministic
event replay and shadow execution rather than static-book assumptions.

## Good Practice

- Keep train, calibration, and evaluation periods separate.
- Compare strategy changes on the same dataset hash.
- Promote only after chronological, regime, or market-family holdouts clear.
- Store archives for improvement runs so later regressions can be traced to the exact data and config.
