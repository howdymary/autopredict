# Architecture

AutoPredict separates live observation, offline evaluation, and self-improvement so production paths do not depend on fabricated data.

## Runtime Layers

```text
live Polymarket data
  -> live_scan read-only reports

resolved historical data
  -> evaluation snapshots
  -> strategies
  -> simulated execution
  -> scoring/calibration metrics
  -> archives/frontier promotion
```

## Packages

- `autopredict.live_scan`: public Gamma/CLOB scanner. It is read-only and never emits fair probabilities or order recommendations.
- `autopredict.prediction_market`: typed scaffold for venue configs, market state, signals, decisions, and strategy registries.
- `autopredict.evaluation`: proper scoring rules, calibration summaries, slice reports, and backtest runners.
- `autopredict.self_improvement`: mutation, selection, walk-forward validation, archive writing, and frontier storage.
- `autopredict.ingestion`: normalization primitives for caller-provided finance, weather, and politics evidence.
- `autopredict.domains`: adapters and conservative domain specialist strategies.

## Data Policy

The package does not include default resolved-market datasets or fabricated domain evidence. Tests define their own local fixtures, but runtime commands require either live public venue data or explicit user-provided resolved data.

Default domain models are `MarketImpliedNoEdgeModel` instances. They pass through `market_prob`, report `verified_training_data: false`, and keep coverage at zero until real data is configured.

## Self-Improvement Flow

1. Load explicit resolved snapshots.
2. Build chronological, regime, or market-family held-out folds.
3. Mutate the active strategy genome.
4. Evaluate candidates through the same scoring/execution surface.
5. Reject regressions and sparse/unstable winners.
6. Write an archive with provenance and dataset hash.
7. Promote to the frontier only for a comparable key.

## Meta-Harness Learnings Applied

Recent harness work points in the same direction: keep traces and files available for diagnosis, gate commitments with verification, and treat the harness as part of the system being evaluated. AutoPredict applies that by preserving archives instead of scalar-only summaries, using held-out frontier keys, and keeping missing evidence explicit rather than filling gaps.
