# Repository Consolidation Review Handoff

## Scope

- Removes redundant, unshipped, unsafe, or broken legacy surfaces.
- Updates documentation references to canonical `docs/` files.
- Adds an issue audit, PRD, technical PRP, and staged task plan.
- Does not change forecast, execution, live-order, or evaluation behavior.

## Key Files

- `issue-audit.md`: prioritized repository and product issue register.
- `prd.md`: user outcome, scope, constraints, and release criteria.
- `prp.md`: technical boundaries, sequencing, testing, and rollout.
- `task-plan.md`: independently verifiable implementation packets.
- `CONTRIBUTING.md`: canonical documentation and evaluation paths.

## Behavior To Verify

- Source checkout no longer becomes an accidental top-level Python package.
- `autopredict.backtest` is absent rather than present but unimportable.
- The supported package CLI, scanner, safety audit, evaluation, and self-improvement imports remain intact.
- No maintained reference points to a deleted file.
- Wheel contents do not include the deleted legacy backtest package.

## Commands Already Run

- `python -m compileall -q autopredict validation scripts` -> passed.
- `python -m pytest tests -q` -> 305 passed; one environment-level LibreSSL warning.
- `python -m build --sdist --wheel` -> sdist and wheel built successfully.
- Installed-wheel import-all smoke -> 83 package modules imported; zero failures.
- `python -m autopredict.cli --help` -> canonical command list rendered.
- `python -m autopredict.cli safety-audit` -> passed with no findings.
- `python -m autopredict.cli scan-live --limit 2 --top 1 --no-books` -> public Polymarket scan returned current data without credentials.
- Maintained-reference search -> no runtime or test dependency on a deleted entrypoint.

## Expected Results

- Compile, source tests, build, and installed-package import checks pass.
- The read-only scanner and no-network safety audit remain operational.
- Grep finds no maintained dependency on deleted entrypoints.

## Known Risks

- External users may have imported the undocumented `autopredict.backtest` package.
- The repository still contains legacy root modules used by package shims; their removal is deferred until the canonical evaluator migration.
- This cleanup does not fix the no-op paper runner or live risk semantics; those are explicitly planned follow-ups.

## Open Questions

- Whether to provide a temporary compatibility package that raises a migration error for `autopredict.backtest`. The current recommendation is no: an absent module is clearer than an unversioned compatibility surface before `1.0`.

## Recommended Review Order

1. Review deleted-file dependency evidence and `issue-audit.md`.
2. Run compile, test, and wheel import checks.
3. Inspect the PRD/PRP boundaries for scope creep.
4. Confirm follow-on task ordering and live-safety gates.
