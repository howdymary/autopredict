# Repo File Audit

This audit classifies every file currently present under `/Users/maryliu/Projects/autopredict`.

Verdicts:

- `keep`: active source, tests, docs, or config that still earns its place.
- `merge later`: currently useful, but overlaps another file or exists as a migration seam that should eventually collapse.
- `archive only`: historical context worth preserving, but not part of the active product surface.
- `remove from repo`: generated or obsolete; safe to keep locally if useful, but it should not live in the maintained source tree.

## Repo metadata and top-level docs

- `.github/workflows/tests.yml` — `keep`: active CI coverage for the supported Python versions and wheel smoke tests.
- `.gitignore` — `keep`: protects secrets and keeps generated outputs out of version control.
- `ARCHITECTURE.md` — `keep`: short top-level pointer that gives readers a fast path to the main architecture guide.
- `CONTRIBUTING.md` — `keep`: contributor workflow, layout, and standards doc.
- `LICENSE` — `keep`: required licensing metadata.
- `QUICKSTART.md` — `keep`: focused onboarding path for new users.
- `README.md` — `keep`: canonical repo entrypoint.
- `ROADMAP.md` — `keep`: product direction and phased delivery context.
- `__init__.py` — `merge later`: namespace bridge for the root-level legacy modules during migration to the packaged layout.
- `agent.py` — `merge later`: legacy mutable-agent entrypoint still used by tests and migration compatibility, but conceptually overlaps the packaged scaffold.
- `cli.py` — `merge later`: legacy CLI still useful for the flat layout, but the packaged CLI is the cleaner long-term surface.
- `config.json` — `merge later`: identical to `autopredict/_defaults/config.json`; still needed by the root CLI during migration.
- `conftest.py` — `keep`: root pytest bootstrap that makes the mixed legacy and packaged layout testable.
- `market_env.py` — `merge later`: core legacy simulator still underpins the older experiment harness, but its responsibilities overlap newer packaged evaluation code.
- `pyproject.toml` — `keep`: packaging, dependency, and test configuration source of truth.
- `run_experiment.py` — `merge later`: active legacy experiment loop that still earns its place until the packaged runtime fully replaces it.
- `run_experiment_with_validation.py` — `merge later`: useful validation-integrated example, but it should eventually become an example or script instead of a published top-level module.
- `strategy.md` — `merge later`: identical to `autopredict/_defaults/strategy.md`; still supports the root workflow.
- `validation.py` — `merge later`: legacy validation entrypoint that overlaps the dedicated `validation/` package.

## Packaged docs and defaults

- `autopredict/README.md` — `merge later`: useful package-level overview, but it largely overlaps the root README and could be folded into main docs later.
- `autopredict/__init__.py` — `merge later`: package namespace bridge that keeps legacy root modules importable under `autopredict.*` during migration.
- `autopredict/_defaults/config.json` — `keep`: packaged default config for installed-wheel workflows.
- `autopredict/_defaults/datasets/finance_domain_examples.json` — `keep`: versioned offline finance training/calibration/evaluation dataset for the domain model path.
- `autopredict/_defaults/datasets/politics_domain_examples.json` — `keep`: versioned offline politics training/calibration/evaluation dataset.
- `autopredict/_defaults/datasets/sample_markets.json` — `keep`: packaged sample markets fixture for installed workflows.
- `autopredict/_defaults/datasets/weather_domain_examples.json` — `keep`: versioned offline weather training/calibration/evaluation dataset.
- `autopredict/_defaults/strategy.md` — `keep`: packaged strategy guidance for installed workflows.
- `autopredict/_defaults/strategy_configs/baseline.json` — `keep`: packaged default strategy config for installed workflows.

## Packaged legacy backtest stack

- `autopredict/backtest/__init__.py` — `merge later`: stable import surface for the older packaged backtest stack.
- `autopredict/backtest/analysis.py` — `merge later`: still useful performance analysis code, but conceptually overlaps newer evaluation reporting.
- `autopredict/backtest/cli.py` — `merge later`: command helpers for the older backtest subsystem; likely collapsible into the main CLI later.
- `autopredict/backtest/engine.py` — `merge later`: active execution/backtest engine for the older packaged path; overlaps the scaffold-native backtester conceptually.
- `autopredict/backtest/metrics.py` — `merge later`: useful metrics library, but partially duplicated by `autopredict/evaluation`.

## Packaged runtime and configuration

- `autopredict/cli.py` — `keep`: canonical packaged CLI entrypoint.
- `autopredict/config/__init__.py` — `keep`: package export surface for configuration loading.
- `autopredict/config/loader.py` — `keep`: real config loading logic with YAML support.
- `autopredict/config/schema.py` — `keep`: structured config definitions and validation.
- `autopredict/core/__init__.py` — `keep`: package export surface for typed core objects.
- `autopredict/core/types.py` — `keep`: central typed market/order/portfolio model used across the repo.

## Domain specialization layer

- `autopredict/domains/__init__.py` — `keep`: consolidated export surface for adapters, models, and strategies.
- `autopredict/domains/base.py` — `keep`: shared `DomainFeatureBundle` and specialist helper contracts.
- `autopredict/domains/finance/__init__.py` — `keep`: finance-domain export surface.
- `autopredict/domains/finance/adapter.py` — `keep`: finance evidence-to-bundle adapter.
- `autopredict/domains/finance/model.py` — `keep`: default finance question-conditioned model builder over the offline dataset.
- `autopredict/domains/finance/strategy.py` — `keep`: finance specialist strategy that plugs the model into the generic scaffold.
- `autopredict/domains/modeling.py` — `keep`: shared dataset/model/report-card implementation for all specialist domains.
- `autopredict/domains/politics/__init__.py` — `keep`: politics-domain export surface.
- `autopredict/domains/politics/adapter.py` — `keep`: politics evidence-to-bundle adapter.
- `autopredict/domains/politics/model.py` — `keep`: default politics question-conditioned model builder.
- `autopredict/domains/politics/strategy.py` — `keep`: politics specialist strategy.
- `autopredict/domains/registry.py` — `keep`: domain adapter registry.
- `autopredict/domains/weather/__init__.py` — `keep`: weather-domain export surface.
- `autopredict/domains/weather/adapter.py` — `keep`: weather evidence-to-bundle adapter.
- `autopredict/domains/weather/model.py` — `keep`: default weather question-conditioned model builder.
- `autopredict/domains/weather/strategy.py` — `keep`: weather specialist strategy.

## Evaluation, ingestion, scaffold, and self-improvement

- `autopredict/evaluation/__init__.py` — `keep`: export surface for scaffold-native evaluation primitives.
- `autopredict/evaluation/backtest.py` — `keep`: deterministic scaffold-native backtester.
- `autopredict/evaluation/domain_slices.py` — `keep`: grouped slice diagnostics for domain/family/regime analysis.
- `autopredict/evaluation/scoring.py` — `keep`: proper scoring rules and calibration summaries.
- `autopredict/ingestion/__init__.py` — `keep`: export surface for fixture-backed evidence ingestion.
- `autopredict/ingestion/base.py` — `keep`: normalized evidence contracts shared across domains.
- `autopredict/ingestion/cache.py` — `keep`: lightweight local cache helpers for fixture-backed ingestion.
- `autopredict/ingestion/finance/__init__.py` — `keep`: finance ingestion export surface.
- `autopredict/ingestion/finance/features.py` — `keep`: finance feature builders.
- `autopredict/ingestion/finance/fixtures.py` — `keep`: deterministic finance ingestion fixtures.
- `autopredict/ingestion/finance/macro.py` — `keep`: finance macro-ingestion normalization.
- `autopredict/ingestion/finance/market_data.py` — `keep`: finance market-data normalization.
- `autopredict/ingestion/politics/__init__.py` — `keep`: politics ingestion export surface.
- `autopredict/ingestion/politics/events.py` — `keep`: politics event normalization.
- `autopredict/ingestion/politics/features.py` — `keep`: politics feature builders.
- `autopredict/ingestion/politics/fixtures.py` — `keep`: deterministic politics ingestion fixtures.
- `autopredict/ingestion/politics/news.py` — `keep`: politics news normalization.
- `autopredict/ingestion/politics/polls.py` — `keep`: politics polling normalization.
- `autopredict/ingestion/registry.py` — `keep`: ingestor registry.
- `autopredict/ingestion/weather/__init__.py` — `keep`: weather ingestion export surface.
- `autopredict/ingestion/weather/features.py` — `keep`: weather feature builders.
- `autopredict/ingestion/weather/fixtures.py` — `keep`: deterministic weather ingestion fixtures.
- `autopredict/ingestion/weather/forecasts.py` — `keep`: weather forecast normalization.
- `autopredict/ingestion/weather/observations.py` — `keep`: weather observation normalization.
- `autopredict/prediction_market/__init__.py` — `keep`: scaffold export surface.
- `autopredict/prediction_market/agent.py` — `keep`: package-native prediction-market agent runtime.
- `autopredict/prediction_market/builtin.py` — `keep`: built-in strategies and compatibility adapters.
- `autopredict/prediction_market/registry.py` — `keep`: strategy factory registry.
- `autopredict/prediction_market/strategy.py` — `keep`: scaffold strategy protocol.
- `autopredict/prediction_market/types.py` — `keep`: typed snapshot, signal, and decision objects.
- `autopredict/self_improvement/__init__.py` — `keep`: self-improvement export surface.
- `autopredict/self_improvement/loop.py` — `keep`: improvement-loop orchestration and held-out validation logic.
- `autopredict/self_improvement/mutation.py` — `keep`: strategy mutation surface.
- `autopredict/self_improvement/selection.py` — `keep`: selection guardrails and Phase 5 report-card comparison hooks.

## Other packaged runtime modules

- `autopredict/learning/README.md` — `merge later`: useful package-specific learning guide, but it overlaps `docs/LEARNING.md`.
- `autopredict/learning/__init__.py` — `keep`: learning-module export surface.
- `autopredict/learning/analyzer.py` — `keep`: performance analysis utilities used by the learning workflow.
- `autopredict/learning/logger.py` — `keep`: trade logging and decision trace infrastructure.
- `autopredict/learning/tuner.py` — `keep`: parameter tuning utilities still used by the older experimentation path.
- `autopredict/live/__init__.py` — `keep`: live-trading package surface, even though the feature is intentionally disabled by default.
- `autopredict/live/monitor.py` — `keep`: live monitoring scaffolding.
- `autopredict/live/risk.py` — `keep`: live risk-management scaffolding.
- `autopredict/live/trader.py` — `keep`: paper/live trading execution scaffolding.
- `autopredict/markets/__init__.py` — `keep`: venue-adapter package surface.
- `autopredict/markets/base.py` — `keep`: venue-adapter protocol.
- `autopredict/markets/manifold.py` — `keep`: Manifold adapter scaffolding.
- `autopredict/markets/polymarket.py` — `keep`: Polymarket adapter scaffolding.
- `autopredict/strategies/__init__.py` — `keep`: strategy package surface.
- `autopredict/strategies/base.py` — `keep`: base strategy protocol and risk-limit helpers.
- `autopredict/strategies/mispriced_probability.py` — `keep`: baseline strategy used by legacy and migration paths.

## Configs and datasets

- `configs/README.md` — `keep`: explains live and paper trading config files.
- `configs/live_trading.yaml.example` — `keep`: example only, not a secret-bearing active config.
- `configs/paper_trading.yaml` — `keep`: default paper-trading config for local experiments.
- `datasets/sample_markets.json` — `merge later`: identical to `autopredict/_defaults/datasets/sample_markets.json`; still useful for root-level workflows.
- `datasets/sample_markets_100.json` — `keep`: larger sample dataset for more realistic backtests and demos.
- `datasets/sample_markets_500.json` — `keep`: stress-test/sample dataset for broader evaluation.
- `datasets/test_markets_minimal.json` — `keep`: compact deterministic dataset for tests and examples.
- `strategy_configs/baseline.json` — `merge later`: identical to `autopredict/_defaults/strategy_configs/baseline.json`; still used by the flat layout.

## Active docs

- `docs/ARCHITECTURE.md` — `keep`: main system design and layering document.
- `docs/BACKTESTING.md` — `keep`: operational guide for the backtest flow.
- `docs/DEPLOYMENT.md` — `keep`: deployment and ops guide.
- `docs/LEARNING.md` — `keep`: active self-improvement/learning guide.
- `docs/METRICS.md` — `keep`: active metrics reference.
- `docs/README.md` — `keep`: docs index.
- `docs/REPO_FILE_AUDIT.md` — `keep`: this audit; useful as a cleanup and migration checklist.
- `docs/STRATEGIES.md` — `keep`: active strategy-development guide.
- `docs/TROUBLESHOOTING.md` — `keep`: active troubleshooting guide.
- `docs/fair_prob_guidelines.md` — `keep`: active forecasting-quality guidance.

## Archived docs

- `docs/archive/ARCHITECTURE_PROPOSAL.md` — `archive only`: historical architecture proposal, useful for provenance but not the active system definition.
- `docs/archive/BACKTESTING_ENGINE.md` — `archive only`: earlier backtest-engine writeup retained for history.
- `docs/archive/CALIBRATION_QUICK_REFERENCE.md` — `archive only`: historical quick-reference card for calibration work.
- `docs/archive/CALIBRATION_RECOMMENDATIONS.md` — `archive only`: detailed calibration recommendations preserved as historical analysis.
- `docs/archive/CALIBRATION_SUMMARY.md` — `archive only`: executive summary of earlier calibration work.
- `docs/archive/DELIVERABLES_SUMMARY.md` — `archive only`: phase deliverables record, not active product documentation.
- `docs/archive/DIAGNOSIS.md` — `archive only`: point-in-time diagnosis of the repo before later phases landed.
- `docs/archive/DOCUMENTATION_SUMMARY.md` — `archive only`: historical summary of a documentation pass.
- `docs/archive/EVALUATION.md` — `archive only`: earlier evaluation report retained as design context.
- `docs/archive/EVALUATION_SUMMARY.md` — `archive only`: executive summary for the archived evaluation report.
- `docs/archive/FINAL_SUMMARY.md` — `archive only`: historical integration summary.
- `docs/archive/INTEGRATION_REPORT.md` — `archive only`: historical integration report, not active guidance.
- `docs/archive/MIGRATION_PLAN.md` — `archive only`: migration planning artifact that is still informative but no longer the active source of truth.
- `docs/archive/PAPER.md` — `archive only`: long-form paper/design narrative worth preserving, but not part of the active docs surface.
- `docs/archive/PHASE2_SUMMARY.md` — `archive only`: historical phase summary.
- `docs/archive/PHASE3_DELIVERABLES.md` — `archive only`: historical phase deliverables summary.
- `docs/archive/PHASE4_DELIVERABLES.md` — `archive only`: historical phase deliverables summary.
- `docs/archive/PHASE4_SUMMARY.md` — `archive only`: historical phase summary.
- `docs/archive/QUICKREF.md` — `archive only`: historical quick-reference artifact.
- `docs/archive/README.md` — `archive only`: index for the archive itself.
- `docs/archive/README_CALIBRATION.md` — `archive only`: historical calibration implementation guide.
- `docs/archive/RESULTS.md` — `archive only`: archived experiment/results document.
- `docs/archive/SELF_IMPROVEMENT.md` — `archive only`: earlier self-improvement writeup superseded by active architecture and learning docs.
- `docs/archive/TESTING_INFRASTRUCTURE.md` — `archive only`: historical testing writeup.
- `docs/archive/TRADING_PLAYBOOK.md` — `archive only`: operational playbook retained as historical material.
- `docs/archive/WORKFLOW.md` — `archive only`: earlier workflow documentation retained for context.
- `docs/archive/calibration_recommendations.json` — `archive only`: archived machine-readable output from prior calibration analysis.

## Examples, notebooks, and prompts

- `examples/backtest_mispriced_prob.py` — `keep`: active example of the baseline strategy on the backtest loop.
- `examples/custom_metrics/README.md` — `keep`: explains the custom-metrics example.
- `examples/custom_metrics/custom_metrics.py` — `keep`: working extension example for custom metrics.
- `examples/custom_metrics/run_with_custom_metrics.py` — `keep`: runnable example entrypoint.
- `examples/custom_strategy/README.md` — `keep`: explains the custom strategy example.
- `examples/custom_strategy/conservative_agent.py` — `keep`: concrete custom-agent example.
- `examples/custom_strategy/run_conservative.py` — `keep`: runnable comparison example.
- `examples/learning_demo.py` — `keep`: active learning workflow example.
- `examples/real_data_integration/README.md` — `keep`: documents the real-data integration example.
- `examples/real_data_integration/adapters.py` — `keep`: useful adapter example for real-data integrations.
- `notebooks/01_basic_backtest.ipynb` — `keep`: exploratory notebook for basic backtests.
- `notebooks/02_strategy_comparison.ipynb` — `keep`: exploratory notebook for strategy comparison.
- `notebooks/03_performance_analysis.ipynb` — `keep`: exploratory notebook for performance analysis.
- `notebooks/04_parameter_tuning.ipynb` — `keep`: exploratory notebook for tuning workflows.
- `prompts/builder_codex.md` — `archive only`: internal prompt asset only referenced from archived evaluation docs.
- `prompts/evaluator_codex.md` — `archive only`: internal prompt asset only referenced from archived evaluation docs.

## Scripts

- `scripts/__init__.py` — `keep`: package marker for script helpers.
- `scripts/calibration_analysis.py` — `merge later`: still useful analysis utility, but better as an example or archive tool than core repo surface.
- `scripts/demo.sh` — `keep`: convenient repo walkthrough/demo script.
- `scripts/detailed_calibration_report.py` — `merge later`: still useful for analysis, but overlaps active docs and archived calibration material.
- `scripts/generate_dataset.py` — `keep`: practical dataset-generation helper.
- `scripts/learn_and_improve.py` — `keep`: useful top-level entrypoint for the learning workflow.
- `scripts/run_live.py` — `keep`: operational live-run entrypoint for future use.
- `scripts/run_paper.py` — `keep`: operational paper-trading entrypoint.
- `scripts/validation_demo.py` — `merge later`: useful validation demo, but it belongs more naturally under `examples/`.
- `scripts/verify_infrastructure.sh` — `keep`: onboarding/infrastructure verification helper.
- `scripts/verify_phase2.py` — `remove from repo`: phase-specific one-off verification script with no live references and strong overlap with the automated test suite.

## Tests

- `tests/__init__.py` — `keep`: package marker for the test suite.
- `tests/conftest.py` — `keep`: shared test fixtures and utilities.
- `tests/test_agent.py` — `keep`: regression coverage for the legacy agent.
- `tests/test_cli_smoke.py` — `keep`: smoke coverage for the packaged CLI.
- `tests/test_config.py` — `keep`: config-system coverage.
- `tests/test_core_types.py` — `keep`: typed-core contract coverage.
- `tests/test_domain_adapters.py` — `keep`: Phase 1 domain-adapter coverage.
- `tests/test_domain_models.py` — `keep`: Phase 3-5 dataset/model/report-card coverage.
- `tests/test_domain_slice_reports.py` — `keep`: grouped domain slice reporting coverage.
- `tests/test_domain_strategies.py` — `keep`: Phase 2-3 specialist-strategy integration coverage.
- `tests/test_evaluation.py` — `keep`: package evaluation coverage.
- `tests/test_evaluation_scaffold.py` — `keep`: scaffold-level evaluation contract coverage.
- `tests/test_ingestion_finance.py` — `keep`: finance ingestion coverage.
- `tests/test_ingestion_politics.py` — `keep`: politics ingestion coverage.
- `tests/test_ingestion_weather.py` — `keep`: weather ingestion coverage.
- `tests/test_learning.py` — `keep`: learning module coverage.
- `tests/test_market_env.py` — `keep`: legacy market environment and execution coverage.
- `tests/test_mispriced_strategy.py` — `keep`: baseline-strategy coverage.
- `tests/test_monitor.py` — `keep`: live-monitoring coverage.
- `tests/test_prediction_market_scaffold.py` — `keep`: Step 1 scaffold coverage.
- `tests/test_risk.py` — `keep`: live-risk coverage.
- `tests/test_self_improvement.py` — `keep`: Step 3-5 mutation/selection/walk-forward coverage.
- `tests/test_trader.py` — `keep`: trader execution coverage.
- `tests/test_validation.py` — `keep`: validation-system coverage.

## Validation package

- `validation/__init__.py` — `keep`: validation package surface.
- `validation/fair_prob.py` — `keep`: fair-probability validation helpers.
- `validation/validator.py` — `keep`: richer validation logic used by the validation path.

## Generated local-only artifacts

- `.pytest_cache/.gitignore` — `remove from repo`: pytest-generated cache metadata; useful locally, not as maintained source.
- `.pytest_cache/CACHEDIR.TAG` — `remove from repo`: pytest cache marker.
- `.pytest_cache/README.md` — `remove from repo`: pytest cache metadata doc.
- `.pytest_cache/v/cache/lastfailed` — `remove from repo`: local test-run state.
- `.pytest_cache/v/cache/nodeids` — `remove from repo`: local test-run state.
- `autopredict.egg-info/PKG-INFO` — `remove from repo`: build artifact generated by packaging tools.
- `autopredict.egg-info/SOURCES.txt` — `remove from repo`: packaging artifact.
- `autopredict.egg-info/dependency_links.txt` — `remove from repo`: packaging artifact.
- `autopredict.egg-info/entry_points.txt` — `remove from repo`: packaging artifact.
- `autopredict.egg-info/requires.txt` — `remove from repo`: packaging artifact.
- `autopredict.egg-info/top_level.txt` — `remove from repo`: packaging artifact.
- `state/backtests/20260327-160047/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-160522/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-160758/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-160759/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-161654/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-161750/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-161927/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-162014/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-215638/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-220524/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-220528/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-221243/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-221800/metrics.json` — `remove from repo`: generated run output captured from a local backtest.
- `state/backtests/20260327-222659/metrics.json` — `remove from repo`: generated run output captured from a local backtest.

## Highest-value cleanup targets

- Collapse the identical root/package duplicate defaults: `config.json`, `strategy.md`, `strategy_configs/baseline.json`, and `datasets/sample_markets.json`.
- Decide when the root compatibility layer can retire: `__init__.py`, `agent.py`, `cli.py`, `market_env.py`, `run_experiment.py`, and `run_experiment_with_validation.py`.
- Remove generated artifacts from the working tree before commits: `.pytest_cache/`, `autopredict.egg-info/`, and `state/backtests/`.
- Move phase-specific or analysis-only helpers out of the main surface when convenient: `scripts/verify_phase2.py`, `scripts/calibration_analysis.py`, `scripts/detailed_calibration_report.py`, and `scripts/validation_demo.py`.
