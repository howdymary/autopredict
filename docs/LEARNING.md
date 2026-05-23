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
