# Backtest Engine Documentation

Comprehensive guide to the AutoPredict backtesting framework for prediction market strategies.

## Overview

The AutoPredict backtesting framework provides production-quality infrastructure for evaluating trading strategies on historical prediction market data.

### Key Features

- **Prediction Market Specific**: Tailored metrics (calibration, Brier score, edge realization)
- **Realistic Execution**: Order book simulation with slippage and market impact
- **Comprehensive Metrics**: Financial, execution, and epistemic analysis
- **Performance Attribution**: By market, time, and liquidity regime
- **Walk-Forward Testing**: Prevent overfitting with proper train/test splits
- **Position Tracking**: Monitor exposure and enforce position limits

## Quick Start

### Installation

The backtest module is part of the autopredict package:

```python
from autopredict.backtest.engine import BacktestEngine, BacktestConfig, load_snapshots_from_json
from autopredict.backtest.analysis import PerformanceAnalyzer
from autopredict.agent import AutoPredictAgent, AgentConfig
```

### Running Your First Backtest

```python
# 1. Load market data
snapshots = load_snapshots_from_json("datasets/sample_markets_100.json")

# 2. Initialize strategy
strategy = AutoPredictAgent(
    config=AgentConfig(min_edge=0.05, aggressive_edge=0.12)
)

# 3. Configure backtest
config = BacktestConfig(starting_bankroll=1000.0)

# 4. Run backtest
engine = BacktestEngine(config=config, strategy=strategy)
result = engine.run(snapshots)

# 5. Analyze results
analyzer = PerformanceAnalyzer()
report = analyzer.analyze(
    forecasts=result.forecasts,
    trades=result.trades,
    starting_bankroll=result.starting_bankroll,
    ending_bankroll=result.ending_bankroll,
)

# 6. View summary
report.print_summary()

# 7. Save results
result.save("results/backtest.json")
report.save("results/report.json")
```

### Command Line

```bash
# Run example backtest
python examples/backtest_mispriced_prob.py

# With options
python examples/backtest_mispriced_prob.py \
  --data datasets/sample_markets_500.json \
  --config strategy_configs/aggressive.json \
  --out results/ \
  --bankroll 5000 \
  --verbose
```

## Data Format

### Market Snapshot Structure

```json
[
  {
    "market_id": "politics-2025-03",
    "timestamp": 1234567890.0,
    "market_prob": 0.45,
    "fair_prob": 0.55,
    "time_to_expiry_hours": 24.0,
    "order_book": {
      "bids": [[0.44, 100], [0.43, 50]],
      "asks": [[0.46, 75], [0.47, 25]]
    },
    "outcome": 1,
    "next_mid_price": 0.46,
    "metadata": {"category": "politics", "tag": "election"}
  }
]
```

### Field Descriptions

- `market_id`: Unique identifier
- `timestamp`: Unix timestamp or sequence number
- `market_prob`: Current market price (0-1)
- `fair_prob`: Strategy's fair value estimate (0-1)
- `time_to_expiry_hours`: Time until resolution
- `order_book`: Current order book with bids/asks
- `outcome`: Eventual outcome (0 or 1)
- `next_mid_price`: Mid at next snapshot (for adverse selection analysis)
- `metadata`: Additional context (category, tags, etc.)

## Configuration

### BacktestConfig

```python
config = BacktestConfig(
    # Capital
    starting_bankroll=1000.0,

    # Fees (basis points)
    maker_fee_bps=0.0,  # Passive/limit orders
    taker_fee_bps=0.0,  # Aggressive/market orders

    # Walk-forward testing
    enable_walk_forward=False,
    walk_forward_window=100,

    # Monte Carlo simulation
    monte_carlo_runs=0,
    random_seed=None,

    # Position management
    enable_position_tracking=True,
    max_concurrent_positions=0,  # 0 = unlimited

    # Debugging
    enable_detailed_logging=False,
)
```

## Results

### BacktestResult

```python
result = engine.run(snapshots)

# Summary stats
result.total_pnl          # Total profit/loss
result.num_trades         # Number of trades executed
result.num_markets_seen   # Number of markets evaluated
result.starting_bankroll  # Initial capital
result.ending_bankroll    # Final capital

# Detailed data
result.forecasts          # List[ForecastRecord]
result.trades             # List[TradeRecord]
result.metrics            # Dict of all metrics
result.position_history   # Position tracking data
result.decision_log       # Decision log (if enabled)

# Save
result.save("results/backtest.json")
```

### Performance Report

```python
report = analyzer.analyze(...)

# Organized metrics
report.financial_metrics   # PnL, Sharpe, win rate
report.execution_metrics   # Slippage, fills, impact
report.epistemic_metrics   # Calibration, Brier score
report.risk_metrics        # Drawdown, volatility
report.attribution         # By market, time, liquidity

# Display
report.print_summary()

# Save
report.save("results/report.json")
```

## Metrics

### Financial Metrics

- `total_pnl`: Total profit/loss
- `num_trades`: Number of trades
- `win_rate`: Percentage of profitable trades
- `sharpe_ratio`: Risk-adjusted return
- `return_pct`: ROI as percentage

### Execution Metrics

- `avg_slippage_bps`: Average slippage
- `avg_market_impact_bps`: Price impact
- `avg_fill_rate`: Fill rate for limit orders
- `edge_capture_rate`: % of theoretical edge captured
- `execution_cost_bps`: Total execution costs

### Epistemic Metrics

- `brier_score`: Mean squared error of probabilities
- `calibration_error`: Forecast accuracy
- `reliability`: Calibration component
- `resolution`: Discrimination component
- `hit_rate_by_confidence`: Win rate by confidence level

### Risk Metrics

- `max_drawdown`: Peak-to-trough decline
- `max_drawdown_pct`: Drawdown as % of peak
- `pnl_volatility`: Return standard deviation
- `downside_volatility`: Negative return volatility
- `sortino_ratio`: Downside risk-adjusted return

## Analysis

### Calibration Analysis

```python
from autopredict.backtest.metrics import PredictionMarketMetrics

calibration = PredictionMarketMetrics.calculate_calibration(forecasts)

# Overall quality
print(f"Brier score: {calibration.overall_brier:.4f}")
print(f"Mean calibration error: {calibration.mean_absolute_calibration_error:.4f}")

# By bucket
for bucket in calibration.buckets:
    print(f"{bucket.range_str}: predicted {bucket.avg_probability:.2%}, "
          f"realized {bucket.realized_rate:.2%}")

# Brier decomposition
decomp = calibration.brier_decomposition
print(f"Reliability: {decomp.reliability:.4f} (should be low)")
print(f"Resolution: {decomp.resolution:.4f} (should be high)")
```

### Market Attribution

```python
from autopredict.backtest.metrics import PredictionMarketMetrics

attribution = PredictionMarketMetrics.calculate_market_attribution(trades)

# Sort by profitability
sorted_markets = sorted(attribution.items(), key=lambda x: x[1]["total_pnl"], reverse=True)

for market_id, stats in sorted_markets[:10]:
    print(f"{market_id}: ${stats['total_pnl']:.2f} "
          f"({stats['num_trades']:.0f} trades, {stats['win_rate']:.1%} win rate)")
```

### Liquidity Regime Analysis

```python
liquidity_analysis = PredictionMarketMetrics.calculate_liquidity_regime_analysis(trades)

print("Thin markets:")
print(f"  Trades: {liquidity_analysis.thin_markets['num_trades']}")
print(f"  PnL: ${liquidity_analysis.thin_markets['total_pnl']:.2f}")
print(f"  Win rate: {liquidity_analysis.thin_markets['win_rate']:.2%}")

print("\nThick markets:")
print(f"  Trades: {liquidity_analysis.thick_markets['num_trades']}")
print(f"  PnL: ${liquidity_analysis.thick_markets['total_pnl']:.2f}")
print(f"  Win rate: {liquidity_analysis.thick_markets['win_rate']:.2%}")
```

## Examples

### Example 1: Basic Backtest

See `examples/backtest_mispriced_prob.py` for complete example.

### Example 2: Parameter Sweep

```python
results = []

for min_edge in [0.03, 0.05, 0.07, 0.10]:
    for aggressive_edge in [0.10, 0.12, 0.15]:
        if aggressive_edge <= min_edge:
            continue

        strategy = AutoPredictAgent(
            config=AgentConfig(min_edge=min_edge, aggressive_edge=aggressive_edge)
        )

        engine = BacktestEngine(config=BacktestConfig(starting_bankroll=1000.0), strategy=strategy)
        result = engine.run(snapshots)

        results.append({
            "min_edge": min_edge,
            "aggressive_edge": aggressive_edge,
            "pnl": result.total_pnl,
            "trades": result.num_trades,
        })

best = max(results, key=lambda x: x["pnl"])
print(f"Best: min_edge={best['min_edge']}, aggressive_edge={best['aggressive_edge']}, PnL=${best['pnl']:.2f}")
```

### Example 3: Custom Strategy

```python
class ConservativeStrategy:
    def evaluate_market(self, market, bankroll):
        edge = abs(market.fair_prob - market.market_prob)
        if edge < 0.15:  # Only huge edges
            return None

        side = "buy" if market.fair_prob > market.market_prob else "sell"
        size = min(20.0, bankroll * 0.02)

        return ProposedOrder(
            market_id=market.market_id,
            side=side,
            order_type="market",
            size=size,
            limit_price=None,
            rationale=f"huge_edge={edge:.2f}"
        )

strategy = ConservativeStrategy()
result = engine.run(snapshots)
```

## Best Practices

### 1. Always Check Calibration

```python
calibration = PredictionMarketMetrics.calculate_calibration(result.forecasts)
if calibration.overall_brier > 0.20:
    print("WARNING: Poor calibration - fix forecasts first!")
```

### 2. Test Out-of-Sample

```python
# 70/30 train/test split
split_idx = int(len(snapshots) * 0.7)
train_data = snapshots[:split_idx]
test_data = snapshots[split_idx:]

# Validate on unseen data
train_result = engine.run(train_data)
test_result = engine.run(test_data)

print(f"Train PnL: ${train_result.total_pnl:.2f}")
print(f"Test PnL: ${test_result.total_pnl:.2f}")
```

### 3. Monitor Multiple Metrics

```python
# Don't optimize PnL alone
checks = [
    ("Sharpe > 1.0", report.financial_metrics["sharpe_ratio"] > 1.0),
    ("Drawdown < 15%", report.risk_metrics["max_drawdown_pct"] < 15),
    ("Calibration good", report.epistemic_metrics["calibration_analysis"]["overall_brier"] < 0.15),
    ("Edge capture > 70%", report.execution_metrics["edge_capture_rate"] > 0.7),
]

for name, passed in checks:
    status = "✅" if passed else "❌"
    print(f"{status} {name}")
```

### 4. Save All Artifacts

```python
# Save everything for reproducibility
result.save("results/backtest_result.json")
report.save("results/performance_report.json")

import json
with open("results/config.json", "w") as f:
    json.dump({
        "strategy_config": strategy.config.__dict__,
        "backtest_config": config.__dict__,
    }, f, indent=2)
```

## Troubleshooting

### No Trades Executed

**Symptom**: `result.num_trades == 0`

**Solutions**:
- Lower `min_edge` threshold
- Increase `max_spread_pct`
- Check `fair_prob` differs from `market_prob`
- Verify order book has liquidity

### Poor Calibration

**Symptom**: High Brier score

**Solutions**:
- Review `fair_prob` calculation
- Check for systematic bias
- Simplify forecasting model
- Validate against outcomes

### High Slippage

**Symptom**: `avg_slippage_bps > 20`

**Solutions**:
- Use more limit orders
- Reduce position sizes
- Avoid thin markets
- Improve price placement

### Low Fill Rate

**Symptom**: `avg_fill_rate < 0.4`

**Solutions**:
- Increase `limit_price_improvement_ticks`
- Use market orders for strong edges
- Accept that passive strategy = lower fills

## API Reference

### BacktestEngine

```python
class BacktestEngine:
    def __init__(self, config: BacktestConfig, strategy: StrategyProtocol):
        """Initialize backtest engine."""

    def run(self, snapshots: list[MarketSnapshot]) -> BacktestResult:
        """Run backtest over market snapshots."""
```

### PerformanceAnalyzer

```python
class PerformanceAnalyzer:
    def analyze(
        self,
        forecasts: list[ForecastRecord],
        trades: list[TradeRecord],
        starting_bankroll: float,
        ending_bankroll: float,
    ) -> PerformanceReport:
        """Generate comprehensive performance report."""
```

### PredictionMarketMetrics

```python
class PredictionMarketMetrics:
    @staticmethod
    def calculate_calibration(
        forecasts: list[ForecastRecord],
        num_buckets: int = 10
    ) -> CalibrationAnalysis:
        """Calculate calibration with Brier decomposition."""

    @staticmethod
    def calculate_market_attribution(
        trades: list[TradeRecord]
    ) -> dict[str, dict[str, float]]:
        """Calculate per-market profit attribution."""

    @staticmethod
    def calculate_liquidity_regime_analysis(
        trades: list[TradeRecord],
        threshold: float = 100.0
    ) -> LiquidityRegimeAnalysis:
        """Analyze performance by liquidity regime."""

    @staticmethod
    def calculate_edge_realization(
        trades: list[TradeRecord]
    ) -> dict[str, float]:
        """Calculate edge capture metrics."""
```

## Further Reading

- **METRICS.md**: Detailed metric definitions
- **ARCHITECTURE.md**: System design
- **EVALUATION.md**: Evaluation framework
- **examples/**: Working code examples

---

For questions or issues, consult the main documentation or open an issue on GitHub.
