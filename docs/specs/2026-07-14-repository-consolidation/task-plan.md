# Repository Consolidation And Golden Path Task Plan

## Outcome

Ship a smaller, trustworthy AutoPredict repository with one buildable package today and a
sequenced plan for a canonical evaluation-to-shadow workflow.

## Work Packets

### Packet 1: Remove Dead And Broken Surfaces

- Owner: coder
- Goal: remove code that is broken, unshipped, redundant, or contrary to the current data policy.
- Files: root `__init__.py`, root CLI wrappers, `autopredict/backtest/`, its example, doc references.
- Dependencies: dependency/reference audit.
- Done when: deleted files have no maintained references and source/wheel imports improve rather than regress.

### Packet 2: Release-Integrity CI

- Owner: coder + tester
- Goal: make syntax, source-import, wheel-import, format, and test failures impossible to miss.
- Files: `.github/workflows/tests.yml`, `pyproject.toml`, optional test helpers.
- Dependencies: Packet 1.
- Done when: CI runs compile, lint/format, source tests, wheel build/install, and import-all smoke checks.

### Packet 3: Canonical Schema And Evaluation CLI

- Owner: planner + coder
- Goal: route one documented dataset contract through one evaluator and report schema.
- Files: `autopredict/cli.py`, `autopredict/evaluation/`, `validation/`, docs and tests.
- Dependencies: Packet 2.
- Done when: one example dataset validates, evaluates, and produces a versioned report; inconsistent input fails clearly.

### Packet 4: Forecast Provider Boundary

- Owner: coder
- Goal: let users bring a forecast without injecting opaque objects into snapshot metadata.
- Files: `autopredict/prediction_market/`, `autopredict/domains/`, evaluation tests and examples.
- Dependencies: Packet 3 contract decisions.
- Done when: market baseline, recalibration, and user provider implement the same typed interface and provenance contract.

### Packet 5: Polymarket Recorder And Replay

- Owner: coder + tester
- Goal: capture point-in-time market metadata, book events, trades, and resolution for deterministic replay.
- Files: `autopredict/markets/polymarket.py`, new data/recording modules, CLI, dataset tests.
- Dependencies: Packet 3 schema.
- Done when: a recorded fixture replays deterministically and completeness/hash metadata is verifiable.

### Packet 6: Real Shadow Trading

- Owner: coder + tester
- Goal: replace the sleeping paper runner with the same decision/risk path used by later live mode.
- Files: `autopredict/live/`, package CLI, `scripts/run_paper.py`, monitor and risk tests.
- Dependencies: Packets 4 and 5.
- Done when: shadow mode consumes live public data, produces simulated fills, persists state, and survives restart reconciliation.

### Packet 7: Statistical Promotion Hardening

- Owner: planner + coder + reviewer
- Goal: prevent single-fold and multiple-selection artifacts from entering the frontier.
- Files: `autopredict/self_improvement/`, `autopredict/evaluation/`, archive/frontier tests.
- Dependencies: Packet 3 report schema.
- Done when: promotion uses aggregate out-of-fold skill versus market, minimum independent-event counts, uncertainty, and explicit rejection reasons.

### Packet 8: Live Safety Readiness Review

- Owner: reviewer + tester
- Goal: decide whether live submission can be exposed, based on evidence rather than schedule.
- Files: live adapter, risk, reconciliation, deployment docs, security docs.
- Dependencies: Packets 2, 5, 6, and 7.
- Done when: direction-aware risk, durable orders, idempotency, stale-feed halts, cancel-all, and multi-day shadow gates all pass.

## Ordering

1. Packets 1-2: repository integrity.
2. Packets 3-4: canonical product contracts.
3. Packets 5-6: real data and shadow operation.
4. Packet 7: defensible promotion.
5. Packet 8: live-readiness decision.

## Parallel Notes

- Packet 2 test helpers and Packet 3 schema proposal can overlap after deletion scope freezes.
- Packet 4 and recorder implementation can overlap once the snapshot contract is approved.
- Packet 7 can begin after versioned reports exist; it need not wait for full shadow mode.
- Packet 8 must remain serialized after the operational prerequisites.

## Risks / Blockers

- No authoritative historical dataset: default to building the recorder before claiming execution realism.
- Unknown users of legacy imports: document removals and avoid silent semantic redirects.
- Venue API changes: isolate raw payload parsing behind fixture-backed adapter contracts.
- Insufficient independent outcomes: block promotion rather than lowering statistical gates.

## Verification Matrix

- Repository compiles -> `python -m compileall -q autopredict validation scripts`
- Canonical package imports -> import-all smoke test from source and installed wheel
- Unit/integration behavior -> `python -m pytest tests -q`
- Packaging -> `python -m build --sdist --wheel`
- Public read-only workflow -> `python -m autopredict.cli scan-live --limit 2 --top 1 --no-books`
- Safety baseline -> `python -m autopredict.cli safety-audit`
- Removed references -> `rg 'autopredict\.backtest|python predict\.py|python cli\.py'`
