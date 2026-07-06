# Learning And Self-Improvement

AutoPredict's learning path is offline and audit-oriented. It mutates strategy parameters, evaluates them on explicit resolved data, and promotes winners only after held-out checks.

## Forecast-Owned Ratchet

```bash
python -m autopredict.cli learn improve \
  --dataset /path/to/resolved_markets.json \
  --archive-dir state/meta_harness/archives \
  --frontier-path state/meta_harness/frontier.json
```

The command:

- loads real resolved snapshots from `--dataset`
- builds walk-forward train/validation folds
- mutates a strategy genome
- evaluates candidates with proper scoring and execution metrics
- writes an archive when requested
- promotes to the frontier only when the selected score improves for the same dataset hash, split mode, and strategy kind

The default genome routes to the domain specialists, which use the market-implied
no-edge model (`fair_prob == market_prob`). That baseline never fabricates alpha,
but it also produces no edge, so every candidate scores identically and no trades
clear the edge gate — the search has nothing to improve until you supply a real
forecast.

## Recalibration Ratchet (learnable forecast)

```bash
python -m autopredict.cli learn improve \
  --dataset /path/to/resolved_markets.json \
  --recalibrate \
  --warmup-fraction 0.4 \
  --archive-dir state/meta_harness/archives
```

`--recalibrate` gives the loop a real, honest forecast to optimize. It applies a
monotonic recalibration of the market's own price:

```text
fair_prob = sigmoid(scale * logit(market_prob) + shift)
```

- `scale = 1.0, shift = 0.0` is the identity (`fair_prob == market_prob`, no edge)
  and is the baseline, so nothing is invented.
- `scale`/`shift` are fit by logistic regression on real `(market_prob, outcome)`
  pairs, **regularized toward the identity**. With little data or a well-calibrated
  market, the fit stays at (or near) no-edge; it only departs from the market where
  real resolved outcomes show the market is miscalibrated (e.g. favorite-longshot
  bias).
- The seed is fit only on the earliest `--warmup-fraction` of the (chronologically
  ordered) dataset. The remaining, strictly-later snapshots drive the walk-forward
  loop, so every promotion is validated on data the seed never saw — no look-ahead.

The recalibration `scale`/`shift` are also carried as searchable genome genes
(`calibration_logit_scale`, `calibration_logit_shift`), so mutation and held-out
promotion can refine the forecast alongside the risk and execution parameters.

Because a calibrated market produces near-identity recalibration and therefore no
trades, this path requires the caller's real resolved data — it bundles no market
datasets and claims no unverified alpha.

## Archives

Archives are JSON episode packages. They include provenance, dependency versions, dataset path/hash, config, final genome, fold metrics, report cards, rejection reasons, and warnings when present.

Use archives when comparing harness changes because scalar metrics alone are not enough to diagnose long-horizon failures.

## Frontier

The frontier is keyed by:

```text
dataset_hash | split_mode | strategy_kind
```

That keeps improvements comparable and prevents a run on one dataset from overwriting a different evaluation surface.

## Guardrails

- No bundled market datasets are used.
- No domain model trains on packaged examples by default.
- Missing live data remains missing.
- Promotions are explicit, scored, and tied to dataset identity.
