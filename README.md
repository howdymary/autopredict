# AutoPredict

AutoPredict is a small framework for building, backtesting, and improving prediction-market agents without hiding synthetic data behind convenient defaults.

The current package has four production-facing surfaces:

- `autopredict.live_scan`: read-only Polymarket Gamma/CLOB scanner for live public market data
- `autopredict.prediction_market`: typed market snapshots, strategies, decisions, and venue metadata
- `autopredict.evaluation`: proper scoring rules, calibration summaries, and scaffold backtests
- `autopredict.self_improvement`: mutation, held-out promotion, archive writing, and frontier tracking

Domain-specialist defaults are conservative by design. Finance, weather, politics, and generic specialists now use market-implied no-edge forecasts until you provide verified training/evaluation data. That prevents packaged examples from masquerading as production alpha.

## Install

```bash
git clone https://github.com/howdymary/autopredict.git
cd autopredict
python -m pip install -e .
```

For the optional authenticated Polymarket order adapter:

```bash
python -m pip install -e ".[polymarket]"
```

## Live Scan

Use the live scanner to inspect public Polymarket data without placing orders or inventing fair values:

```bash
python -m autopredict.cli scan-live --limit 20 --top 5
python -m autopredict.cli scan-live --events --limit 20 --top 5 --json
python -m autopredict.cli safety-audit --config /path/to/your/live_trading.yaml
```

Market scans report observed Gamma prices plus public CLOB bid/ask/depth when available. Missing order-book data stays `null`/`n/a`; the scanner does not fill gaps with estimates.

## Backtest

Backtests require an explicit resolved-market dataset:

```bash
python -m autopredict.cli backtest --dataset /path/to/resolved_markets.json
python -m autopredict.cli score-latest
```

Each record should represent real historical/resolved market data with the fields consumed by `autopredict.evaluation.load_resolved_snapshots`, such as `market_id`, `market_prob`, `outcome`, and venue/order-book fields. The legacy loop may score a provided `fair_prob` column, but AutoPredict does not ship one.

## Improve

Run the forecast-owned ratchet on explicit resolved data:

```bash
python -m autopredict.cli learn improve \
  --dataset /path/to/resolved_markets.json \
  --archive-dir state/meta_harness/archives \
  --frontier-path state/meta_harness/frontier.json
```

The archive captures the run artifact, dataset hash, config, final genome, dependency versions, report cards, and warnings. The frontier accepts a run only when its explicit score improves for the same dataset hash, split mode, and strategy kind.

By default the loop routes to the market-implied no-edge model, so it can search risk/execution genes but has no forecast edge to improve. Add `--recalibrate` to let it learn an honest, out-of-sample-validated recalibration of the market's own prices:

```bash
python -m autopredict.cli learn improve \
  --dataset /path/to/resolved_markets.json \
  --recalibrate --warmup-fraction 0.4 \
  --archive-dir state/meta_harness/archives
```

The recalibration `fair_prob = sigmoid(scale * logit(market_prob) + shift)` defaults to the identity (no edge), is fit on real resolved outcomes with a prior toward no-edge, and is seeded only on a strictly-past window so promotions stay leakage-free. See [docs/LEARNING.md](docs/LEARNING.md#recalibration-ratchet-learnable-forecast).

## Data Policy

AutoPredict does not package default market datasets, generated market snapshots, or fabricated domain evidence. Test fixtures live in tests only. Runtime commands either read live venue data or require user-provided real historical/resolved data.

This matters for production use:

- No command silently falls back to bundled sample markets.
- No default domain model claims training support from unverified examples.
- Missing live fields remain missing rather than being replaced by synthetic probabilities.
- Meta-harness archives include dataset identity so improvements can be audited and reproduced.

## Core Pieces

- [autopredict/live_scan.py](autopredict/live_scan.py): read-only live Polymarket scanner
- [autopredict/prediction_market](autopredict/prediction_market): strategy interfaces, signals, decisions, and registry
- [autopredict/evaluation](autopredict/evaluation): scoring, calibration, and backtesting
- [autopredict/self_improvement](autopredict/self_improvement): mutation, held-out promotion, archives, and frontier store
- [autopredict/ingestion](autopredict/ingestion): normalization primitives for caller-provided evidence
- [autopredict/domains](autopredict/domains): adapters and conservative no-edge specialist defaults
- [market_env.py](market_env.py): legacy order-book simulation
- [agent.py](agent.py): legacy mutable baseline agent

## Documentation

Start with [QUICKSTART.md](QUICKSTART.md), then use:

- [docs/BACKTESTING.md](docs/BACKTESTING.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/LEARNING.md](docs/LEARNING.md)
- [docs/STRATEGIES.md](docs/STRATEGIES.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/fair_prob_guidelines.md](docs/fair_prob_guidelines.md)

## Included

AutoPredict includes read-only Polymarket market scanning, explicit-data backtesting,
scoring and calibration utilities, grouped slice diagnostics, and offline experiment
tracking for strategy variants. Runs can be archived with dataset and configuration
provenance so results are easier to compare and reproduce.

Live order execution requires a separately configured venue adapter and credentials.
Built-in domain specialists are neutral baselines unless you supply verified data and
models.

## License

MIT. See [LICENSE](LICENSE).
