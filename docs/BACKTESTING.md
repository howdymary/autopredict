# Backtesting

AutoPredict backtests run only on explicit resolved-market data. The package no longer ships default market snapshots, generated datasets, or hidden fallback examples.

## CLI

```bash
python -m autopredict.cli backtest --dataset /path/to/resolved_markets.json
python -m autopredict.cli backtest \
  --config strategy_configs/baseline.json \
  --dataset /path/to/resolved_markets.json
```

`score-latest` reads the newest saved metrics:

```bash
python -m autopredict.cli score-latest
```

## Data Expectations

Use real historical/resolved market snapshots. At minimum, records should include the fields required by the loader you are using, such as:

- `market_id`
- `market_prob`
- `outcome`
- `time_to_expiry_hours` or equivalent expiry metadata
- order-book or liquidity fields when execution quality is being evaluated

If you provide `fair_prob`, the legacy loop can score that supplied forecast source. The package does not generate or bundle `fair_prob` values.

## Interpreting Results

- `brier_score` and `log_score` measure forecast quality.
- `total_pnl`, `win_rate`, and `sharpe` summarize simulated financial outcomes.
- `fill_rate`, `avg_slippage_bps`, and impact metrics describe execution quality.
- `agent_feedback` points at the most likely bottleneck.

## Good Practice

- Keep train, calibration, and evaluation periods separate.
- Compare strategy changes on the same dataset hash.
- Promote only after chronological, regime, or market-family holdouts clear.
- Store archives for improvement runs so later regressions can be traced to the exact data and config.
