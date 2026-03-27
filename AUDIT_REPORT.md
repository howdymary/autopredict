# AutoPredict Adversarial Audit

Date: 2026-03-27
Branch: `codex/phase5-report-cards-audit`

## Verdict

If this repository were pointed at real money on Polymarket or Kalshi tomorrow, it would fail before the first trustworthy production trade. The active backtest loop is also not yet a valid `autoresearch` ratchet for end-to-end prediction-market agents: it optimizes execution against an exogenous `fair_prob` column and uses legacy financial metrics that can mis-rank strategies.

This report is grounded in direct inspection of the current codebase and baseline runs, not in roadmap claims.

## Scope And Method

Inspected directly:

- `run_experiment.py`
- `market_env.py`
- `agent.py`
- `cli.py`
- `autopredict/cli.py`
- `autopredict/live/trader.py`
- `autopredict/markets/base.py`
- `autopredict/markets/polymarket.py`
- `autopredict/markets/manifold.py`
- `autopredict/core/types.py`
- `scripts/run_live.py`
- `.gitignore`
- `configs/live_trading.yaml.example`
- `tests/conftest.py`
- `tests/test_trader.py`

Reproduced locally:

- `python -m autopredict.cli backtest --dataset /Users/maryliu/Projects/autopredict/datasets/sample_markets_500.json`
- `python /Users/maryliu/Projects/autopredict/run_experiment.py` (fails as a direct script)

Quick data sanity checks:

- `datasets/sample_markets.json`: 6 records, no invalid or unsorted order-book records on a quick pass
- `datasets/sample_markets_500.json`: 500 records, no invalid or unsorted order-book records on a quick pass

Baseline behavior:

- `sample_markets.json`: 4 trades out of 6 markets, `sharpe=7.6675`, `brier_score=0.2548`
- `sample_markets_500.json`: 312 trades out of 500 markets, `sharpe=5.4598`, `brier_score=0.2021`, `total_pnl=695.50`

## Severity Definitions

- `P0`: blocks safe production deployment
- `P1`: blocks a trustworthy autoresearch loop
- `P2`: materially weakens realism or scientific validity, but can be worked around temporarily
- `P3`: cleanup or roadmap work

## Executive Summary

1. The live trading stack is not wired end-to-end.
2. The adapter layer and live trader do not agree on interfaces or types.
3. The active CLI backtest does not test forecasting skill; it tests trade execution given a provided forecast.
4. The legacy Sharpe and drawdown calculations can distort the ratchet.
5. The repo is safer than the prompt assumed in a few places: `.env` is already ignored, no hardcoded live secrets were found in inspected configs, and the 500-market sample is usable for experimentation.

## P0 Findings

### P0-1: Real venue trading is not implemented

Evidence:

- `autopredict/markets/polymarket.py:67-100` returns `[]` from `get_markets()`
- `autopredict/markets/polymarket.py:102-115` returns `None` from `get_market()`
- `autopredict/markets/polymarket.py:117-155` raises `NotImplementedError` from `place_order()`
- `autopredict/markets/manifold.py:49-95` returns `[]` from `get_markets()`
- `autopredict/markets/manifold.py:97-111` returns `None` from `get_market()`
- `autopredict/markets/manifold.py:113-163` raises `NotImplementedError` from `place_order()`
- There is no `autopredict/markets/kalshi.py`
- `scripts/run_live.py:215-218` still instantiates `MockVenueAdapter()`

Why this is `P0`:

The repo cannot fetch live markets, cannot place a real venue order, and does not contain a Kalshi adapter at all. Production deployment is blocked by missing core functionality, not by tuning quality.

### P0-2: The live execution contracts are internally inconsistent

Evidence:

- `autopredict/markets/base.py:79-104` defines adapters in terms of `place_order(order: autopredict.core.types.Order) -> autopredict.core.types.ExecutionReport`
- `autopredict/live/trader.py:109` expects `submit_order(order: autopredict.live.trader.Order) -> autopredict.live.trader.ExecutionReport`
- Direct runtime inspection confirms `autopredict.live.trader.Order is not autopredict.core.types.Order`
- Direct runtime inspection confirms `autopredict.live.trader.ExecutionReport` fields differ from `autopredict.core.types.ExecutionReport`

Why this is `P0`:

Even a completed adapter against the market-adapter protocol would not cleanly plug into `LiveTrader` without an additional translation layer. This is a structural integration failure waiting to happen.

### P0-3: Live trading safety guarantees are overstated and incomplete

Evidence:

- `autopredict/live/trader.py:286-291` claims credential validation and risk checks before every trade
- `autopredict/live/trader.py:317-329` only stores `venue_adapter` and a `safety_checks` flag
- `autopredict/live/trader.py:361-406` validates the order and forwards it to `venue_adapter.submit_order(order)`, but does not perform credential checks, explicit risk-manager checks, or partial-fill reconciliation
- `autopredict/live/trader.py:408-423` kill switch only flips `self.is_active = False`
- `scripts/run_live.py:253-262` contains comments describing the production loop, but no actual fetch-decide-check-execute-update path

Why this is `P0`:

The code advertises production safeguards that are not fully enforced by the live path. In the presence of partial fills, adapter exceptions, or mismatched venue state, the system has no reconciliation or rollback story.

### P0-4: There is no production-grade market data path

Evidence:

- `autopredict/markets/polymarket.py:63-65` has a commented-out client init
- `autopredict/markets/polymarket.py:227-232` synthesizes `best_bid` and `best_ask` as `market_prob +/- 0.01`
- no WebSocket client exists under `autopredict/markets/`
- no request backoff, throttling, or Cloudflare handling logic is present in the inspected adapters

Why this is `P0`:

Prediction-market execution depends on accurate real-time order books. Placeholder spreads and missing rate-limit handling make the live path unusable.

## P1 Findings

### P1-1: Legacy Sharpe is inflated by trade count

Evidence:

- `market_env.py:662-666` computes `sharpe = mean(pnl) / std(pnl) * sqrt(len(pnl_series))`

Why this is `P1`:

This makes Sharpe depend directly on the number of trades, not on a fixed sampling interval. A configuration that trades more frequently can look better even if its per-trade distribution is not actually superior. That corrupts any ratchet based on the metric.

### P1-2: Legacy drawdown is computed on cumulative dollar PnL, not portfolio equity or returns

Evidence:

- `market_env.py:668-674` tracks drawdown from a cumulative PnL path starting at zero

Why this is `P1`:

This is not an equity-relative drawdown measure. It is directionally useful, but it is not comparable across bankroll sizes or strategy leverage choices in the way the autoresearch prompt assumes.

### P1-3: The active CLI path scores dataset `fair_prob`, not an agent-generated forecast

Evidence:

- `run_experiment.py:62-78` reads `fair_prob` directly from the dataset and appends `ForecastRecord(... probability=fair_prob, outcome=outcome)`
- `agent.py:418` uses that same `fair_prob` as input to compute edge
- `market_env.py:685-705` mixes those forecast metrics into the combined evaluation output

Why this is `P1`:

The current root loop does not test whether the agent can forecast markets. It tests whether an execution policy can monetize a supplied forecast. Brier score and calibration therefore describe the dataset inputs, not the trading agent's epistemic skill.

This is the most important scientific gap in the current `autoresearch` framing.

### P1-4: The active backtest path lacks robust input validation

Evidence:

- `run_experiment.py:17-23` builds `BookLevel`s by blindly casting values to float
- `run_experiment.py:62-68` directly indexes `record["market_id"]`, `record["market_prob"]`, `record["fair_prob"]`, `record["outcome"]`, and `record["order_book"]`
- `market_env.py:28-45` gives `BookLevel` no validation
- `market_env.py:80-82` sorts bids and asks but does not validate ranges, positivity, or crossed books

Why this is `P1`:

The current sample datasets are clean enough to run, but this path is brittle against malformed or adversarial data. A ratchet that is meant to run unattended needs deterministic failure modes and explicit validation, not incidental success on clean fixtures.

### P1-5: PaperTrader limit fills are stochastic and unseeded

Evidence:

- `autopredict/live/trader.py:221-235` imports `random` and calls `random.random()` without a seed
- `tests/conftest.py` does not seed global randomness

Why this is `P1`:

Any improvement loop that uses `PaperTrader` for evaluation inherits run-to-run randomness and loses ratchet reliability.

Important nuance:

The active CLI backtest does not use `PaperTrader`; it uses `market_env.ExecutionEngine`. So this is not the reason the current root backtest is deterministic. It is still a blocker for any paper/live experimentation path described as part of the future research loop.

## P2 Findings

### P2-1: The strategy logic is execution-aware but mathematically simplified

Evidence:

- `agent.py:418-445` uses symmetric absolute-edge thresholds and linear sizing

Why this matters:

Binary markets have asymmetric payout geometry near 0 and 1. The current sizing is a pragmatic heuristic, not Kelly or fractional Kelly. That can be reasonable, but it should be treated as a design choice, not as statistically principled sizing.

### P2-2: Order-book simulation is deliberately simple

Evidence:

- `market_env.py:159-221` walks only visible depth
- `market_env.py:341-356` uses a static passive-fill model with fixed bonuses and caps

Why this matters:

There is no queue position, hidden-liquidity, or pulled-liquidity modeling. The environment is fine as a fast scaffold, but it is not a high-fidelity venue simulator.

### P2-3: The smallest bundled dataset is too small for honest research decisions

Evidence:

- `sample_markets.json` contains 6 records
- baseline on that file produced only 4 trades

Why this matters:

Any Sharpe-like or drawdown-like signal from 4 trades is noise. The 500-market sample is much more appropriate for ratchet experiments than the 6-record fixture.

### P2-4: The root experiment entrypoint is easy to invoke incorrectly

Evidence:

- `run_experiment.py:8-9` uses relative imports
- direct invocation with `python run_experiment.py` fails with `ImportError: attempted relative import with no known parent package`
- module invocation via `python -m autopredict.cli backtest` works

Why this matters:

This is not a scientific failure, but it is an operational footgun.

### P2-5: The repo now contains a more principled package-native scaffold, but the default CLI still targets the legacy loop

Evidence:

- `autopredict/cli.py:12` imports `.run_experiment`
- the active run path still resolves to the legacy root experiment structure and metrics

Why this matters:

There is architectural progress elsewhere in the repo, but the default user-facing backtest path still evaluates the older execution-centric loop. That gap should be made explicit.

## P3 Findings

### P3-1: The live and learning roadmap is ahead of the current implementation

Examples:

- `trade-live` intentionally exits as a placeholder in both CLIs
- the tuning and improvement CLI commands currently redirect users to scripts rather than running a complete integrated loop

This is acceptable for a scaffold, but it should be described plainly.

## Verified Non-Findings

These claims did not hold up as stated in the prompt:

1. `.env` handling is already reasonable.
   - `.gitignore:22-29` already ignores `.env`, `.env.local`, and common secret YAML patterns.

2. No hardcoded production secrets were found in the inspected config files.
   - `configs/live_trading.yaml.example:5-11` explicitly tells users to keep real config out of version control.
   - `configs/live_trading.yaml.example:41-42` references environment variables instead of embedding secrets.

3. The bundled 500-market dataset is not obviously malformed.
   - Quick inspection found no invalid probabilities or unsorted books in the sampled files used for baseline runs.

4. The current root backtest path is deterministic.
   - It uses `market_env.ExecutionEngine`, not the stochastic `PaperTrader`.

## Gate Decision

### Production Deployment Gate

Status: `FAIL`

Reason:

- No functional Polymarket adapter
- No Kalshi adapter
- Mock live runner
- Broken live type/interface boundary
- Missing production-grade order-book and order-submission path

### Autoresearch Gate

Status: `FAIL`

Reason:

- Legacy Sharpe and drawdown are not fit for a ratchet without adjustment
- The active forecast metrics score exogenous dataset forecasts, not agent forecasts
- Paper-trading research paths remain stochastic if they route through `PaperTrader`

Important note:

The prompt only gates Phase 2 on `P0` resolution, but in practice the `P1` issues above also block a scientifically honest ratchet. Fixing only the production blockers would still leave the research conclusions unreliable.

## Recommended Fix Order

1. Freeze one active evaluator path.
   - Decide whether the canonical ratchet should run on the legacy root loop or the newer package-native scaffold.

2. Fix ratchet metrics before any optimization campaign.
   - Replace trade-count-scaled Sharpe
   - Use an equity-aware drawdown definition
   - Add an explicit deterministic composite score implementation

3. Be explicit about what the system is optimizing.
   - Either:
     - treat the current loop as an execution optimizer given external forecasts, or
     - require the agent to generate forecasts so Brier and calibration measure the agent

4. Unify the live trading contracts.
   - One `Order`
   - One `ExecutionReport`
   - One adapter protocol

5. Only then implement real venue adapters.
   - Polymarket first
   - Kalshi second
   - Add credential validation, rate limiting, and a non-placeholder live loop

6. Run autoresearch on `sample_markets_500.json`, not the 6-record fixture.

## Bottom Line

AutoPredict is currently closer to a promising research scaffold than to a production trading system. The strongest part of the repo today is the ability to run quick, deterministic execution-focused backtests on resolved sample markets. The weakest part is the mismatch between that reality and the stronger claims implied by the live-trading and autoresearch framing.

That is still a useful result. It means the next step is not "tune harder." The next step is to tighten the evaluator, clarify the forecasting boundary, and unify the live execution interfaces before trusting any self-improvement loop.
