# AutoPredict Troubleshooting

Common issues and solutions.

## Installation & Setup

### "ModuleNotFoundError: No module named 'autopredict'"

**Cause**: Python can't find the package.

**Solution**:
```bash
# Make sure you're in the right directory
cd /Users/howdymary/Documents/New\ project/autopredict

# Run with module syntax
python -m autopredict.cli backtest

# Or add to PYTHONPATH
export PYTHONPATH="/Users/howdymary/Documents/New project/autopredict:$PYTHONPATH"
python -c "import autopredict"
```

### "No metrics.json found under state directory"

**Cause**: You've never run a backtest, so `state/backtests/` is empty.

**Solution**:
```bash
# Run a backtest first
python -m autopredict.cli backtest

# Then check the latest
python -m autopredict.cli score-latest
```

### JSON decode error when running backtest

**Cause**: Your config or dataset JSON is malformed.

**Solution**:
```bash
# Validate JSON syntax
python -c "
import json
with open('strategy_configs/baseline.json') as f:
    config = json.load(f)
    print('Config valid:', config.keys())
"

# Check for common issues:
# - Missing commas between fields
# - Trailing commas (invalid in JSON)
# - Single quotes instead of double quotes
```

## Execution Issues

### No orders executed (empty metrics)

**Symptoms**:
```json
{
  "num_trades": 0,
  "total_pnl": 0,
  "sharpe": 0,
  "win_rate": 0
}
```

**Cause**: Agent rejected all markets at the gating stage.

**Debug Steps**:

1. Check edge is present in dataset:
```python
import json
with open('datasets/sample_markets.json') as f:
    data = json.load(f)
    for market in data:
        edge = market['fair_prob'] - market['market_prob']
        print(f"{market['market_id']}: edge={edge:.3f}")
```

2. Compare with your thresholds:
```json
{
  "min_edge": 0.05
}
```

If all edges < 0.05, increase `min_edge`:

```json
{
  "min_edge": 0.02
}
```

3. Check liquidity:
```python
for market in data:
    book = market['order_book']
    total_depth = sum(s for p, s in book.get('bids', [])) + sum(s for p, s in book.get('asks', []))
    print(f"{market['market_id']}: depth={total_depth}")
```

If all < min_book_liquidity threshold, lower it:

```json
{
  "min_book_liquidity": 30.0  // was 60.0
}
```

4. Add debug output to agent.py:
```python
def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
    edge = market.fair_prob - market.market_prob
    abs_edge = abs(edge)

    # Add this debug line
    print(f"DEBUG: {market.market_id} edge={abs_edge:.3f} vs min={self.config.min_edge}")

    if abs_edge < self.config.min_edge:
        print(f"  → REJECTED: edge too small")
        return None
```

### Orders executed but all limit orders fill at 0%

**Cause**: Limit order prices are not competitive (too far from spread).

**Solution**:

Check how limit prices are set in run_experiment.py:
```python
limit_price = best_bid if side == "buy" else best_ask
```

This should place you AT the touch. If still not filling:

1. Orders may be too small (queued behind larger orders)
2. Spread may be too wide (10%+ is unrealistic)
3. Time frame may be too short to accumulate fills

Try:
```json
{
  "max_risk_fraction": 0.03  // bigger orders
}
```

Or switch to more market orders:
```json
{
  "aggressive_edge": 0.08  // lower threshold to use market orders
}
```

### All orders are market orders (high slippage)

**Cause**: Your edge is usually > aggressive_edge threshold.

**Solution**:

Increase aggressive_edge to use limit orders more:
```json
{
  "aggressive_edge": 0.15  // was 0.12
}
```

Or check your fair_prob estimates - if they're consistently > 15% away from market_prob, you might be overconfident. See CALIBRATION_SUMMARY.md.

## Metric Anomalies

### Fill rate > 100%

**This is impossible.** Indicates a bug in execution simulation.

**Check**: In ExecutionEngine._build_report(), ensure:
```python
fill_rate = (filled_size / requested_size) if requested_size > 0 else 0.0
assert 0.0 <= fill_rate <= 1.0
```

### Slippage is negative

**Meaning**: You filled BETTER than mid price (good!).

**Example**:
- Mid price: $0.50
- You buy at: $0.48
- Slippage: -200 bps (captured 200 bps of value!)

This happens with limit orders that cross the spread. It's excellent execution.

### Brier score = 0.5

**Cause**: All forecasts are 50/50 (no edge).

**Solution**:

Check your fair_prob values in the dataset:
```python
for market in data:
    if market['fair_prob'] == 0.5:
        print(f"WARNING: {market['market_id']} has no signal")
```

Add real forecasts with genuine edges.

### Sharpe = 0

**Cause**: Either 0 trades or 0 variance in PnL.

**Solution**:
- If 0 trades: See "No orders executed" section above
- If low variance: All trades are small winners/losers. Trade larger sizes:

```json
{
  "max_risk_fraction": 0.03  // was 0.02
}
```

### Max drawdown = 0

**Meaning**: Never had a drawdown (peak never declined).

**Interpretation**:
- Could mean no losing trades (lucky or small sample size)
- Could mean trades are all winners in sequence
- With N=6 markets, not statistically meaningful

Collect more trades (100+) before worrying.

### Calibration bucket has 0% realized_rate but forecast prob = 0.6

**Cause**: Small sample size. One market contradicts the bucket.

**Solution**:

With only 6 markets, calibration analysis is not reliable. See CALIBRATION_SUMMARY.md for guidance on how to get to 100+ markets.

## Logic Issues

### Agent keeps missing profitable trades

**Cause**: Gating rules too strict.

**Debug**:

Add logging to agent.evaluate_market():
```python
def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
    edge = market.fair_prob - market.market_prob
    abs_edge = abs(edge)
    book = market.order_book
    mid = book.get_mid_price()
    spread_pct = book.get_spread() / max(mid, 1e-9)
    liquidity_depth = book.get_total_depth("buy") if edge > 0 else book.get_total_depth("sell")

    # Log each gating rule
    print(f"Market: {market.market_id}")
    print(f"  edge={abs_edge:.3f} vs min={self.config.min_edge} → {abs_edge >= self.config.min_edge}")
    print(f"  depth={liquidity_depth:.1f} vs min={self.config.min_book_liquidity} → {liquidity_depth >= self.config.min_book_liquidity}")
    print(f"  spread={spread_pct:.4f} vs max={self.config.max_spread_pct} → {spread_pct <= self.config.max_spread_pct}")

    # ... rest of function
```

Then identify which rule is rejecting the trade. Loosen it:
```json
{
  "min_edge": 0.02,
  "min_book_liquidity": 30,
  "max_spread_pct": 0.06
}
```

### Position sizes are too small / too large

**Check sizing logic**:

```python
edge_scale = min(max(edge / max(config.min_edge, 1e-9), 1.0), 2.5)
# If edge = 0.05 and min_edge = 0.05: scale = 1.0
# If edge = 0.10 and min_edge = 0.05: scale = 2.0
# If edge = 1.00 and min_edge = 0.05: scale = 2.5 (capped)

bankroll_cap = bankroll * config.max_risk_fraction * edge_scale
# If bankroll = 1000, max_risk = 0.02, scale = 1.0: cap = $20

depth_cap = liquidity_depth * config.max_depth_fraction
# If depth = 100, max_depth_fraction = 0.15: cap = $15

final_size = min(bankroll_cap, depth_cap, config.max_position_notional)
```

If sizes are too small:
- Increase `max_risk_fraction` (0.02 → 0.03)
- Increase `max_position_notional` ($25 → $50)
- Increase `max_depth_fraction` (0.15 → 0.25)

If sizes are too large:
- Decrease any of the above
- Or increase `min_edge` to only trade high-conviction

### Order splitting not working

**Expected behavior**: If size > 25% of depth, split into 3 slices.

**Debug**:

Add logging:
```python
if self.execution.should_split_order(size, book, self.config):
    split_sizes = self.execution.split_order(size)
    print(f"Splitting {size:.2f} into {split_sizes}")
else:
    print(f"Not splitting {size:.2f} (depth={book.get_total_depth('buy')})")
```

If splitting not triggering:
- Check `split_threshold_fraction`: is it reasonable? (0.25 = 25%)
- Verify book depth is calculated correctly

## Performance Issues

### Backtest takes too long

**Cause**: Dataset is large or you're debugging with prints.

**Solution**:

Remove debug print statements from agent.py and market_env.py.

Optimize if needed:
```python
# Instead of this (slow):
for market in dataset:
    # ... complex logic ...

# Do this (faster):
# Pre-filter markets
valid_markets = [m for m in dataset if should_consider(m)]
for market in valid_markets:
    # ... only process relevant ones ...
```

### Memory usage is high

**Cause**: Keeping all trade records in memory.

**Solution**: Not relevant for small backtests (6 markets). Only matters for 100k+ trades.

## Validation Issues

### Validation.py warnings on every market

**These are informational.** The validator (validation.py) warns about:
- Poor quality categories (sports, macro, crypto)
- Extreme probabilities (< 0.05 or > 0.95)
- Inconsistency with market price

**What to do**:

1. Read the warning
2. Decide if it's valid (is it a weak category? should it be?)
3. Either improve the forecast or accept the warning

Warnings are not errors - they don't block trades.

## Common Pitfalls

### "My edge is 20% but agent doesn't trade"

**Cause**: Spread is wider than your edge, or liquidity is too thin.

**Check**:
```python
edge = 0.20
spread = 0.25  # 25% spread!
# Spread > edge, so you'll lose money immediately
```

Solution: Don't trade wide spread markets. Increase `max_spread_pct` threshold cautiously, or increase `min_edge`:

```json
{
  "min_edge": 0.30  // only trade if edge > spread
}
```

### "I got good PnL but slippage is terrible"

**Cause**: Slippage calculation includes favorable fills.

**Reality check**:
- Your market order bought at $0.52 (vs mid $0.50)
- Slippage = +200 bps (favorable!)
- But market moved against you (filled right before a drop)
- You had good execution, bad luck on edge direction

Both can be true.

### "Fill rate is 0% but total_pnl > 0"

**Cause**: This is impossible. If nothing filled, PnL must be 0.

**Solution**: Bug in metrics calculation. Verify:
```python
for trade in trades:
    assert trade.filled_size > 0, "No fill but in trade record!"
```

## Validation Checklist

Before deploying an agent:

1. **Config is valid JSON**
   ```bash
   python -c "import json; json.load(open('strategy_configs/your_config.json'))"
   ```

2. **Dataset has market_prob and fair_prob with edges**
   ```python
   import json
   with open('datasets/your_dataset.json') as f:
       data = json.load(f)
       assert all('fair_prob' in m for m in data)
       assert all('market_prob' in m for m in data)
       assert any(abs(m['fair_prob'] - m['market_prob']) > 0.01 for m in data)
   ```

3. **Order book has bids and asks**
   ```python
   assert all('order_book' in m for m in data)
   assert all(m['order_book']['bids'] for m in data)  # has bids
   assert all(m['order_book']['asks'] for m in data)  # has asks
   ```

4. **Backtest produces metrics with no NaN or infinity**
   ```python
   import json
   metrics = json.load(open('state/backtests/[latest]/metrics.json'))
   assert all(v is not None for v in metrics.values())
   assert all(not math.isnan(v) if isinstance(v, float) else True for v in metrics.values())
   ```

5. **Metrics are in reasonable ranges**
   ```python
   assert 0 <= metrics['fill_rate'] <= 1
   assert 0 <= metrics['brier_score'] <= 1
   assert 0 <= metrics['win_rate'] <= 1
   ```

6. **Agent provides feedback**
   ```python
   assert 'weakness' in metrics['agent_feedback']
   assert 'hypothesis' in metrics['agent_feedback']
   ```

## Getting Help

### Read the docs

- **ARCHITECTURE.md**: Understand component design
- **WORKFLOW.md**: Follow the decision loop step-by-step
- **METRICS.md**: Understand each metric deeply
- **CALIBRATION_SUMMARY.md**: Fix forecast quality issues

### Enable debug mode

Add this to agent.py:
```python
import sys

class AutoPredictAgent:
    def __init__(self, config=None, debug=False):
        self.config = config or AgentConfig()
        self.execution = ExecutionStrategy()
        self.debug = debug

    def evaluate_market(self, market, bankroll):
        edge = market.fair_prob - market.market_prob
        if self.debug:
            print(f"[DEBUG] {market.market_id}: fair={market.fair_prob}, market={market.market_prob}, edge={edge}")
        # ... rest ...
```

Then create a debug script:
```python
from agent import AutoPredictAgent
from run_experiment import run_backtest

# Monkey-patch for debugging
original_evaluate = AutoPredictAgent.evaluate_market
def debug_evaluate(self, market, bankroll):
    print(f"Evaluating {market.market_id}...")
    return original_evaluate(self, market, bankroll)

AutoPredictAgent.evaluate_market = debug_evaluate

metrics = run_backtest(
    config_path="strategy_configs/baseline.json",
    dataset_path="datasets/sample_markets.json"
)
```

### Check recent changes

If something broke:
```bash
git log --oneline | head -5
git diff HEAD~1
```

Or check what changed in agent.py:
```python
import inspect
print(inspect.getsource(AutoPredictAgent.evaluate_market))
```

## Summary

Most issues fall into these categories:

| Issue | Cause | Fix |
|-------|-------|-----|
| No trades | Gating rules too strict | Lower min_edge, min_liquidity |
| Low fill rate | Limit prices not competitive | Use more market orders |
| High slippage | Market orders on thin books | Use more limit orders |
| Poor Brier | Forecasts overconfident | Read CALIBRATION_SUMMARY.md |
| High drawdown | Position sizing too large | Lower max_risk_fraction |
| All metrics 0 | No trades executed | See "No trades" row above |

When stuck: Run the **Validation Checklist** above, then enable **debug mode** and trace through one problematic market step-by-step.
