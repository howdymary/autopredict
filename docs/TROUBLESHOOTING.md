# Troubleshooting

## `backtest requires --dataset`

This is expected. AutoPredict does not ship default market datasets. Pass a real resolved-market JSON file:

```bash
python -m autopredict.cli backtest --dataset /path/to/resolved_markets.json
```

## `learn improve requires --dataset`

The improvement loop also requires explicit resolved data:

```bash
python -m autopredict.cli learn improve --dataset /path/to/resolved_markets.json
```

## Live Scanner Has Missing Book Fields

The scanner reports missing CLOB fields as `null` or `n/a`. It does not synthesize order-book levels. Retry later, increase `--timeout`, or run with `--no-books` to inspect Gamma prices only.

## Domain Specialists Hold Everything

That is the safe packaged default. Domain specialists use market-implied no-edge forecasts until verified domain data and models are configured.

## Frontier Promotion Fails

Check that the archive includes:

- `dataset.sha256`
- a split mode in config
- a final genome with `strategy_kind`
- a finite score for the selected metric

The frontier rejects runs that are worse than the current entry or use a different metric direction for the same key.
