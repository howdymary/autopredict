# AutoPredict

AutoPredict is a framework for building and backtesting prediction market trading agents.

The repo now includes three additive package-native layers alongside the legacy experiment harness:

- `autopredict.prediction_market` for scaffold-native strategies and decisions
- `autopredict.evaluation` for proper scoring rules, calibration summaries, and scaffold backtests
- `autopredict.self_improvement` for mutation, selection, and promotion loops

It also now includes a domain-specialization scaffold with model-backed specialist strategies:

- `autopredict.ingestion` for fixture-backed evidence normalization
- `autopredict.domains` for domain adapters and question-conditioned specialist strategies that emit or consume `domain`, `market_family`, and `regime` labels

It keeps the market simulator fixed, the trading logic mutable, and the iteration loop tight:

1. run a backtest
2. inspect forecast, PnL, and execution metrics
3. change one config or strategy decision
4. rerun and compare

## What makes it useful

- Fixed evaluation environment: order book simulation, execution quality, and scoring stay stable across experiments.
- Mutable strategy surface: you can evolve the agent through `agent.py` and `strategy_configs/*.json`.
- Execution-aware metrics: the framework treats slippage, fill rate, and market impact as first-class, not afterthoughts.
- Lightweight local workflow: one small runtime dependency (`PyYAML`) plus the Python standard library.

## Quick start

```bash
git clone https://github.com/howdymary/autopredict.git
cd autopredict
python -m pip install -e .

python -m autopredict.cli backtest
python -m autopredict.cli score-latest
```

The editable install pulls in the package runtime dependencies, including `PyYAML` for configuration loading.

Example output:

```json
{
  "total_pnl": 23.848357929641246,
  "sharpe": 4.426818787804096,
  "brier_score": 0.25475000000000003,
  "fill_rate": 0.4420699362191731,
  "num_trades": 4.0,
  "forecast_source": "dataset_fair_prob",
  "agent_feedback": {
    "weakness": "forecast_input_quality",
    "hypothesis": "The supplied fair_prob inputs appear poorly calibrated; improve the upstream forecast source before blaming execution logic."
  }
}
```

To run your first full iteration, start with [QUICKSTART.md](QUICKSTART.md).

## Core pieces

- [autopredict/prediction_market](autopredict/prediction_market): scaffold-native strategy interfaces, typed signals/decisions, and legacy bridge adapters
- [autopredict/evaluation](autopredict/evaluation): proper scoring rules, calibration summaries, and scaffold-level backtests
- [autopredict/self_improvement](autopredict/self_improvement): deterministic mutation, evaluation, and selection loops
- [autopredict/ingestion](autopredict/ingestion): fixture-backed evidence normalization for finance, weather, and politics
- [autopredict/domains](autopredict/domains): domain adapters that translate evidence into normalized feature bundles and split labels
- [market_env.py](market_env.py): order books, execution simulation, and evaluation metrics
- [agent.py](agent.py): the mutable baseline agent
- [run_experiment.py](run_experiment.py): the backtest loop
- [autopredict/cli.py](autopredict/cli.py): packaged command-line entrypoint
- [strategy_configs](strategy_configs): tunable strategy parameters
- [datasets](datasets): sample market snapshots
- [tests](tests): automated regression coverage

## Step 1 scaffold

Step 1 adds a dedicated prediction-market agent layer under
`autopredict.prediction_market`. It is intentionally additive and does not
replace the current backtest loop or baseline strategy.

This package introduces:

- venue-aware snapshots via `VenueConfig` and `MarketSnapshot`
- typed signal and decision objects such as `MarketSignal` and `AgentDecision`
- a `PredictionMarketAgent` that cleanly separates signal generation from order generation
- a strategy registry for later mutation, A/B testing, and selection workflows
- a bridge adapter, `LegacyMispricedStrategyAdapter`, that runs the existing `MispricedProbabilityStrategy` through the new scaffold

That scaffold now feeds the next package-native layers:

- Step 2 adds proper scoring rules, calibration analysis, and execution-aware backtests
- Step 3 mutates and ranks strategies through the registry instead of rewriting runtime entrypoints

## Step 2 evaluation

Step 2 adds a dedicated evaluation layer under `autopredict.evaluation`. Its job is to score the new scaffold with proper scoring rules and to keep backtest logic separate from strategy logic.

The evaluation layer is centered on three kinds of outputs:

- proper scoring rules: `brier_score`, `log_score`, and `spherical_score`
- calibration summaries: bucketed reliability views and forecast-vs-outcome drift
- scaffold backtests: deterministic, venue-aware checks on fills, slippage, and realized outcomes

That gives later strategy mutation work a stable target: the agent can change, but the scoring surface stays fixed.

## Step 3 self-improvement

Step 3 adds a dedicated self-improvement layer under `autopredict.self_improvement`. It mutates strategy variants, runs them through `autopredict.evaluation`, and keeps the winners behind score and calibration guardrails.

In practice, that means:

- strategy variants can be cloned, perturbed, and re-scored without changing the agent runtime
- promotion decisions depend on proper scoring rules and calibration, not PnL alone
- walk-forward promotion can gate mutations on chronological slices, regime blocks, or market-family holdouts
- the registry and evaluation layers stay stable while the search loop iterates

The goal is a simple improvement loop: generate variants, evaluate them, keep the ones that improve forecast quality and execution quality together.

The default family holdout key is `category`, which uses raw category metadata when available and falls back to `MarketState.category`. Regime splits can either use explicit labels such as `metadata.regime` or auto-bucket market conditions like spread and liquidity.

## Domain specialization

Phase 1 adds the evidence and labeling contract, Phase 2 threads that contract into scaffold-native specialist strategies, Phase 3 swaps the heuristic signal logic for lightweight learned question-conditioned models, Phase 4 adds offline train/calibration/evaluation datasets for those defaults, and Phase 5 versions those datasets and attaches model report cards so promotion can compare lineage and held-out quality together:

- `autopredict.ingestion` normalizes fixture-backed evidence for finance, weather, and politics
- `autopredict.domains` turns that evidence into normalized feature bundles with stable `domain`, `market_family`, and `regime` labels
- domain-specialist strategies consume those bundle-derived snapshot features inside the same scaffold agent and backtester
- offline dataset manifests now carry stable `dataset_name`, `dataset_version`, and split coverage summaries for each specialist default
- domain model report cards summarize coverage, held-out calibration stability, and evaluation metrics before model-backed specialists are compared in selection loops

In practice, the handoff is: fixture evidence -> `IngestionBatch` -> `DomainFeatureBundle` -> merged snapshot features and labels -> versioned offline dataset -> held-out calibrated domain model -> domain model report card -> specialist strategy -> grouped evaluation and held-out self-improvement splits.

Those labels now plug directly into backtests, grouped slice diagnostics, and held-out promotion. The default specialist strategies are model-backed, calibrated on held-out examples, and still deterministic and local, so the runtime seam stays reusable for stronger future models.

## What it measures

AutoPredict reports three groups of metrics:

- Epistemic: `brier_score`, `calibration_by_bucket`
- Financial: `total_pnl`, `sharpe`, `max_drawdown`, `win_rate`
- Execution: `avg_slippage_bps`, `fill_rate`, `market_impact_bps`, `implementation_shortfall_bps`

In the legacy evaluator, `sharpe` is intentionally reported as an unannualized per-trade return-to-volatility ratio so configs are not rewarded just for trading more often. The evaluator also exposes `calculate_composite_score(...)` for baseline-relative ratchet decisions.
On that same legacy loop, `forecast_source` is reported as `dataset_fair_prob`, so Brier and calibration describe the supplied input forecast column rather than a forecast generated by `agent.py`.

The framework also returns `agent_feedback`, a short diagnosis of the current bottleneck:

- `execution_quality`
- `forecast_input_quality`
- `limit_fill_quality`
- `calibration`
- `risk`
- `selection`

## Documentation

Start here:

- [QUICKSTART.md](QUICKSTART.md)
- [docs/README.md](docs/README.md)

Most useful guides:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/STRATEGIES.md](docs/STRATEGIES.md)
- [docs/BACKTESTING.md](docs/BACKTESTING.md)
- [docs/METRICS.md](docs/METRICS.md)
- [docs/LEARNING.md](docs/LEARNING.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/fair_prob_guidelines.md](docs/fair_prob_guidelines.md)

Historical design notes, phase summaries, and internal reports live under [docs/archive](docs/archive).

## Scope today

Good today:

- local backtesting
- strategy and config iteration
- packaged CLI from a repo checkout or installed wheel
- execution-aware metrics
- test coverage for core components
- a prediction-market-specific scaffold that keeps venue logic separate from the experiment harness
- a package-native evaluation layer with Brier, log, and spherical scoring
- grouped slice diagnostics that flag sparse or unstable domain families
- a self-improvement prototype that mutates, selects, and validates strategy variants across time, regimes, and market families
- fixture-backed ingestion, domain adapters, versioned offline train/calibration/evaluation datasets, report-carded domain models, and calibrated model-backed specialist strategies for finance, weather, and politics

Intentionally limited today:

- live trading is disabled by default
- exchange integrations are still scaffolding
- autonomous self-editing is not part of the runtime yet
- promotion is still deterministic and offline; it supports chronological, regime, and family holdouts, but not live evaluation
- domain-specialist strategies are question-conditioned and calibrated on offline held-out datasets, but still offline rather than live-data-driven

## License

MIT. See [LICENSE](LICENSE).
