# AutoPredict Adversarial Audit Report

**Date:** 2026-03-27
**Scope:** Full codebase audit against the question: "If deployed to trade real money on Polymarket and Kalshi tomorrow, what would break?"
**Verdict:** Not production-ready. Multiple P0 blockers. The autoresearch loop is viable after targeted fixes.

---

## Baseline Metrics (Pre-Audit Reference)

| Metric | 6 markets | 100 markets | 500 markets |
|---|---|---|---|
| Trades executed | 4 | 59 | 312 |
| Total PnL | +23.85 | +135.26 | +695.50 |
| Sharpe | 7.67 | 2.44 | 5.46 |
| Win rate | 100% | 61% | 63% |
| Fill rate | 0.44 | 0.61 | 0.65 |
| Avg slippage (bps) | 0 | 55.3 | 79.6 |
| Max drawdown | 0 | 22.77 | 34.28 |
| Brier score | 0.255 | 0.189 | 0.202 |

---

## P0 — Blocks Production Deployment AND Autoresearch Loop

### P0-1: Sharpe Ratio Scales with Trade Count (Corrupts Ratchet Metric)

**File:** `market_env.py:666`
**Bug:** `sharpe = mean(pnl) / std(pnl) * sqrt(len(pnl_series))`

The annualization factor uses `sqrt(N)` where N is the number of trades, not a fixed time period. This means:
- A config that trades 4 times gets a `sqrt(4) = 2x` multiplier
- A config that trades 400 times gets `sqrt(400) = 20x` multiplier

**Impact on autoresearch:** A configuration that simply trades more often will report a higher Sharpe, even if per-trade quality is identical or worse. The ratchet would systematically accept configs that lower edge thresholds (more trades = inflated Sharpe) and reject configs that raise them. **This completely corrupts the composite score.**

**Evidence:** Baseline Sharpe is 7.67 with 4 trades (6-market dataset) vs 5.46 with 312 trades (500-market dataset). The per-trade mean/std ratio is actually better with 312 trades, but the `sqrt(N)` factor doesn't scale linearly because the two datasets have different underlying characteristics.

**Fix:** Report un-annualized Sharpe (`mean / std`) or annualize with a fixed factor (e.g., `sqrt(252)` for daily). Document the choice.

```python
# Option A: Un-annualized (simplest, recommended for autoresearch)
sharpe = (statistics.fmean(pnl_series) / std) if std > EPSILON else 0.0

# Option B: Fixed annualization (if comparing to industry benchmarks)
ANNUALIZATION_FACTOR = math.sqrt(252)  # assuming ~1 trade/day
sharpe = (statistics.fmean(pnl_series) / std * ANNUALIZATION_FACTOR) if std > EPSILON else 0.0
```

---

### P0-2: Non-Deterministic Limit Order Fills in PaperTrader

**File:** `autopredict/live/trader.py:223-235`
**Bug:** `PaperTrader._execute_limit_order()` calls `random.random()` (line 235) without seeding.

```python
def _execute_limit_order(self, order, current_price):
    import random  # imported at function scope
    ...
    filled = is_executable or (random.random() < self.limit_fill_rate)
```

**Impact:** While `PaperTrader` is not used in the core `run_experiment.py` backtest loop (which uses `market_env.ExecutionEngine` with deterministic fill rates), any test or workflow that uses `PaperTrader` produces non-reproducible results. The `tests/conftest.py` does NOT seed `random`.

**Note:** The core backtest loop in `market_env.py` uses a deterministic fill rate model (`BASE_FILL_RATE + bonuses`, capped at `MAX_FILL_RATE = 0.75`), so **the autoresearch ratchet IS deterministic as currently configured.** This is P0 for production but P1 for the autoresearch loop specifically.

**Fix:** Add `seed` parameter to `PaperTrader.__init__()`:
```python
def __init__(self, ..., seed: int | None = 42):
    ...
    self._rng = random.Random(seed)
```
Then use `self._rng.random()` instead of `random.random()`.

---

### P0-3: Dual Type Systems — Will Break Integration

**Files:** `agent.py` vs `autopredict/core/types.py`

Two incompatible type systems exist:

| Concept | `agent.py` (backtest) | `core/types.py` (adapters) |
|---|---|---|
| Market state | `MarketState(market_id, market_prob, fair_prob, time_to_expiry_hours, order_book)` | `MarketState(market_id, question, market_prob, expiry, category, best_bid, best_ask, ...)` — frozen, no `fair_prob`, no `OrderBook` |
| Order | `ProposedOrder(market_id, side: str, ...)` | `Order(market_id, side: OrderSide, order_type: OrderType, ...)` — uses enums, frozen |
| Execution report | `market_env.ExecutionReport` | `core/types.ExecutionReport` — completely different fields |

**Impact:** The Polymarket adapter (`autopredict/markets/polymarket.py`) imports from `core/types`. The backtest loop (`run_experiment.py`) imports from `agent.py` and `market_env.py`. These types are **not interchangeable**:
- `core.types.MarketState` has no `fair_prob` field (required for trading decisions)
- `core.types.MarketState` has no `order_book: OrderBook` (uses flat `best_bid`/`best_ask` instead)
- `core.types.MarketState` is `frozen=True` while `agent.MarketState` is mutable
- Side is `str` in agent vs `OrderSide` enum in core types

Connecting the Polymarket adapter to the backtest engine will require a translation layer or type unification.

**Fix:** Unify types. Recommended approach: extend `agent.MarketState` with the fields needed by adapters (question, expiry, category), make the adapter convert venue responses to this unified type, and delete `core/types.MarketState`.

---

### P0-4: Brier Score Measures Dataset Quality, Not Agent Quality

**Files:** `run_experiment.py:78`, `market_env.py:595-607`

The backtest loop records `ForecastRecord(probability=fair_prob, outcome=outcome)` where `fair_prob` comes directly from the dataset. The agent does NOT generate this probability — it receives it as input.

```python
# run_experiment.py line 78
forecasts.append(ForecastRecord(market_id=market_id, probability=fair_prob, outcome=outcome))
```

**Impact:** Brier score in the composite metric is a constant for a given dataset. It will never change regardless of agent configuration or code changes. Including it in the ratchet metric (at 25% weight!) adds noise that dilutes signal from the metrics the agent actually controls (Sharpe, PnL, fill rate, drawdown).

**For autoresearch:** This doesn't *corrupt* the ratchet (since it's constant across experiments), but it wastes 25% of the composite score on a fixed value, reducing sensitivity to real improvements.

**For production:** The agent must generate its own `fair_prob` (via LLM or statistical model). This is the fundamental architectural gap — AutoPredict optimizes execution but has no forecasting capability.

**Fix for autoresearch:** Either remove Brier from the composite score and redistribute weight, or (better) acknowledge it as a dataset quality metric and only include it when comparing across datasets.

---

## P1 — Blocks Production Deployment

### P1-1: Polymarket Adapter Is Entirely Placeholder

**File:** `autopredict/markets/polymarket.py`

- `get_markets()` returns `[]`
- `get_market()` returns `None`
- `place_order()` raises `NotImplementedError`
- `get_position()` returns `0.0`
- `get_balance()` returns `0.0`
- `_convert_market()` uses placeholder bid/ask: `market_prob ± 0.01`
- 8 `TODO` comments
- Does NOT import `py_clob_client` (commented out)

**Impact:** No live trading is possible on Polymarket.

---

### P1-2: No Kalshi Adapter Exists

**File:** `autopredict/markets/` contains only `base.py`, `manifold.py`, `polymarket.py`

No `kalshi.py` exists. Kalshi uses Ed25519 auth (fundamentally different from Polymarket's EIP-712), REST at `trading-api.kalshi.com`, and integer cent pricing (not 0-1 probability floats).

---

### P1-3: No WebSocket Support

No file in the repository implements WebSocket connections. Production Polymarket requires WebSocket for real-time order book updates (`wss://ws-subscriptions-clob.polymarket.com/ws/market`). Without this, the agent cannot react to book changes in real time.

---

### P1-4: No Rate Limiting or HTTP Client Infrastructure

No HTTP client code implements backoff, retry, or request queuing. Polymarket uses Cloudflare throttling that delays (not rejects) requests. Without backoff logic, the adapter will hang on throttled requests.

---

### P1-5: Kill Switch Is Not Thread-Safe

**File:** `autopredict/live/trader.py:408-423`

`kill_switch()` sets `self.is_active = False`. While `place_order()` checks `self.is_active` at entry (line 373), there's no locking. If a concurrent execution is already past the check and inside `venue_adapter.submit_order()`, the kill switch won't stop it.

**Note:** Current code is single-threaded, so this is theoretical. Flag for production.

---

### P1-6: No Partial Fill Rollback in LiveTrader

**File:** `autopredict/live/trader.py:381-406`

If `venue_adapter.submit_order()` raises after a partial fill on the venue, the exception propagates but there's no position reconciliation. The error is logged but the actual venue position is unknown.

---

### P1-7: Position Sizing Is Not Kelly

**File:** `agent.py:222-271`

`calculate_trade_size()` uses linear scaling: `bankroll * max_risk_fraction * min(edge / min_edge, 2.5)`. The Kelly criterion for binary markets is:

```
f* = (p * b - q) / b
where p = fair_prob, b = (1/market_prob) - 1, q = 1 - p
```

The linear proxy overallocates when edge is large relative to odds and underallocates when odds are extreme. At `market_prob = 0.90`, a 5% edge justifies much less Kelly sizing than at `market_prob = 0.50` (because the cost of being wrong is 9x the potential gain).

**Impact:** The agent's sizing doesn't account for asymmetric payoffs in binary markets. This could lead to excessive risk at extreme probabilities.

---

## P2 — Should Fix But Can Work Around

### P2-1: Symmetric Edge Threshold

**File:** `agent.py:418-419`

```python
edge = market.fair_prob - market.market_prob
abs_edge = abs(edge)
```

The agent uses `abs_edge >= min_edge` for all gating decisions. But a 5% edge at `market_prob = 0.10` (potential 10x payout) is much more valuable than a 5% edge at `market_prob = 0.90` (potential 1.1x payout). The threshold should arguably be tighter at extreme probabilities.

---

### P2-2: No Input Validation in `_build_order_book()`

**File:** `run_experiment.py:17-23`

`_build_order_book()` does not validate:
- Prices are in (0, 1) range
- Sizes are positive
- Bids are sorted descending / asks ascending (though `OrderBook.__post_init__` sorts them)
- Required fields exist (will raise `KeyError` on missing `market_id`, `order_book`)

The `OrderBook.__post_init__()` does sort bids/asks, so ordering is handled. But price/size validation is absent — negative sizes or prices outside (0,1) would silently corrupt results.

---

### P2-3: Order Book Simulation Assumes All Liquidity Is Real

**File:** `market_env.py:159-221`

`walk_book()` consumes all visible depth at face value. In production:
- **Hidden liquidity** (iceberg orders) means more depth than visible
- **Phantom liquidity** (orders pulled on approach) means less depth than visible
- Queue position for limit orders is not modeled — fill rate uses a flat probability model

The fill rate model (`BASE_FILL_RATE = 0.15`, max `0.75`) is deterministic but not empirically calibrated against any real exchange data.

---

### P2-4: `LiveTrader` Logs Sensitive Information to stdout

**File:** `autopredict/live/trader.py:379`

```python
print(f"[LIVE] Submitting {order.side} order: {order.market_id} size={order.size} type={order.order_type}")
```

Order details are printed to stdout. While this doesn't leak keys, in a production deployment these could leak to container logs, CI outputs, or shared terminals. Should use a proper logger with configurable levels.

---

### P2-5: Dependencies Not Pinned

**File:** `pyproject.toml`

Core dependencies: none (stdlib only — good). Dev dependencies use floor pins (`pytest>=7.0`, `black>=22.0`, `mypy>=0.990`). No lock file exists. Production deployment should pin exact versions.

`py-clob-client` is mentioned in comments but not listed as a dependency.

---

### P2-6: Backtest Engine Duplication

**Files:** `run_experiment.py` vs `autopredict/backtest/engine.py`

Two backtest engines exist. `run_experiment.py` is the authoritative one used by the CLI. `autopredict/backtest/engine.py` is a separate implementation. Any changes to one must be mirrored in the other, or (better) one should be deleted.

---

### P2-7: `VenueConfig` Can Serialize Secrets to YAML in Plaintext

**File:** `autopredict/config/loader.py:293-308`, `autopredict/config/schema.py:176-177`

`VenueConfig` has `api_key` and `api_secret` fields. The loader supports `${ENV_VAR}` substitution, but `save_config()` serializes the resolved (substituted) values back to YAML in plaintext. If a user loads, modifies, and saves a config, their secrets are written to disk.

---

### P2-8: `KeyboardInterrupt` During Live Trading Leaves Positions Open

**File:** `autopredict/scripts/run_live.py:281-283`

On `Ctrl+C`, the handler prints a warning but does NOT cancel open orders, close positions, or activate the kill switch.

---

### P2-9: `RiskManager.check_order()` Position Size Bug

**File:** `autopredict/live/risk.py:170-180`

Position size check calculates `new_position = current + order.size` regardless of buy/sell. Sell orders that reduce an existing long are treated as increasing position, potentially blocking risk-reducing trades.

---

### P2-10: Backtest Engine Duplication with Divergent Imports

**Files:** `run_experiment.py` vs `autopredict/backtest/engine.py`

`autopredict/backtest/engine.py` has a `sys.path` hack importing directly from root `agent` and `market_env`, while `run_experiment.py` uses relative imports. `BacktestConfig.random_seed` exists but is never used. `PositionState.add_position` has a logic bug on line 123.

---

## P3 — Nice to Have

### P3-1: Manifold Adapter Is Placeholder

**File:** `autopredict/markets/manifold.py` — same state as Polymarket adapter.

### P3-2: Grid Search Tuner Uses Exhaustive Search

**File:** `autopredict/learning/tuner.py` — no Bayesian optimization, random search, or early stopping.

### P3-3: `config.json` at Repo Root Contains No Secrets

Verified: `config.json` only has paths and flags. No API keys, private keys, or credentials. `.gitignore` properly excludes `.env`, `*_secret.yaml`, `*_secrets.yaml`, `api_keys.yaml`.

### P3-4: Test Suite Does Not Seed Random

**File:** `tests/conftest.py` — no `random.seed()` call. Tests using `PaperTrader` are non-deterministic. All 189 current tests pass, but `test_trader.py::TestPaperTrader::test_limit_order_*` tests could flake.

---

## Prerequisite Fixes for Autoresearch Loop

The following must be resolved before beginning Phase 2:

| # | Fix | Severity | Files |
|---|---|---|---|
| 1 | Fix Sharpe: remove `sqrt(N)`, use un-annualized `mean/std` | P0-1 | `market_env.py` |
| 2 | Seed `PaperTrader` randomness | P0-2 | `autopredict/live/trader.py` |
| 3 | Implement `calculate_composite_score()` | New | `market_env.py` |
| 4 | Adjust composite score weights (remove or downweight Brier) | P0-4 | New function |
| 5 | Unify type systems (defer to Phase 2 Agent D) | P0-3 | Multiple |

Fix #5 (type unification) can be deferred since the autoresearch loop only uses `agent.py` + `market_env.py` types. The dual type system only matters when connecting adapters.

---

## Architectural Assessment

### What Works
- The core backtest loop (`run_experiment.py` + `market_env.py` + `agent.py`) is clean, deterministic, and functional
- The agent's gating logic (edge, spread, liquidity, depth) is sound in principle
- The execution engine's fill model is deterministic (good for autoresearch)
- The config-driven approach makes the autoresearch loop straightforward
- 189 tests pass, good coverage of core primitives

### What Doesn't Work
- **No forecasting capability.** The agent consumes `fair_prob` as input. In production, someone (human or model) must generate these. This is the binding constraint — execution optimization without forecast generation is optimizing the wrong bottleneck.
- **No live venue connectivity.** All adapters are placeholder. WebSocket, rate limiting, and auth infrastructure are missing.
- **The Sharpe bug would silently corrupt any automated experiment loop.**

### Autoresearch Viability
**The autoresearch loop is viable** after fixes 1-4. The mutable surface (agent.py + strategy_configs) is well-separated from the fixed evaluation layer. The deterministic fill model means experiments are reproducible. The main risk is overfitting to the dataset, which must be mitigated by cross-validation across the 6/100/500-market datasets.

---

## Gate Decision

**Phase 2 may proceed** after committing fixes for P0-1 (Sharpe), P0-2 (seed randomness), P0-4 (composite score adjustment), and implementing the composite score function. P0-3 (type unification) is deferred to Phase 2 Agent D work.
