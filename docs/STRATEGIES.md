# Strategies

Strategies in AutoPredict turn market snapshots into decisions. The active production-safe defaults are conservative: when verified forecast data is not configured, specialist strategies use market-implied no-edge probabilities and hold rather than inventing alpha.

## Strategy Surfaces

- `agent.py`: legacy configurable agent used by the original backtest loop
- `autopredict.prediction_market`: scaffold-native strategy protocol and decision objects
- `autopredict.domains`: finance, weather, politics, and generic specialist wrappers
- `autopredict.self_improvement.mutation`: deterministic genome mutation for offline search

## Default Behavior

Domain specialists consume `DomainFeatureBundle` metadata and features, but their packaged default models do not claim verified training support. They return the observed `market_prob` as a neutral no-edge forecast until you wire real, versioned training/evaluation data.

## Comparing Strategies

Use the same resolved dataset and config surface for every comparison:

```bash
python -m autopredict.cli backtest \
  --config strategy_configs/baseline.json \
  --dataset /path/to/resolved_markets.json
```

For self-improvement, use:

```bash
python -m autopredict.cli learn improve \
  --dataset /path/to/resolved_markets.json \
  --archive-dir state/meta_harness/archives \
  --frontier-path state/meta_harness/frontier.json
```

## Promotion Rules

Do not promote from PnL alone. Require forecast quality, calibration, execution quality, and held-out robustness to move together.
