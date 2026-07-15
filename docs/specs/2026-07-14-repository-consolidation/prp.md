# Repository Consolidation And Golden Path PRP

## Objective

Convert the product intent in `prd.md` into a staged implementation that first restores
repository integrity, then replaces overlapping legacy workflows with one auditable
evaluation and shadow-deployment path.

## Technical Shape

- Treat `autopredict.cli`, `autopredict.evaluation`, `autopredict.prediction_market`, and
  `autopredict.self_improvement` as the canonical package layers.
- Remove dead surfaces instead of maintaining `exec()`-based shims indefinitely.
- Introduce a versioned dataset manifest and forecast-provider protocol before changing
  evaluation semantics.
- Feed historical replay, shadow trading, and later live execution through the same normalized
  market events, strategy decisions, risk checks, and logs.
- Keep live submission behind a release gate until state reconciliation tests pass.

## Touch Points

- `autopredict/cli.py`: converge commands on the canonical loader and evaluator.
- `autopredict/evaluation/`: own schema loading, scoring, replay, and reports.
- `autopredict/prediction_market/`: own stable strategy and forecast-provider contracts.
- `autopredict/self_improvement/`: aggregate held-out evaluation and promotion rules.
- `autopredict/live/`: share shadow/live state, risk, reconciliation, and observability.
- `autopredict/markets/polymarket.py`: provide normalized public stream and authenticated venue boundaries.
- `scripts/run_paper.py` and `scripts/run_live.py`: shrink into package CLI adapters or remove.
- `.github/workflows/tests.yml`: add release-integrity gates.
- `README.md`, `QUICKSTART.md`, `docs/`: document one path and maturity model.

## Data / State Changes

- Add a dataset manifest containing schema version, venue, capture interval, source endpoints,
  content hashes, and completeness warnings.
- Store market metadata, book snapshots/deltas, trades, and resolutions as immutable records.
- Add durable shadow/live order state keyed by venue and idempotent client order ID.
- Version evaluation reports and frontier keys so incompatible methodologies cannot compare.

## API / Interface Changes

- Add a forecast-provider protocol returning probability, confidence, provenance, and optional rationale.
- Replace ambiguous backtest inputs with one validated dataset schema.
- Replace final-fold promotion with an aggregate out-of-fold promotion report.
- Expose shadow mode through the main `autopredict` CLI.
- Keep live execution unavailable unless an explicit release capability and preflight pass.

## Execution Sequence

1. Complete repository cleanup and release-integrity CI.
2. Define the canonical dataset and forecast-provider contracts.
3. Route `autopredict backtest/evaluate` through one engine and deprecate remaining root shims.
4. Implement Polymarket point-in-time recording and deterministic replay.
5. Implement shadow mode with durable state and reconciliation.
6. Strengthen held-out selection and promotion methodology.
7. Reassess live readiness against explicit operational gates.

## Parallelizable Work

- CI/repository layout can proceed alongside dataset-schema design.
- Forecast-provider contracts can proceed alongside the market recorder.
- Statistical promotion work can proceed after the report schema is fixed.
- Documentation can track each packet but must be finalized after interfaces stabilize.

## Testing Plan

- Compile and import every tracked/package Python module.
- Test source checkout and installed wheel independently.
- Contract-test dataset validation, forecast providers, and report serialization.
- Replay captured event fixtures deterministically and verify accounting invariants.
- Run shadow/live parity tests with a fake venue and restart/reconciliation scenarios.
- Test risk-reducing orders, stale feeds, duplicate submissions, partial fills, and cancellations.
- Verify promotion on aggregate out-of-fold forecasts with event-clustered samples.

## Observability / Debugging

- Structured decision, order, fill, reconciliation, and circuit-breaker events.
- Dataset completeness report and capture-gap counters.
- Report provenance containing code version, dataset hash, config, and forecast-provider version.
- Explicit rejection reasons for every candidate and promotion attempt.

## Rollout / Safety

- Land cleanup before changing runtime semantics.
- Feature-gate recorder and shadow mode until their schemas stabilize.
- Disable live submission by default and require a capability check in addition to credentials.
- Preserve a manual venue intervention path and cancel-all command.
- Roll back by disabling the new command while retaining immutable datasets and reports.

## Risks / Tradeoffs

- Removing code reduces surface area but can break undocumented imports; this is acceptable before
  stable API guarantees and is mitigated with migration notes.
- Realistic replay is slower and more data-intensive than snapshot simulation; correctness is more
  valuable than optimistic throughput for this product.
- Statistical gates will reduce the number of apparent improvements; that is an intended outcome.

## Definition Of Done

- [ ] Canonical package and CLI boundaries are documented and enforced.
- [ ] Repository and wheel integrity gates pass.
- [ ] One versioned data-to-report workflow is implemented.
- [ ] Shadow mode shares production normalization and risk logic.
- [ ] Promotion uses aggregate held-out evidence with uncertainty.
- [ ] Reviewer handoff and migration notes are current.
