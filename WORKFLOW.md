# AutoPredict Workflow

How to use AutoPredict for iterative agent improvement. This guide walks through the decision loops and improvement patterns.

## Agent Decision Loop

Every market snapshot flows through this sequence:

```
┌─────────────────────────────────────────────────────────┐
│ 1. Normalize Market State                               │
├─────────────────────────────────────────────────────────┤
│ Input: market_prob, fair_prob, order_book, etc.        │
│ Output: MarketState with edge, spread, depth, time     │
│                                                         │
│ Code: agent.evaluate_market() lines 162-170            │
│                                                         │
│ Question: Do we have an edge?                          │
│   edge = |fair_prob - market_prob|                     │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Check Gating Rules                                   │
├─────────────────────────────────────────────────────────┤
│ ✓ edge >= min_edge (0.05)?                             │
│ ✓ liquidity_depth >= min_book_liquidity (60.0)?        │
│ ✓ spread_pct <= max_spread_pct (0.04) OR edge strong? │
│                                                         │
│ Code: agent.evaluate_market() lines 172-177            │
│                                                         │
│ → If any fails: return None (skip market)              │
│                                                         │
│ Question: Should we even consider this trade?          │
└─────────────────────────────────────────────────────────┘
                         │
                         │ Yes, passes gating
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Choose Order Type (Market vs Limit)                  │
├─────────────────────────────────────────────────────────┤
│ Key metric: edge_to_spread_ratio = edge / spread       │
│                                                         │
│ Rules (ExecutionStrategy.decide_order_type):           │
│                                                         │
│ IF edge >= aggressive_edge (0.12) AND                  │
│    edge_to_spread_ratio >= 3.0                         │
│   → Use MARKET order (pay spread, get certainty)       │
│                                                         │
│ ELSE IF time_to_expiry <= 12h AND                      │
│    edge >= aggressive_edge * 0.75                      │
│   → Use MARKET order (time pressure)                   │
│                                                         │
│ ELSE IF spread_pct >= 0.05 AND                         │
│    depth < 100                                         │
│   → Use LIMIT order (avoid thin market slippage)       │
│                                                         │
│ ELSE                                                   │
│   → Use LIMIT order (default to passive)               │
│                                                         │
│ Code: ExecutionStrategy.decide_order_type()            │
│                                                         │
│ Question: How urgently do we need execution?           │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 4. Calculate Position Size                              │
├─────────────────────────────────────────────────────────┤
│ Three constraints:                                       │
│                                                         │
│ 1) Edge scaling                                         │
│    strong_edge = min(edge / min_edge, 2.5) = 1.0-2.5x │
│                                                         │
│ 2) Risk limit                                           │
│    max_loss = bankroll * max_risk_fraction (0.02)      │
│    position_size_cap = max_loss * edge_scale           │
│                                                         │
│ 3) Depth limit                                          │
│    don't take more than max_depth_fraction (0.15)      │
│    of visible depth per trade                          │
│                                                         │
│ Code: ExecutionStrategy.calculate_trade_size()         │
│                                                         │
│ Question: How much should we risk on this edge?        │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 5. Check Order Splitting                                │
├─────────────────────────────────────────────────────────┤
│ IF desired_size > available_depth * 0.25               │
│   → Split into 3 equal slices                          │
│                                                         │
│ Code: ExecutionStrategy.should_split_order()           │
│       ExecutionStrategy.split_order()                  │
│                                                         │
│ Question: Is this order too large for one slice?       │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 6. Execute Trades                                       │
├─────────────────────────────────────────────────────────┤
│ For each order slice:                                   │
│                                                         │
│ IF market order:                                        │
│   → Execute immediately at best available price        │
│   → Walk book, consume liquidity                        │
│   → Expected fill rate: 80-100%                        │
│                                                         │
│ IF limit order:                                        │
│   → Place at limit price (at spread or inside)         │
│   → Simulate queue position, partial fill              │
│   → Expected fill rate: 15-75% (depends on price)      │
│                                                         │
│ Code: ExecutionEngine.execute_market_order()           │
│       ExecutionEngine.execute_limit_order()            │
│                                                         │
│ Question: How much actually gets filled?               │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 7. Record Metrics                                       │
├─────────────────────────────────────────────────────────┤
│ For each filled trade:                                  │
│   - filled_size, fill_price, slippage_bps              │
│   - market_impact_bps, fill_rate                       │
│   - realized_pnl (based on actual outcome)             │
│   - implementation_shortfall (slippage + fees)         │
│                                                         │
│ Code: ExecutionEngine._build_report()                  │
│       run_experiment.py lines 107-124                  │
│                                                         │
│ Question: How did we actually perform?                 │
└─────────────────────────────────────────────────────────┘
```

## Improvement Loop

After a backtest run, AutoPredict identifies weaknesses and suggests improvements:

```
┌──────────────────────────────────────────────────────────┐
│ Analyze Metrics Snapshot                                 │
├──────────────────────────────────────────────────────────┤
│ Calculate:                                               │
│   - avg_slippage_bps (execution cost)                   │
│   - fill_rate (passive order success)                   │
│   - brier_score (forecast accuracy)                     │
│   - max_drawdown (largest loss)                         │
│                                                          │
│ Code: agent.analyze_performance()                       │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
         ┌─────────────────────────────────────┐
         │ Which metric is worst?              │
         └─────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┬─────────────┬──────────────┐
          │                │                │             │              │
          ▼                ▼                ▼             ▼              ▼
    ┌─────────┐      ┌──────────┐    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ Slippage│      │Fill Rate │    │ Brier    │  │Max Drawd │  │Selection │
    │> 15 bps │      │< 35%     │    │> 0.20    │  │> 75%     │  │Too Much  │
    └─────────┘      └──────────┘    └──────────┘  └──────────┘  └──────────┘
    │                │                │             │              │
    ▼                ▼                ▼             ▼              ▼
    Too much      Passive       Forecasts     Taking too   Trading low
    market        orders not    too confident  much risk    quality edges
    order use     filling
         │                │                │             │              │
         └────────────────┴────────────────┴─────────────┴──────────────┘
                           │
                           ▼
         ┌──────────────────────────────────┐
         │ Suggest Improvement               │
         │ "Focus next iteration on X"       │
         │ "Hypothesis: try Y"               │
         └──────────────────────────────────┘
                           │
                           ▼
         ┌──────────────────────────────────┐
         │ Manual Improvement Workflow       │
         │ (see below)                       │
         └──────────────────────────────────┘
```

## Manual Improvement Workflow

### Weakness: High Slippage

**Diagnosis**: You're using market orders too aggressively.

**Root causes to check**:
1. `aggressive_edge` threshold too low (catching weak edges)
2. `min_book_liquidity` too low (trading thin books)
3. Time pressure logic too eager (edge_to_spread_ratio check weak)

**Fixes**:

Option 1: Raise aggressive edge threshold
```json
{
  "aggressive_edge": 0.15  // was 0.12
}
```

Option 2: Better liquidity filtering
```json
{
  "min_book_liquidity": 100.0  // was 60.0
}
```

Option 3: Stricter edge-to-spread logic in `decide_order_type()`
```python
if edge >= aggressive_edge and edge_to_spread_ratio >= 4.0:  # was 3.0
    return "market"
```

### Weakness: Low Fill Rate

**Diagnosis**: Passive limit orders aren't executing.

**Root causes to check**:
1. Limit prices too far from touch (not competitive)
2. Orders too small (queued behind larger sizes)
3. Spread too wide for passive strategy to work

**Fixes**:

Option 1: Improve limit price (place at top of spread)
```python
# In execute_market(), for limit orders:
limit_price = book.bids[0].price if side == "buy" else book.asks[0].price
# This places you at the best bid/ask, competitive
```

Option 2: Larger limit order sizes
```json
{
  "max_risk_fraction": 0.03  // was 0.02
}
```

Option 3: More market orders (sacrifice spread for fills)
```json
{
  "aggressive_edge": 0.08  // was 0.12, triggers market orders sooner
}
```

### Weakness: Poor Calibration

**Diagnosis**: Forecasts are overconfident.

**Root causes to check**:
1. Fair_prob estimates too extreme (0.05, 0.95)
2. Category-specific biases (see CALIBRATION_SUMMARY.md)
3. Not incorporating base rates

**Fixes**:

Option 1: Read CALIBRATION_SUMMARY.md
- Sports category is weak (0.462 Brier) - needs better methodology
- Macro category shows bias - check base rates
- Crypto volatility not accounted for

Option 2: Use validation.py to flag low-quality estimates
```python
from validation import FairProbValidator

validator = FairProbValidator()
warnings = validator.validate(fair_prob=0.75, market_prob=0.60, category="sports")
# Returns warnings like "sports has poor calibration history"
```

Option 3: Shrink toward market in weak categories
```python
if category in ("sports", "macro"):
    fair_prob = 0.5 * fair_prob + 0.5 * market_prob  # Blend
```

### Weakness: High Max Drawdown

**Diagnosis**: Position sizing is too aggressive relative to edge quality.

**Root causes to check**:
1. `max_risk_fraction` too high (2% is standard)
2. Consecutive losses (bad luck or bad model)
3. Trading same direction repeatedly (correlated errors)

**Fixes**:

Option 1: Lower max risk fraction
```json
{
  "max_risk_fraction": 0.01  // was 0.02
}
```

Option 2: Lower max position notional
```json
{
  "max_position_notional": 15.0  // was 25.0
}
```

Option 3: Filter low-confidence markets
```json
{
  "min_edge": 0.08  // was 0.05 - only high conviction trades
}
```

### Weakness: Too Much Selection Churn

**Diagnosis**: Trading too many low-quality edges, costs exceed edge.

**Root causes to check**:
1. `min_edge` threshold too low (catching noise)
2. Slippage + fees exceeding edge value
3. Overtrading when uncertain

**Fixes**:

Option 1: Raise minimum edge
```json
{
  "min_edge": 0.08  // was 0.05
}
```

Option 2: Increase filter thresholds
```json
{
  "min_book_liquidity": 120.0,  // was 60.0
  "max_spread_pct": 0.02         // was 0.04
}
```

Option 3: Use limit orders only to reduce costs
```json
{
  "aggressive_edge": 0.30  // never use market orders
}
```

## Autonomous vs Manual Workflows

### Autonomous Workflow (Using propose_improvement)

```python
# After running a backtest
metrics = run_backtest(...)

# Get automatic suggestion
agent = AutoPredictAgent()
suggestion = agent.propose_improvement(
    current_config=config,
    metrics=metrics,
    guidance=guidance_text
)

print(suggestion)
# → {"summary": "Focus on execution_quality",
#    "hypothesis": "Use passive orders more selectively"}
```

**Limitations**:
- Only identifies the single weakest metric
- Doesn't know domain context (is Sharpe 0.8 good?)
- Can't reason about trade-offs
- No feedback loop yet

**Use case**: Quick first pass when uncertain where to start.

### Manual Workflow (Domain Expert Loop)

```
1. Run backtest
   python -m autopredict.cli backtest

2. Analyze metrics manually
   - Is Sharpe acceptable? (> 1.0?)
   - Is fill rate reasonable? (> 50% for limit?)
   - Is Brier score improving? (< 0.20 target?)
   - Which metric caused biggest loss?

3. Read TROUBLESHOOTING.md or METRICS.md
   - Understand what the weak metric indicates
   - Find the "Fixes" section for that weakness

4. Edit config or code
   - Change strategy_configs/baseline.json OR
   - Modify ExecutionStrategy methods in agent.py

5. Run backtest again
   - Verify improvement
   - Check for regressions in other metrics

6. Commit findings
   - Document what you changed and why
   - Save your config variant
```

**Advantages**:
- Full understanding of trade-offs
- Can incorporate domain knowledge
- Faster convergence with expertise
- Build system intuition

**Recommended**: Use manual workflow with periodic autonomous suggestions.

## Example: Complete Improvement Cycle

### Run 1: Baseline

```bash
python -m autopredict.cli backtest
# Output:
# {
#   "sharpe": 0.8,
#   "brier_score": 0.28,
#   "max_drawdown": 45,
#   "avg_slippage_bps": 22,
#   "fill_rate": 0.45
# }
```

**Assessment**: Slippage is high (22 bps), fill rate low (0.45).

### Run 2: Experiment - More Passive

Edit `strategy_configs/baseline.json`:
```json
{
  "aggressive_edge": 0.20,  // was 0.12 - use market orders less
  "max_spread_pct": 0.03    // was 0.04 - filter wide spreads
}
```

```bash
python -m autopredict.cli backtest
# Output:
# {
#   "sharpe": 1.2,
#   "brier_score": 0.28,
#   "max_drawdown": 35,
#   "avg_slippage_bps": 8,   // improved!
#   "fill_rate": 0.32         // got worse :(
# }
```

**Result**: Slippage dropped from 22→8 bps (good!) but fill rate dropped 45→32% (bad).

### Run 3: Experiment - Hybrid

Find the sweet spot - trade better execution quality for some fill rate loss:

```json
{
  "aggressive_edge": 0.15,  // compromise between 0.12 and 0.20
  "max_spread_pct": 0.035   // compromise between 0.04 and 0.03
}
```

```bash
python -m autopredict.cli backtest
# Output:
# {
#   "sharpe": 1.15,
#   "brier_score": 0.28,
#   "max_drawdown": 38,
#   "avg_slippage_bps": 14,  // still better than baseline
#   "fill_rate": 0.40        // better than Run 2
# }
```

**Result**: Good balance. Slippage down 22→14 bps, fill rate only down 45→40.

### Run 4: Improve Forecasts (Longer Term)

File issue: "Sports category Brier is 0.46, need better estimation methodology"

Reference CALIBRATION_SUMMARY.md → sports category overestimates favorites.

Document in strategy.md:
```markdown
## Current research
- Sports forecasts too confident (0.46 Brier)
- Suspect overestimating favorites
- Next: Build base-rate adjusted model for sports
```

This becomes a separate project thread.

## Tips & Best Practices

### General

1. **Change one thing at a time**: Don't modify multiple config params in one run. You won't know which change helped.

2. **Look at statistical significance**: With only 6 sample markets, a 0.02 Sharpe change might just be luck. Aim for bigger moves (2-4x) for confidence.

3. **Document your experiments**: Track which config version produced what metrics. Create new files:
   - `strategy_configs/v2_more_passive.json`
   - `strategy_configs/v3_tighter_edge.json`

4. **Preserve the baseline**: Keep `baseline.json` as reference. Branch from it.

5. **Test on real data eventually**: Sample markets are useful for testing logic, but backtest on actual market data before deploying.

### Debugging

1. **Read agent.py line by line**: Understand the decision sequence.

2. **Print intermediate values**: Add debugging to agent.evaluate_market():
   ```python
   print(f"Market {market.market_id}: edge={edge}, spread_pct={spread_pct}, order_type={order_type}")
   ```

3. **Check gating rules first**: Most "no orders executed" issues are due to not passing gating rules (edge too small, liquidity too thin).

4. **Validate order book**:
   ```python
   print(order_book.get_spread())
   print(order_book.get_total_depth("buy"))
   ```

5. **Simulate execution manually**: Take one problematic market, step through execute_market_order() or execute_limit_order() by hand.

### Reporting

When you find a good improvement:

```markdown
## Improvement: [Name]

**Hypothesis**: [What you think is wrong]

**Change**: Modified [config param or code logic]

**Results**:
- Sharpe: 0.8 → 1.2 (+50%)
- Slippage: 22 → 14 bps (-36%)
- Fill rate: 45% → 40% (-5%)

**Trade-off**: Accepting 5% fill rate loss to save 8 bps slippage (net positive)

**Next**: [What to try next]
```

## Summary

AutoPredict's iterative loop:

1. **Normalize** market state
2. **Check** gating rules
3. **Decide** order type and size
4. **Execute** trades
5. **Measure** epistemic, financial, execution metrics
6. **Analyze** which metric is weakest
7. **Improve** that metric via config or code changes
8. **Repeat**

The workflow supports both:
- **Quick automated suggestions** for when you're stuck
- **Deep manual analysis** when you have domain expertise

Use both to accelerate improvement.
