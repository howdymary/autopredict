# Repository Consolidation And Golden Path PRD

## Summary

AutoPredict needs one trustworthy path from real point-in-time market data to forecast
evaluation, shadow trading, and guarded promotion. This initiative removes misleading
legacy surfaces, defines the canonical product path, and establishes release gates for
developers who want to evaluate prediction-market forecasts without fabricated data.

## Problem

The repository currently exposes overlapping backtest implementations, duplicate CLIs,
incomplete paper/live workflows, and documentation that describes different maturity
levels. Some unused legacy code does not compile, yet the wheel can still build. The
result is a broad framework whose strongest ideas—data honesty, proper scoring, and
auditable promotion—are harder to trust and adopt.

The prioritized evidence is captured in `issue-audit.md`.

## Goals

- Establish `autopredict.evaluation` and `autopredict.cli` as canonical public surfaces.
- Make source and wheel validation fail on syntax, import, schema, or workflow breakage.
- Define a single data-to-report workflow that can later run unchanged in shadow mode.
- Align product claims with behavior and explicit release gates.

## Non-Goals

- Invent or bundle a profitable forecasting model.
- Enable new real-money trading behavior in this consolidation.
- Add additional venues before the Polymarket golden path is reliable.
- Preserve every unversioned compatibility script indefinitely.

## Users / Operators

- Primary: quantitative and AI developers bringing their own forecast source.
- Secondary: maintainers reviewing experiments, releases, and live-safety readiness.

## Use Cases

- Install AutoPredict and scan public Polymarket data without credentials.
- Validate and evaluate a versioned resolved-market dataset with a user forecast provider.
- Compare a model against the market-implied baseline on aggregate held-out predictions.
- Run the same strategy in shadow mode before live execution is even available.

## User Experience / Behavior

The supported journey should be obvious from `autopredict --help` and the README:

```text
record/ingest -> validate -> evaluate -> report -> shadow -> promote
```

Unsupported or experimental behavior must fail closed with an actionable message. Removed
legacy module paths are not silently redirected to behavior with different semantics.

## Requirements

- One canonical dataset schema with a version and point-in-time timestamps.
- One canonical backtest/evaluation engine and CLI route.
- A forecast-provider boundary with an explicit market-implied baseline.
- Aggregate out-of-fold reporting relative to that baseline.
- CI verification from both a source checkout and an installed wheel.
- Shadow execution must share strategy, risk, logging, and market normalization with live mode.
- Live execution remains disabled until durable reconciliation and risk gates pass.

## Constraints

- Runtime paths may not silently fabricate missing market or forecast data.
- Credentials and live actions remain opt-in and fail closed.
- Historical datasets are caller-provided until a first-party recorder is implemented.
- Breaking cleanup is acceptable before a stable `1.0` API, but it must be documented.

## Success Criteria

- Fresh install, public scan, package imports, and documented smoke commands all pass in CI.
- A user sees one documented dataset contract and one evaluation output contract.
- Every promotion reports aggregate held-out skill versus the market baseline.
- Shadow mode can operate continuously for seven days without state reconciliation drift.

## Acceptance Criteria

- [ ] No tracked Python file fails `compileall`.
- [ ] No public package included in the wheel fails an import-all smoke test.
- [ ] Source-tree pytest and installed-wheel tests pass on supported Python versions.
- [ ] Root duplicate entrypoints and the broken legacy backtest package are removed.
- [ ] Documentation names only the canonical architecture and CLI paths.
- [ ] The follow-on task plan has binary completion and verification criteria.

## Risks

- Removing legacy imports may affect unknown users. Mitigation: document the removal before a
  stable release and provide migration guidance to `autopredict.evaluation`.
- Consolidation can accidentally mix legacy and scaffold semantics. Mitigation: preserve
  behavior until one schema and one engine are selected, then change them behind explicit tests.
- Product scope may expand again. Mitigation: gate roadmap work on golden-path success metrics.

## Open Questions

- Should the first stable dataset format be JSON Lines plus a manifest or Parquet plus a
  manifest? Proposed default: Parquet for event data, JSON for manifests and reports.
- Should legacy root modules receive one deprecation release? Proposed default: keep only
  modules still used by the package CLI, then remove them during canonical-engine migration.
