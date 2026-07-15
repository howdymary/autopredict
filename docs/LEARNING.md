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
- considers frontier promotion only after a corrected paired-evidence check passes for the same dataset hash, split mode, and strategy kind

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

Archive schema 2 also records a canonical content-derived attempt ID, a separate
optional operator run ID, raw-evidence and content SHA-256 digests,
dataset/method/provider versions, the corrected threshold, and the complete
evidence summary. The rebuild path cross-checks those independent provenance
fields before promotion. Archive
schema 1 did not preserve enough evidence to reproduce a decision and therefore
fails with an explicit migration error if passed to `promote_archive`; rerun the
offline evaluation to create a schema-2 archive.

Use archives when comparing harness changes because scalar metrics alone are not enough to diagnose long-horizon failures.

## Frontier

The frontier is keyed by:

```text
dataset_hash | split_mode | strategy_kind
```

That keeps improvements comparable and prevents a run on one dataset from overwriting a different evaluation surface.

Frontier acceptance is intentionally stricter than a scalar score comparison:

- every out-of-fold selected forecast is paired with the contemporaneous market probability on the same resolved row
- the exact multiset of `(fold_index, event_id, market_id[, snapshot_id])` row identities must match the declared holdout surface; duplicate or reweighted identities fail closed
- distinct markets under one event may resolve differently, while outcome consistency is enforced for each event-and-market pair
- uncertainty is still clustered by `event_id`, so correlated markets and snapshots do not increase the independent sample count
- frontier promotion always requires at least 30 independent events, alpha at most 0.05, and Bonferroni correction, even if an archive records a more lenient exploratory policy
- uncertainty is computed from event-cluster mean Brier-loss differences using a finite-sample one-sided Student-t bound
- the one-sided alpha is Bonferroni-corrected by the number of candidate hypotheses tried in the run
- that hypothesis count is derived from a complete per-fold attempted-artifact manifest and cannot be supplied independently
- the corrected lower confidence bound must exceed the configured minimum improvement
- each row identifies its evaluated provider and artifact; mixed fold winners are promoted as the evaluated walk-forward trajectory rather than falsely attributed to the final genome
- the contemporaneous market probability is carried by the typed forecast record, while row provider/artifact identity is derived from the canonical fold winner and provider configuration
- missing rows, swapped mappings, duplicate weighting, non-finite values, conflicting outcomes, and incomplete metadata reject the attempt without writing the frontier
- immutable attempt IDs are checked across the whole frontier before score comparison

Small 3/1 train-validation folds may evolve the local ratchet. The 30-event gate
applies only after their out-of-fold evidence is aggregated for frontier
promotion. Bonferroni correction covers the hypotheses declared within one
attempt; repeatedly searching the same dataset across separate attempts remains
exploratory and is recorded as a caveat in frontier metadata.

## Guardrails

- No bundled market datasets are used.
- No domain model trains on packaged examples by default.
- Missing live data remains missing.
- Promotions are explicit, statistically corrected, auditable, and tied to dataset identity.
