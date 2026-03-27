# AutoPredict Metrics Reference

Complete guide to interpreting all metrics returned by backtest evaluation.

## Quick Reference Table

| Metric | Type | Unit | Range | Target | Interpretation |
|--------|------|------|-------|--------|-----------------|
| brier_score | epistemic | - | [0, 1] | < 0.20 | Lower = better forecasts |
| sharpe | financial | - | (-∞, ∞) | > 1.0 | Higher = better risk-adjusted returns |
| max_drawdown | financial | $ | [0, ∞) | < 50% | Lower = more stable |
| total_pnl | financial | $ | (-∞, ∞) | positive | Sum of all gains/losses |
| win_rate | financial | pct | [0, 1] | > 50% | Fraction of profitable trades |
| num_trades | financial | count | [0, ∞) | > 30 | More trades = better stats |
| avg_slippage_bps | execution | bp | [0, ∞) | < 20 | Lower = better fills |
| fill_rate | execution | pct | [0, 1] | 0.5-1.0 | Fraction of order size filled |
| market_impact_bps | execution | bp | [0, ∞) | < 50 | How much book moved |
| spread_capture_bps | execution | bp | [0, ∞) | > 0 | Value captured from spread |
| adverse_selection_rate | execution | pct | [0, 1] | < 20% | How often filled on wrong side |
| implementation_shortfall_bps | execution | bp | [0, ∞) | < 30 | Total execution cost |

## Epistemic Metrics

### Brier Score

**Definition**: Mean squared error of probability forecasts.

**Formula**:
```
Brier = mean((forecast_prob - outcome)^2 for all forecasts)
```

**Range**: 0 (perfect) to 1 (worst possible)

**Interpretation**:
- **0.10-0.15**: Excellent (expertly calibrated)
- **0.15-0.20**: Good (competitive)
- **0.20-0.30**: Fair (some skill but room for improvement)
- **0.30-0.50**: Poor (worse than random guessing)
- **0.50**: Useless (no signal, same as random)
- **> 0.50**: Negative skill (consistently wrong)

**Example**:
```
You forecast:  [0.60, 0.70, 0.40, 0.80]
Outcomes:      [1,    1,    0,    0  ]

Errors:        [0.40, 0.30, 0.40, 0.80]
Squared:       [0.16, 0.09, 0.16, 0.64]
Brier = 0.26
```

**Current Performance**:
- Your system: 0.255
- Market prices: 0.315
- You're 19% better than market

**How to Improve**:
- Read CALIBRATION_SUMMARY.md - sports (0.462) and macro (0.292) categories are weak
- Don't trust extreme probabilities (0.05, 0.95) - they're usually overconfident
- Use base rates - don't just react to news
- Get feedback on your forecasts (what actually happens?) and adjust methodology

### Calibration by Bucket

**Definition**: How well-calibrated you are in each probability range.

**Example output**:
```json
"calibration_by_bucket": {
  "0.0-0.1": {
    "count": 3,
    "avg_probability": 0.07,
    "realized_rate": 0.33
  },
  "0.4-0.5": {
    "count": 2,
    "avg_probability": 0.45,
    "realized_rate": 0.50
  }
}
```

**Interpretation**:

For the "0.4-0.5" bucket above:
- You made 2 forecasts in the 40-50% range
- Average of those forecasts: 45%
- Actually occurred: 50% of the time
- **Conclusion**: You're slightly underconfident in this range (said 45%, happened 50%)

**What good calibration looks like**:
```
Bucket      | Avg Forecast | Realized | Status
0.0-0.1     | 8%           | 10%      | ✓ Good
0.1-0.2     | 15%          | 12%      | ✓ Close
0.2-0.3     | 25%          | 28%      | ✓ Good
0.3-0.4     | 35%          | 36%      | ✓ Good
0.4-0.5     | 45%          | 50%      | ~ Slight underconfidence
0.5-0.6     | 55%          | 50%      | ~ Slight overconfidence
0.6-0.7     | 65%          | 63%      | ✓ Good
0.7-0.8     | 75%          | 80%      | ~ Slight underconfidence
0.8-0.9     | 85%          | 82%      | ✓ Close
0.9-1.0     | 95%          | 92%      | ~ Slight overconfidence
```

**Warning signs**:
- Bucket claims 20% but outcome is 80% → massive miscalibration
- All buckets cluster at one outcome → no signal in your forecasts
- Extreme buckets (0.0-0.1, 0.9-1.0) have very different realized rates → overconfidence at extremes

## Financial Metrics

### Sharpe Ratio

**Definition**: Risk-adjusted return. How much return per unit of risk taken.

**Formula**:
```
Sharpe = (mean(pnl_series) / std(pnl_series)) * sqrt(N)
```

Where:
- `pnl_series` = list of P&L from each trade
- `std()` = standard deviation (volatility of returns)
- `sqrt(N)` = scaling factor for number of trades

**Range**: -∞ to +∞ (higher is better)

**Interpretation**:
- **< 0**: Negative returns (losing money)
- **0-0.5**: Weak returns relative to risk
- **0.5-1.0**: Acceptable (beating risk-free rate)
- **1.0-2.0**: Good (professional trader level)
- **2.0-3.0**: Excellent (hedge fund quality)
- **> 3.0**: Exceptional (rare; check for over-fitting)

**Example**:
```
Trades: [+$5, -$2, +$8, -$1, +$4]
Mean PnL: ($5 - $2 + $8 - $1 + $4) / 5 = $2.80
Std Dev: √(variance) = $4.38
Sharpe = ($2.80 / $4.38) * √5 = 1.43
```

**Interpretation**: For every unit of volatility, you make $1.43 of return (decent).

**How to Improve**:
- Increase win_rate (fewer losing trades)
- Increase consistency (reduce volatility)
- Reduce position sizes in losing periods
- Better edge selection (skip low-confidence trades)

### Max Drawdown

**Definition**: Largest peak-to-trough loss.

**Formula**:
```
peak = max cumulative profit so far
running = current cumulative profit
drawdown = peak - running
max_drawdown = max(all drawdowns)
```

**Example**:
```
Cumulative PnL over time:
  $0 → $5 → $3 → $12 → $8 → $9

Drawdowns:
  At $3: peak was $5, so drawdown = $2
  At $8: peak was $12, so drawdown = $4 ← This is max

Max drawdown = $4 (or 33% if starting capital was $12)
```

**Range**: 0 (never went down) to 100% (lost everything)

**Interpretation**:
- **0-20%**: Excellent stability
- **20-40%**: Good (acceptable for growth strategies)
- **40-60%**: Moderate risk
- **60-80%**: High risk (could be tolerable for very high returns)
- **> 80%**: Dangerous (near-bankruptcy territory)

**What it means**:
- Max drawdown of $25 means at worst, you were $25 below your best result
- If you started with $1000, that's a 2.5% loss from peak
- Or if you made $1000 profit then lost $750 of it, that's a 75% drawdown (but from peak, not initial capital)

**How to Improve**:
- Lower `max_risk_fraction` (smaller positions)
- Filter out low-conviction trades
- Stop trading during losing streaks
- Use stop losses

### Total PnL

**Definition**: Sum of all profits and losses.

**Formula**:
```
For each trade:
  if side == "buy":
    pnl = (outcome - fill_price) * filled_size
  else:
    pnl = (fill_price - outcome) * filled_size

total_pnl = sum(all pnls)
```

**Example**:
```
Buy 100 YES at $0.50, outcome YES (1):
  pnl = (1 - 0.50) * 100 = $50

Sell 50 NO at $0.40, outcome NO (0):
  pnl = (0.40 - 0) * 50 = $20

Total PnL = $70
```

**Interpretation**:
- Positive = system makes money
- Negative = system loses money
- Magnitude depends on position sizes

**Caution**: Not scaled by amount of capital risked. A $10 profit on $100 (10% ROI) is different from $10 profit on $1000 (1% ROI). Use Sharpe ratio for risk-adjusted view.

### Win Rate

**Definition**: Fraction of trades with positive PnL.

**Formula**:
```
win_rate = count(pnl > 0) / count(all trades)
```

**Range**: 0 to 1 (or 0% to 100%)

**Interpretation**:
- **< 30%**: Few winners (losing strategy)
- **30-50%**: Below break-even (need very high average gain to profit)
- **50-60%**: Break-even to slight edge
- **60-70%**: Good win rate
- **> 70%**: Excellent (but watch for small-sample luck)

**Example**:
```
5 trades: +$10, -$5, +$2, -$1, +$8
4 winners, 1 loser
win_rate = 4/5 = 80%
```

**Important**: High win rate doesn't mean you make money!

```
100 trades:
  90 winners at +$1 = +$90
  10 losers at -$20 = -$200
  Total PnL = -$110
  Win rate = 90% but you lose money!
```

**How to Improve**:
- Increase edge threshold (only trade high-conviction)
- Better execution (fill at better prices)
- Filter categories with poor calibration

## Execution Metrics

### Average Slippage (in basis points)

**Definition**: How much worse than mid price you filled on average.

**Formula**:
```
For each trade:
  if side == "buy":
    slippage_bps = (fill_price - mid_price) / mid_price * 10000
  else:
    slippage_bps = (mid_price - fill_price) / mid_price * 10000

avg_slippage = mean(absolute value of slippage_bps)
```

**Unit**: Basis points (bps) = 0.01% = 1/10000

**Example**:
```
Mid price: $0.500
You buy at: $0.502
Slippage = (0.502 - 0.500) / 0.500 * 10000 = 40 bps

Mid price: $0.500
You buy at: $0.498
Slippage = (0.498 - 0.500) / 0.500 * 10000 = -40 bps (favorable!)

Average = 40 bps
```

**Range**: 0 to ∞ (higher is worse)

**Interpretation**:
- **0-5 bps**: Excellent (pro-level execution)
- **5-15 bps**: Good (competitive)
- **15-30 bps**: Fair (acceptable but costly)
- **30-50 bps**: Poor (hurts profitability)
- **> 50 bps**: Terrible (trading too aggressively or in thin books)

**What causes high slippage**:
- Market orders in thin order books
- Trading when spread is wide
- Oversized orders that walk the book
- Poor timing (filling at worst possible time)

**How to Improve**:
- Use limit orders (but accept lower fill rate)
- Skip thin markets (`min_book_liquidity` filter)
- Reduce order sizes (`max_depth_fraction`)
- Wait for better execution opportunity

### Fill Rate

**Definition**: Fraction of requested size that actually executed.

**Formula**:
```
fill_rate = filled_size / requested_size
```

**Range**: 0 to 1

**Interpretation**:
- **0 (0%)**: Order didn't execute at all
  - Typical for limit orders in thin books or far from spread
  - Can be acceptable if you wanted high fill certainty
- **0.25-0.5 (25-50%)**: Partial fill
  - Typical for passive limit orders at the spread
  - Balance between not paying spread and actually getting filled
- **0.75-1.0 (75-100%)**: Good fill
  - Typical for market orders
  - Shows liquidity is available

**Market orders**:
```
Requested: 100 units
Depth available: 80 units (at good prices)
                 40 units (further out)
Likely fill: 120-150 units possible (better than requested!)
Expected fill_rate: ~0.90-1.0
```

**Limit orders**:
```
Requested: 100 units
You place at bid (passive)
Typical fill: 20-40 units (people queue ahead)
Expected fill_rate: 0.20-0.40
```

**How to Improve**:
- Market orders: faster fills, higher slippage
- Limit orders: better prices, lower fill rate
- Choose order_type based on how much fill certainty you need

### Spread Capture (in basis points)

**Definition**: How much of the bid-ask spread you captured with passive orders.

**Formula**:
```
For passive limit buy orders:
  spread_capture = (mid_price - fill_price) / mid_price * 10000

For passive limit sell orders:
  spread_capture = (fill_price - mid_price) / mid_price * 10000

Only counted if: order_type == "limit" AND filled_size > 0
```

**Example**:
```
Spread: Bid $0.50, Ask $0.51 (1 bp spread)
Mid: $0.505

You place passive buy limit at $0.50 and it fills:
Spread capture = (0.505 - 0.50) / 0.505 * 10000 = 99 bps
(You captured almost the entire spread!)
```

**Interpretation**:
- **0 bps**: Filled at the mid (no spread captured)
  - Happens when limit crosses and becomes market
- **10-50 bps**: Good spread capture
  - Placed away from touch, got lucky
- **50-100 bps**: Excellent
  - Captured half to full spread
- **> 100 bps**: Exceptional
  - Spread was wide or you placed very aggressively

**How to Improve**:
- Place limit orders inside the spread (not at the touch)
- Accept wider spreads as the cost of passive execution
- Trade only when spreads are narrow

### Market Impact (in basis points)

**Definition**: How much the mid price moved after your trade.

**Formula**:
```
market_impact = abs(mid_after - mid_before) / mid_before * 10000
```

**Example**:
```
Before trade: Bid $0.50, Ask $0.51
You buy 100 units (market order)
After trade:  Bid $0.51, Ask $0.52
Market impact = (0.515 - 0.505) / 0.505 * 10000 ≈ 198 bps
(The market moved 2% due to your order!)
```

**Interpretation**:
- **0-10 bps**: Negligible impact (your trade was small relative to market)
- **10-30 bps**: Reasonable (normal for small orders)
- **30-50 bps**: Noticeable (you moved the market)
- **> 50 bps**: Significant (your order was large or book was thin)

**What it means**:
- High impact = your order is a large fraction of available liquidity
- Problem: Those traders behind you in the book see the price moved and might not fill
- Silver lining: Your trade provided price discovery

**How to Improve**:
- Smaller order sizes
- Trade deeper markets
- Split orders across time

### Adverse Selection Rate

**Definition**: Fraction of passive limit orders that filled on the wrong side of subsequent price movement.

**Formula**:
```
relevant = limit orders that were filled
adverse = count(
  (side == "buy" AND next_mid < fill_price) OR
  (side == "sell" AND next_mid > fill_price)
)
adverse_selection_rate = adverse / len(relevant)
```

**Example**:
```
You place passive buy limit at $0.50, fills
Next mid price: $0.49
You were wrong! You paid too much.
This counts as 1 adverse selection.

You place passive sell limit at $0.60, fills
Next mid price: $0.61
You were wrong! You sold too cheap.
This counts as 1 adverse selection.
```

**Range**: 0 to 1

**Interpretation**:
- **0 (0%)**: Perfect timing (never filled on wrong side)
  - Unlikely, would indicate insider information
- **0.20 (20%)**: Good (only 1 in 5 fills were unlucky)
  - Professional level
- **0.50 (50%)**: Neutral (coin flip)
  - Can still be profitable if your edge > slippage
- **> 0.50**: Poor (more often wrong than right)
  - Either bad market conditions or poor timing

**Why it matters**:
```
You're buying because you think price will go up.
If you fill and price goes down, that's bad timing, not bad forecasting.

Adverse selection = timing risk
Calibration = forecasting risk
```

**How to Improve**:
- Better timing of order placement
- More aggressive execution (market orders) when conviction is high
- Passive orders only when you're less certain

### Implementation Shortfall (in basis points)

**Definition**: Total execution cost = slippage + fees

**Formula**:
```
for market orders:
  implementation_shortfall = slippage + taker_fee_bps

for limit orders:
  implementation_shortfall = slippage + maker_fee_bps
```

In AutoPredict, `taker_fee_bps = 0` and `maker_fee_bps = 0` by default.

So: implementation_shortfall ≈ slippage_bps

**Interpretation**:
- This is the total cost of your execution
- If your edge is 10 bps but implementation shortfall is 15 bps, you lose money
- Need: edge > implementation_shortfall to be profitable

**How to Improve**:
- Same as improving slippage
- Or find venues with lower fees

## Interpreting a Complete Metrics Report

### Example: Good Performance

```json
{
  "brier_score": 0.18,
  "sharpe": 1.45,
  "max_drawdown": 18,
  "total_pnl": 87.50,
  "win_rate": 0.62,
  "num_trades": 45,
  "avg_slippage_bps": 8.2,
  "fill_rate": 0.68,
  "spread_capture_bps": 42,
  "market_impact_bps": 5,
  "adverse_selection_rate": 0.18,
  "implementation_shortfall_bps": 12.1
}
```

**Analysis**:
- ✅ Brier 0.18: Good forecasts
- ✅ Sharpe 1.45: Solid risk-adjusted returns
- ✅ Drawdown 18%: Stable
- ✅ Win rate 62%: Above average
- ✅ Slippage 8 bps: Excellent execution
- ✅ Fill rate 68%: Getting decent fills
- ✅ Adverse selection 18%: Good timing

**Verdict**: This system is working well. Continue iterating on small improvements.

### Example: Poor Performance

```json
{
  "brier_score": 0.38,
  "sharpe": -0.2,
  "max_drawdown": 75,
  "total_pnl": -34.20,
  "win_rate": 0.35,
  "num_trades": 8,
  "avg_slippage_bps": 45,
  "fill_rate": 0.15,
  "spread_capture_bps": 0,
  "market_impact_bps": 120,
  "adverse_selection_rate": 0.62,
  "implementation_shortfall_bps": 52
}
```

**Analysis**:
- ❌ Brier 0.38: Poor forecasts (worse than market)
- ❌ Sharpe -0.2: Losing money
- ❌ Drawdown 75%: Nearly bankrupt
- ❌ Win rate 35%: Few winners
- ❌ Slippage 45 bps: Expensive execution
- ❌ Fill rate 15%: Not filling orders
- ❌ Adverse selection 62%: Terrible timing
- ❌ Market impact 120 bps: Oversized orders

**Diagnose** (from TROUBLESHOOTING.md):
1. Core issue: **Forecasts are bad** (Brier 0.38 >> market 0.315)
   - Read CALIBRATION_SUMMARY.md
   - Fix fair_prob estimation methodology

2. Secondary issue: **Execution is terrible** (slippage 45 bps)
   - Too many market orders in thin books
   - Increase `aggressive_edge` threshold
   - Increase `min_book_liquidity`

3. Tertiary issue: **Position sizing too aggressive** (max_drawdown 75%)
   - Reduce `max_risk_fraction` from 0.02 to 0.01
   - Reduce `max_position_notional`

**Priority order**:
1. Fix forecasts (biggest issue by far)
2. Fix execution (reduce slippage)
3. Fix sizing (reduce risk)

## Recommended Monitoring

Track these numbers after every backtest:

```python
def score_report(metrics):
    print(f"Forecast Quality: {metrics['brier_score']:.3f} (target < 0.20)")
    print(f"Risk-Adjusted Return: {metrics['sharpe']:.2f} (target > 1.0)")
    print(f"Stability: {metrics['max_drawdown']:.0f}% drawdown (target < 50%)")
    print(f"Profitability: ${metrics['total_pnl']:.2f} PnL")
    print(f"Execution: {metrics['avg_slippage_bps']:.1f} bps slippage (target < 20 bps)")
    print(f"Fill Rate: {metrics['fill_rate']:.1%} (target > 50%)")

    # Automated improvement suggestion
    if metrics['avg_slippage_bps'] > 30:
        print("→ High slippage: reduce market orders or filter thin books")
    if metrics['fill_rate'] < 0.3:
        print("→ Low fill rate: use more market orders or place closer to spread")
    if metrics['brier_score'] > 0.25:
        print("→ Poor calibration: improve fair_prob estimation")
```

## Summary

- **Epistemic**: Brier score (forecast accuracy) - read CALIBRATION_SUMMARY.md to improve
- **Financial**: Sharpe, max_drawdown, PnL, win_rate - indicates profitability and risk
- **Execution**: Slippage, fill_rate, market_impact - indicates order type and sizing quality

Optimize in priority order: **Forecasts → Financial metrics → Execution**.

Generally: **Better forecasts >> Better execution >> Better trading parameters**.
