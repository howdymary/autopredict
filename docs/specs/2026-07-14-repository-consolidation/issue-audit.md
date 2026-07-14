# AutoPredict Issue Identification

## Scope

This audit covers the current repository architecture, supported command-line workflows,
packaging, evaluation methodology, paper/live execution, and documentation. Priorities use:

- **P0**: blocks trustworthy development or distribution
- **P1**: blocks a credible end-to-end product workflow
- **P2**: undermines evaluation validity or operational reliability
- **P3**: product clarity, maintainability, or adoption improvement

## Issue Register

| ID | Priority | Issue | Evidence | Impact | Proposed resolution |
| --- | --- | --- | --- | --- | --- |
| AP-001 | P0 | Broken and redundant legacy backtest package | `autopredict/backtest/engine.py` did not compile, had no maintained CLI entrypoint, and was used only by a broken example. | Wheels could build while shipping an unimportable public package. | Remove the package and example; make `autopredict.evaluation` the canonical implementation. Completed by this cleanup. |
| AP-002 | P0 | Root `__init__.py` breaks source-tree test collection | The repository root was treated as a Python package and accessed `__path__` when imported as a plain module. | A normal local `pytest` invocation failed during setup. | Remove the root initializer; retain only `autopredict/__init__.py`. Completed by this cleanup. |
| AP-003 | P0 | Multiple overlapping CLI and compatibility entrypoints | Root `cli.py`, `predict.py`, package CLI, console scripts, and root/package shims exposed different behavior. | Users could not tell which workflow was supported. | Remove unshipped root CLI wrappers now; migrate remaining legacy modules behind one package-native CLI in Packet 3. |
| AP-004 | P0 | CI can miss syntax and installed-package failures | CI runs pytest and a narrow wheel smoke test but not `compileall`, import-all, formatting, or typing. | Broken modules can merge and ship. | Add compile, format/lint, type, source-test, and installed-wheel import gates. |
| AP-005 | P0 | Backtest command and documented dataset contract disagree | `autopredict.cli backtest` calls the legacy evaluator, while documentation points toward `load_resolved_snapshots`; the legacy path requires `fair_prob` and `next_mid_price`. | First-time users cannot prepare a reliably valid dataset. | Define a versioned schema and route all evaluation through one loader and engine. |
| AP-006 | P1 | Paper trading loop does not fetch, decide, or trade | `scripts/run_paper.py` initializes components and sleeps while emitting zero metrics. | The primary safety gate before live execution is not real. | Build paper/shadow execution from the same live market feed and strategy path as live mode. |
| AP-007 | P1 | Live product messaging is contradictory | Package `trade-live` is disabled, while `autopredict-live` can submit orders and deployment docs describe live support. | Users may infer a maturity level the system has not earned. | Mark live execution experimental and disabled until shadow and safety gates pass; align all docs and commands. |
| AP-008 | P1 | Risk checks are not direction-aware | Pre-trade position and exposure calculations add order size/notional even for risk-reducing orders. | Closing trades can be blocked and exposure can be misstated. | Calculate signed post-trade positions and exposure; always allow validated risk-reducing orders within venue constraints. |
| AP-009 | P1 | Live state and resting orders are not durable | Resting orders and local positions are primarily memory-backed; restart reconciliation is incomplete. | A restart can lose order state or diverge from the venue. | Add durable order state, idempotent client IDs, startup reconciliation, cancel-all, and stale-state circuit breakers. |
| AP-010 | P1 | No first-party point-in-time market recorder | The scanner polls current REST data but does not persist CLOB deltas, trades, resolutions, and metadata as a replayable dataset. | Realistic backtests and shadow/live parity are impossible. | Record Polymarket Gamma metadata and public CLOB WebSocket events into immutable, versioned datasets. |
| AP-011 | P2 | Default validation folds are statistically too small | Walk-forward defaults use three training snapshots and one validation snapshot. | A single market can determine promotion. | Enforce minimum independent-event counts and aggregate all out-of-fold forecasts before selection. |
| AP-012 | P2 | Frontier promotion uses the final fold only | CLI promotion reads the last fold's `log_score`. | The promoted frontier may not represent total held-out performance. | Promote on an aggregate out-of-fold report with confidence intervals and explicit metric direction. |
| AP-013 | P2 | Mutation selection lacks multiple-testing protection | The best of several mutations is repeatedly selected on small folds. | Reported improvement is optimistically biased. | Use nested selection/final evaluation, record all attempts, and apply repeated or bootstrapped held-out checks. |
| AP-014 | P2 | Passive fill simulation is optimistic | Fill rate is derived from limit-price aggressiveness and static visible liquidity. | Backtest PnL can materially overstate executable performance. | Replay book events and model queue position, latency, cancellation, fees, and sensitivity bands. |
| AP-015 | P2 | “Self-improvement” exceeds current model scope | The learnable model is a global two-parameter market recalibration. | Product claims can be mistaken for general autonomous forecasting. | Call the current feature recalibration/parameter search; add a forecast-provider interface before restoring broader claims. |
| AP-016 | P3 | Roadmap and maturity labels are stale | Roadmap dates and the Beta classifier do not match the implemented product. | Contributors and users receive incorrect expectations. | Rebase roadmap on measurable release gates and label the project Alpha until the golden path is complete. |

## Deletion Decisions In This Change

The cleanup removes files only when all of the following are true:

1. The file is not an active packaging or console-script entrypoint.
2. No maintained test or runtime path requires it.
3. A canonical replacement exists, or the file is broken/misleading with no supported use.
4. Removing it makes failure more explicit instead of silently changing trading behavior.

Removed surfaces:

- Root packaging/CLI ambiguity: `__init__.py`, `cli.py`, `predict.py`
- Redundant architecture pointer: `ARCHITECTURE.md`
- Unshipped, evidence-claiming validator: `validation.py`
- Broken legacy backtest package: `autopredict/backtest/`
- Example that depended exclusively on that broken package: `examples/backtest_mispriced_prob.py`

## Recommended Product Decision

Position AutoPredict as a reproducible **forecast evaluation and shadow-deployment
framework**. The product should prove that a user-provided forecast adds held-out value
over the market baseline before exposing real-money execution.
