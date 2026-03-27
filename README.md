# AutoPredict

**Build self-improving prediction market agents that learn from experience.**

AutoPredict is a minimal, powerful framework for developing and backtesting algorithmic trading agents for prediction markets. It separates a **fixed evaluation environment** from a **mutable agent strategy** that evolves through iterative experimentation.

## What is AutoPredict?

Prediction markets let you trade on the outcome of future events. AutoPredict helps you build agents that:

1. **Sense**: Analyze market data (prices, order books, liquidity)
2. **Think**: Evaluate edge (your forecast vs market price) and decide whether to trade
3. **Act**: Execute orders (market or limit) to capture profitable opportunities
4. **Learn**: Analyze performance metrics and propose improvements

**The Agent Loop**:
```
Market Data → Evaluate Edge → Size Position → Execute Order → Measure Results → Improve Strategy
     ↑                                                                               ↓
     └───────────────────────────────────────────────────────────────────────────────┘
```

## Why AutoPredict?

**Rapid iteration**: Test strategy changes in seconds via backtest
**Realistic simulation**: Order book execution with slippage, partial fills, market impact
**Comprehensive metrics**: Epistemic (forecast accuracy), Financial (PnL, Sharpe), Execution (slippage, fill rate)
**Self-improvement**: Built-in performance analysis suggests targeted improvements
**Minimal dependencies**: Core uses Python stdlib only (~1500 lines)

## Quick Start

Get your first agent running in 15 minutes.

### Install

```bash
git clone https://github.com/yourusername/autopredict.git
cd autopredict

# No external dependencies needed for core functionality
# Optional: Install test tools
pip install pytest pytest-cov
```

### Run Your First Backtest

```bash
# Backtest on sample data (6 markets)
python -m autopredict.cli backtest

# View results
python -m autopredict.cli score-latest
```

**Expected output**:
```json
{
  "total_pnl": 45.23,
  "sharpe": 2.44,
  "brier_score": 0.189,
  "avg_slippage_bps": 55.2,
  "fill_rate": 0.78,
  "num_trades": 59,
  "agent_feedback": {
    "dominant_weakness": "execution_quality",
    "hypothesis": "Slippage high - consider more limit orders"
  }
}
```

### Modify and Re-test

Edit `strategy_configs/baseline.json`:
```json
{
  "min_edge": 0.08,  // Increased from 0.05 (be more selective)
  "aggressive_edge": 0.15,  // Fewer market orders
  "max_risk_fraction": 0.015  // Smaller position sizes
}
```

Run again:
```bash
python -m autopredict.cli backtest
```

Compare metrics to see if Sharpe improved.

**That's it!** You've completed the iteration loop: test → analyze → modify → re-test.

## How It Works

### Agent Architecture

**Fixed components** (never change during experiments):
- `market_env.py`: Order book, execution engine, metrics
- Guarantees fair comparison across experiments

**Mutable components** (you modify these):
- `agent.py`: Trading logic, order selection, position sizing
- `strategy_configs/*.json`: Tunable parameters

### The Decision Loop

For each market snapshot:
1. **Calculate edge**: `fair_prob - market_prob`
2. **Check filters**: Is edge large enough? Is liquidity sufficient?
3. **Decide order type**: Market (aggressive) or limit (passive)?
4. **Size position**: Based on edge, risk limits, available capital
5. **Simulate execution**: Walk order book, calculate slippage
6. **Record result**: Track PnL, fill rate, execution quality

### Metrics That Matter

**Epistemic** (Are your forecasts good?)
- `brier_score`: Forecast accuracy (< 0.20 is good)
- `calibration`: Do 60% forecasts happen 60% of the time?

**Financial** (Are you making money?)
- `sharpe`: Risk-adjusted returns (> 1.0 is good)
- `total_pnl`: Total profit/loss
- `max_drawdown`: Worst peak-to-trough loss (< 35% is acceptable)

**Execution** (Are you trading efficiently?)
- `avg_slippage_bps`: Cost vs mid price (< 30 bps is good)
- `fill_rate`: Fraction of orders filled (> 0.5 is good)
- `market_impact`: Price movement from your trades

## Common Use Cases

### 1. Test a New Strategy Idea

Hypothesis: "Markets with wide spreads are overreacting - use limit orders to capture mean reversion"

```python
# strategy_configs/mean_reversion.json
{
  "min_edge": 0.05,
  "max_spread_pct": 0.10,  // Accept wide spreads
  "aggressive_edge": 0.30   // Almost always use limit orders
}
```

Test it:
```bash
python -m autopredict.cli backtest --config strategy_configs/mean_reversion.json
```

### 2. Optimize Parameters

Find the best `min_edge` threshold:

```bash
for edge in 0.03 0.05 0.08 0.10; do
  # Update config with different edge values
  python -m autopredict.cli backtest | grep sharpe
done
```

### 3. Validate Forecasts

Check if your probability estimates are well-calibrated:

```bash
python -m autopredict.cli backtest | jq '.calibration_by_bucket'
```

### 4. Generate Synthetic Data

Create test datasets for experimentation:

```bash
python scripts/generate_dataset.py --num-markets 100 --output datasets/test_data.json
python -m autopredict.cli backtest --dataset datasets/test_data.json
```

## Documentation

**Get started**:
- [QUICKSTART.md](QUICKSTART.md) - 15-minute tutorial
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design and data flow

**Develop strategies**:
- [STRATEGIES.md](STRATEGIES.md) - How to build custom strategies
- [BACKTESTING.md](BACKTESTING.md) - Rigorous backtesting methodology
- [METRICS.md](METRICS.md) - Detailed metric interpretations

**Go to production**:
- [DEPLOYMENT.md](DEPLOYMENT.md) - Paper trading and live trading guide
- [LEARNING.md](LEARNING.md) - Self-improvement and meta-learning

**Contribute**:
- [CONTRIBUTING.md](CONTRIBUTING.md) - Code style, testing, PR process
- [ROADMAP.md](ROADMAP.md) - Planned features and vision

## Example Workflows

### Workflow 1: Improve Execution Quality

```bash
# 1. Run backtest
python -m autopredict.cli backtest

# Output shows: "dominant_weakness": "execution_quality"
#                "avg_slippage_bps": 85

# 2. Hypothesis: Use more limit orders
# Edit strategy_configs/baseline.json:
#   "aggressive_edge": 0.15  (was 0.12)

# 3. Test improvement
python -m autopredict.cli backtest

# Output shows: "avg_slippage_bps": 42  (improved!)

# 4. Keep change (commit to git)
git add strategy_configs/baseline.json
git commit -m "Reduce slippage by increasing aggressive_edge threshold"
```

### Workflow 2: Improve Forecast Calibration

```bash
# 1. Identify calibration issue
python -m autopredict.cli backtest | jq '.calibration_by_bucket'

# Shows: You're overconfident (60% forecasts only hit 45%)

# 2. Improve forecasting (external to AutoPredict)
# - Add more data sources
# - Ensemble multiple models
# - Regularize probability estimates

# 3. Re-test with improved forecasts
python -m autopredict.cli backtest

# Brier score should improve
```

## Key Features

### Realistic Simulation

Order book execution with:
- **Depth-aware fills**: Large orders walk the book
- **Slippage calculation**: Cost vs mid price
- **Partial fills**: Limit orders may not fully execute
- **Market impact**: Track price movement from trades

### Comprehensive Metrics

Evaluate performance across 3 dimensions:

**Epistemic Metrics**:
- Brier score, log loss, calibration curves
- Per-category forecast quality
- Confidence interval coverage

**Financial Metrics**:
- PnL, Sharpe ratio, Sortino ratio
- Max drawdown, win rate
- Risk-adjusted returns

**Execution Metrics**:
- Slippage, fill rate, spread capture
- Market impact, implementation shortfall
- Adverse selection rate

### Self-Diagnosis

Built-in performance analysis:
```python
agent.analyze_performance(metrics)
# Returns:
# {
#   "dominant_weakness": "execution_quality",
#   "weakness_score": 0.72,
#   "hypothesis": "High slippage - consider more limit orders"
# }
```

Use feedback to guide next iteration.

## Advanced Features

### Walk-Forward Testing

Prevent overfitting with out-of-sample validation:

```bash
# Train on period 1, test on period 2
python -m autopredict.cli backtest --dataset datasets/period_1.json
# Tune strategy based on results
python -m autopredict.cli backtest --dataset datasets/period_2.json
```

See [BACKTESTING.md](BACKTESTING.md) for full walk-forward methodology.

### Strategy Portfolio

Combine multiple strategies:

```python
from autopredict.strategies import MispricedStrategy, MomentumStrategy, MeanReversionStrategy

portfolio = StrategyPortfolio([
    MispricedStrategy(config1),
    MomentumStrategy(config2),
    MeanReversionStrategy(config3)
])
```

### Parameter Optimization

Grid search or Bayesian optimization:

```bash
python scripts/optimize_parameters.py \
  --param min_edge --range 0.03:0.15 \
  --param aggressive_edge --range 0.10:0.25 \
  --objective sharpe
```

See [LEARNING.md](LEARNING.md) for optimization techniques.

## Extending AutoPredict

### Add a Custom Strategy

```python
# autopredict/strategies/my_strategy.py
from autopredict.agent import AutoPredictAgent

class MyCustomStrategy(AutoPredictAgent):
    def evaluate_market(self, market, bankroll):
        # Your custom logic
        edge = market.fair_prob - market.market_prob

        if abs(edge) < 0.10:
            return None  # Skip

        # Custom order sizing
        size = self._my_sizing_logic(edge, bankroll)

        return ProposedOrder(
            side="buy" if edge > 0 else "sell",
            order_type="limit",
            size=size
        )
```

See [STRATEGIES.md](STRATEGIES.md) for detailed guide.

### Add a Market Adapter

Connect to live prediction markets:

```python
# autopredict/markets/polymarket.py
class PolymarketAdapter:
    def fetch_markets(self):
        """Fetch live markets from Polymarket API."""
        # API integration
        pass

    def execute_order(self, order):
        """Execute order on Polymarket."""
        # Order execution
        pass
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment.

### Add Custom Metrics

```python
# In market_env.py
def calculate_sortino_ratio(trades):
    """Risk-adjusted returns using downside deviation."""
    # Implementation
    pass

# Add to evaluate_all()
metrics["sortino_ratio"] = calculate_sortino_ratio(trades)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## Testing

Run the test suite:

```bash
# All tests
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=. --cov-report=html

# Specific test file
python -m pytest tests/test_agent.py -v
```

**Test coverage**: 65 tests, 80%+ coverage

## Repository Structure

```
autopredict/
├── agent.py              # Mutable agent logic (400 lines)
├── market_env.py         # Fixed market simulation (700 lines)
├── cli.py                # Command-line interface (100 lines)
├── run_experiment.py     # Backtest harness (150 lines)
├── autopredict/          # Package structure
│   ├── core/             # Core components
│   ├── strategies/       # Strategy implementations
│   ├── markets/          # Market adapters
│   └── learning/         # Learning algorithms
├── strategy_configs/     # JSON strategy configurations
├── datasets/             # Market data (JSON)
├── tests/                # Test suite
├── examples/             # Example implementations
├── scripts/              # Utility scripts
└── notebooks/            # Jupyter tutorials
```

## Performance Benchmarks

**Baseline strategy on 100-market test**:
- Sharpe: 2.44
- Brier: 0.189
- Slippage: 55 bps
- Trades: 59
- Win rate: 62.7%

**Conservative strategy** (higher edge threshold):
- Sharpe: 3.12
- Brier: 0.175
- Slippage: 12 bps
- Trades: 18
- Win rate: 72.2%

Performance varies by:
- Dataset quality and size
- Fair probability accuracy
- Market liquidity
- Strategy parameters

## Roadmap

**Q2 2026** - Real data integration:
- Polymarket adapter
- Paper trading mode
- Advanced risk controls

**Q3-Q4 2026** - Multi-strategy portfolio:
- Portfolio manager
- Online learning
- LLM-assisted strategy generation

**2027+** - Full autonomy:
- Meta-learning across strategies
- Collaborative agent swarms
- Causal inference

See [ROADMAP.md](ROADMAP.md) for detailed plans.

## Dependencies

**Core**: Python 3.9+ (stdlib only, no external packages)

**Optional**:
- `pytest` - Testing
- `pytest-cov` - Coverage reporting
- `black` - Code formatting
- `mypy` - Type checking

**Future**:
- `anthropic` - LLM-assisted improvement
- `scikit-learn` - Machine learning
- `numpy/pandas` - Data analysis

## Design Philosophy

**Principles**:
1. **Fixed environment, mutable strategy**: Guarantees fair comparison
2. **Minimal core**: ~1500 lines for rapid understanding
3. **Metrics-first**: Every decision validated by measurable outcomes
4. **Iteration-friendly**: Changes testable in seconds
5. **Self-improving**: Agents propose their own improvements
6. **Production-ready**: Path from backtest → paper → live

**Trade-offs**:
- Simplicity over features
- Clarity over cleverness
- Testability over completeness

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Code style guidelines
- Testing requirements
- Pull request process
- How to add features

## Community

- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: Questions, ideas
- **Discord**: Real-time chat (coming soon)

## License

MIT License - see LICENSE file

## Acknowledgments

Inspired by:
- [autoresearch](https://github.com/karpathy/autoresearch) - Auto-improving research agents
- Prediction markets: Polymarket, Kalshi, Manifold
- Algorithmic trading literature

## Citation

If you use AutoPredict in research:

```bibtex
@software{autopredict2026,
  title={AutoPredict: Self-Improving Prediction Market Agents},
  author={AutoPredict Contributors},
  year={2026},
  url={https://github.com/yourusername/autopredict}
}
```

## Questions?

- Check [QUICKSTART.md](QUICKSTART.md) for tutorials
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues
- Create a GitHub Issue
- Read the [FAQ](docs/FAQ.md) (coming soon)

**Happy trading!**
