# Self-Improvement Guide

Guide to building self-improving prediction market agents using AutoPredict's learning loop.

## Table of Contents

1. [Overview](#overview)
2. [The Learning Loop](#the-learning-loop)
3. [Analyzing Performance](#analyzing-performance)
4. [Strategy Tuning](#strategy-tuning)
5. [Adding Learning Algorithms](#adding-learning-algorithms)
6. [Meta-Learning](#meta-learning)
7. [Online Learning](#online-learning)

## Overview

AutoPredict is designed for **iterative self-improvement**: agents propose changes, test them via backtest, and keep improvements. This guide explains how to build agents that learn from experience.

### Self-Improvement Philosophy

**Human-in-the-loop**: Agents propose improvements, humans approve

**Metrics-driven**: Every change is validated via backtest metrics

**Version controlled**: Track what works via git commits

**Incremental**: Small changes compound over time

### Learning vs Optimization

**Learning**: Agent discovers patterns in performance data and proposes targeted improvements

**Optimization**: Brute-force search over parameter space

AutoPredict supports both:
- **Learning**: `agent.analyze_performance()` identifies weaknesses and suggests fixes
- **Optimization**: Grid search, Bayesian optimization (see below)

## The Learning Loop

The core learning loop:

```
1. Run backtest
2. Analyze metrics
3. Identify dominant weakness
4. Propose hypothesis
5. Implement change
6. Test via backtest
7. Keep if better, revert if worse
8. Repeat
```

### Implemented Learning Loop

AutoPredict agents have built-in performance analysis:

```python
# agent.py
class AutoPredictAgent:
    def analyze_performance(self, metrics: dict) -> dict:
        """Identify dominant weakness and propose improvement."""

        # Identify weakness
        weakness_type, weakness_score = self._identify_weakness(metrics)

        # Propose hypothesis
        hypothesis = self._generate_hypothesis(weakness_type, metrics)

        return {
            "weakness": weakness_type,
            "hypothesis": hypothesis
        }
```

### Weakness Types

Agents identify these weakness categories:

1. **execution_quality**: High slippage or low fill rate
2. **limit_fill_quality**: Passive orders not filling or adversely selected
3. **calibration**: Forecasts poorly calibrated (high Brier score)
4. **risk**: Position sizing causing large drawdowns
5. **selection**: Trading low-quality edges

### Example Learning Iteration

**Iteration 1: Baseline**

```bash
python -m autopredict.cli backtest
```

**Output**:
```json
{
  "sharpe": 1.23,
  "brier_score": 0.255,
  "avg_slippage_bps": 85.3,
  "fill_rate": 0.42,
  "agent_feedback": {
    "weakness": "execution_quality",
    "hypothesis": "High slippage - consider using more limit orders"
  }
}
```

**Iteration 2: Fix Execution**

Based on hypothesis, adjust config:

```json
{
  "aggressive_edge": 0.15,  // Increased from 0.12 (fewer market orders)
  "max_spread_pct": 0.05    // Increased from 0.04 (accept wider spreads for limit orders)
}
```

**Backtest again**:
```bash
python -m autopredict.cli backtest --config strategy_configs/improved_execution.json
```

**Output**:
```json
{
  "sharpe": 1.67,  // Improved from 1.23
  "brier_score": 0.255,  // Unchanged (expected)
  "avg_slippage_bps": 42.1,  // Improved from 85.3
  "fill_rate": 0.58,  // Improved from 0.42
  "agent_feedback": {
    "weakness": "calibration",  // New weakness revealed
    "hypothesis": "Brier score mediocre - improve probability estimates"
  }
}
```

**Result**: Keep this change (better Sharpe, better slippage). Move to next weakness.

**Iteration 3: Fix Calibration**

Improve fair probability estimates (external to AutoPredict):
- Add more data sources
- Use statistical models
- Ensemble multiple forecasts

Backtest with improved forecasts → continue iterating.

## Analyzing Performance

Deep-dive performance analysis to guide improvements.

### Trade-Level Analysis

Analyze individual trades to find patterns:

```python
# analysis/trade_analysis.py
import json
from collections import defaultdict

def analyze_trades(backtest_dir: str):
    """Analyze trade-level patterns."""

    # Load trades
    with open(f"{backtest_dir}/trades.json") as f:
        trades = json.load(f)

    # Group by outcome
    winners = [t for t in trades if t["pnl"] > 0]
    losers = [t for t in trades if t["pnl"] <= 0]

    print(f"Winners: {len(winners)}, Losers: {len(losers)}")

    # Analyze winners
    print("\nWinner characteristics:")
    print(f"  Avg edge: {sum(t['edge'] for t in winners) / len(winners):.3f}")
    print(f"  Avg size: {sum(t['size'] for t in winners) / len(winners):.2f}")
    print(f"  Avg slippage: {sum(t['slippage_bps'] for t in winners) / len(winners):.1f} bps")

    # Analyze losers
    print("\nLoser characteristics:")
    print(f"  Avg edge: {sum(t['edge'] for t in losers) / len(losers):.3f}")
    print(f"  Avg size: {sum(t['size'] for t in losers) / len(losers):.2f}")
    print(f"  Avg slippage: {sum(t['slippage_bps'] for t in losers) / len(losers):.1f} bps")

    # Find patterns
    # Example: Do limit orders perform better than market orders?
    limit_trades = [t for t in trades if t["order_type"] == "limit"]
    market_trades = [t for t in trades if t["order_type"] == "market"]

    limit_win_rate = sum(1 for t in limit_trades if t["pnl"] > 0) / len(limit_trades)
    market_win_rate = sum(1 for t in market_trades if t["pnl"] > 0) / len(market_trades)

    print(f"\nOrder type performance:")
    print(f"  Limit orders: {limit_win_rate:.1%} win rate")
    print(f"  Market orders: {market_win_rate:.1%} win rate")
```

### Category Analysis

Analyze performance by market category:

```python
def analyze_by_category(trades):
    """Analyze performance by market category."""

    by_category = defaultdict(list)

    for trade in trades:
        category = trade.get("category", "unknown")
        by_category[category].append(trade)

    for category, cat_trades in by_category.items():
        pnl = sum(t["pnl"] for t in cat_trades)
        win_rate = sum(1 for t in cat_trades if t["pnl"] > 0) / len(cat_trades)
        avg_edge = sum(abs(t["edge"]) for t in cat_trades) / len(cat_trades)

        print(f"\n{category}:")
        print(f"  Trades: {len(cat_trades)}")
        print(f"  Total PnL: ${pnl:.2f}")
        print(f"  Win rate: {win_rate:.1%}")
        print(f"  Avg edge: {avg_edge:.3f}")
```

### Time-Based Analysis

Analyze performance over time:

```python
def analyze_time_series(trades):
    """Analyze performance time series."""

    # Sort by timestamp
    trades = sorted(trades, key=lambda t: t["timestamp"])

    # Calculate cumulative PnL
    cumulative_pnl = []
    running_pnl = 0

    for trade in trades:
        running_pnl += trade["pnl"]
        cumulative_pnl.append(running_pnl)

    # Calculate rolling Sharpe (30-trade window)
    rolling_sharpe = []

    for i in range(29, len(trades)):
        window = trades[i-29:i+1]
        pnls = [t["pnl"] for t in window]
        mean_pnl = sum(pnls) / len(pnls)
        std_pnl = (sum((p - mean_pnl)**2 for p in pnls) / len(pnls)) ** 0.5
        sharpe = mean_pnl / std_pnl * (30 ** 0.5) if std_pnl > 0 else 0
        rolling_sharpe.append(sharpe)

    print(f"Final cumulative PnL: ${cumulative_pnl[-1]:.2f}")
    print(f"Final rolling Sharpe (30-trade): {rolling_sharpe[-1]:.2f}")

    # Detect degradation
    if len(rolling_sharpe) > 60:
        early_sharpe = sum(rolling_sharpe[:30]) / 30
        late_sharpe = sum(rolling_sharpe[-30:]) / 30

        if late_sharpe < early_sharpe * 0.7:
            print(f"WARNING: Performance degradation detected")
            print(f"  Early Sharpe: {early_sharpe:.2f}")
            print(f"  Late Sharpe: {late_sharpe:.2f}")
```

### Attribution Analysis

Attribute performance to specific factors:

```python
def attribution_analysis(trades):
    """Attribute PnL to different factors."""

    total_pnl = sum(t["pnl"] for t in trades)

    # Attribute to edge quality
    high_edge_trades = [t for t in trades if abs(t["edge"]) > 0.10]
    low_edge_trades = [t for t in trades if abs(t["edge"]) <= 0.10]

    high_edge_pnl = sum(t["pnl"] for t in high_edge_trades)
    low_edge_pnl = sum(t["pnl"] for t in low_edge_trades)

    print("Attribution by edge:")
    print(f"  High edge (>10%): ${high_edge_pnl:.2f} ({high_edge_pnl/total_pnl:.1%})")
    print(f"  Low edge (<=10%): ${low_edge_pnl:.2f} ({low_edge_pnl/total_pnl:.1%})")

    # Attribute to execution quality
    good_execution = [t for t in trades if t["slippage_bps"] < 30]
    poor_execution = [t for t in trades if t["slippage_bps"] >= 30]

    good_exec_pnl = sum(t["pnl"] for t in good_execution)
    poor_exec_pnl = sum(t["pnl"] for t in poor_execution)

    print("\nAttribution by execution:")
    print(f"  Good execution (<30bps): ${good_exec_pnl:.2f}")
    print(f"  Poor execution (>=30bps): ${poor_exec_pnl:.2f}")
```

## Strategy Tuning

Systematic approaches to tuning strategy parameters.

### Grid Search

Exhaustive search over parameter grid:

```python
# tuning/grid_search.py
import itertools
import json

def grid_search(param_grid: dict, dataset: str):
    """Grid search over parameter combinations."""

    # Generate all combinations
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(itertools.product(*param_values))

    results = []

    for combo in combinations:
        # Create config
        config = dict(zip(param_names, combo))

        # Run backtest
        metrics = run_backtest(config, dataset)

        results.append({
            "config": config,
            "sharpe": metrics["sharpe"],
            "brier": metrics["brier_score"],
            "slippage": metrics["avg_slippage_bps"]
        })

        print(f"Config: {config} -> Sharpe: {metrics['sharpe']:.2f}")

    # Find best
    best = max(results, key=lambda r: r["sharpe"])

    print(f"\nBest config: {best['config']}")
    print(f"  Sharpe: {best['sharpe']:.2f}")

    return best

# Example usage
param_grid = {
    "min_edge": [0.03, 0.05, 0.08, 0.10],
    "aggressive_edge": [0.10, 0.12, 0.15, 0.20],
    "max_risk_fraction": [0.01, 0.015, 0.02, 0.025]
}

best = grid_search(param_grid, "datasets/markets.json")
```

**Warning**: Grid search with N parameters and K values each requires K^N backtests. Use sparingly.

### Bayesian Optimization

Smarter search using Gaussian process:

```python
# tuning/bayesian_optimization.py
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern
import numpy as np

def bayesian_optimize(param_bounds: dict, n_iterations: int = 50):
    """Bayesian optimization of parameters."""

    # Initialize
    param_names = list(param_bounds.keys())
    bounds = np.array([param_bounds[name] for name in param_names])

    # Sample initial points
    X_observed = []
    y_observed = []

    for _ in range(5):
        # Random sample
        params = {
            name: np.random.uniform(bounds[i, 0], bounds[i, 1])
            for i, name in enumerate(param_names)
        }

        # Evaluate
        metrics = run_backtest(params, "datasets/markets.json")
        sharpe = metrics["sharpe"]

        X_observed.append([params[name] for name in param_names])
        y_observed.append(sharpe)

    # Bayesian optimization loop
    for i in range(n_iterations):
        # Fit GP
        gp = GaussianProcessRegressor(kernel=Matern(nu=2.5))
        gp.fit(X_observed, y_observed)

        # Find next point (maximize expected improvement)
        next_params = find_next_point(gp, bounds)

        # Evaluate
        params = dict(zip(param_names, next_params))
        metrics = run_backtest(params, "datasets/markets.json")
        sharpe = metrics["sharpe"]

        # Update
        X_observed.append(next_params)
        y_observed.append(sharpe)

        print(f"Iteration {i+1}: Sharpe={sharpe:.2f}")

    # Best result
    best_idx = np.argmax(y_observed)
    best_params = dict(zip(param_names, X_observed[best_idx]))
    best_sharpe = y_observed[best_idx]

    print(f"\nBest params: {best_params}")
    print(f"Best Sharpe: {best_sharpe:.2f}")

    return best_params

# Example
param_bounds = {
    "min_edge": [0.02, 0.15],
    "aggressive_edge": [0.08, 0.25],
    "max_risk_fraction": [0.005, 0.03]
}

best = bayesian_optimize(param_bounds)
```

### Online Parameter Adaptation

Adapt parameters based on recent performance:

```python
class AdaptiveAgent(AutoPredictAgent):
    """Agent that adapts parameters based on performance."""

    def __init__(self, config):
        super().__init__(config)
        self.recent_trades = []
        self.adaptation_window = 20

    def evaluate_market(self, market, bankroll):
        """Evaluate market with adaptive parameters."""

        # Update parameters based on recent performance
        if len(self.recent_trades) >= self.adaptation_window:
            self._adapt_parameters()

        # Normal evaluation
        return super().evaluate_market(market, bankroll)

    def record_trade(self, trade):
        """Record trade for adaptation."""
        self.recent_trades.append(trade)

        # Keep only recent window
        if len(self.recent_trades) > self.adaptation_window:
            self.recent_trades.pop(0)

    def _adapt_parameters(self):
        """Adapt parameters based on recent performance."""

        # Calculate recent Sharpe
        pnls = [t.pnl for t in self.recent_trades]
        mean_pnl = sum(pnls) / len(pnls)
        std_pnl = (sum((p - mean_pnl)**2 for p in pnls) / len(pnls)) ** 0.5
        sharpe = mean_pnl / std_pnl * (len(pnls) ** 0.5) if std_pnl > 0 else 0

        # Adapt min_edge based on Sharpe
        if sharpe < 0.5:
            # Performance poor - be more selective
            self.config.min_edge = min(self.config.min_edge * 1.1, 0.15)
            print(f"Increasing min_edge to {self.config.min_edge:.3f}")
        elif sharpe > 2.0:
            # Performance great - be more aggressive
            self.config.min_edge = max(self.config.min_edge * 0.9, 0.02)
            print(f"Decreasing min_edge to {self.config.min_edge:.3f}")

        # Adapt risk based on drawdown
        recent_pnl_curve = [sum(pnls[:i+1]) for i in range(len(pnls))]
        max_so_far = max(recent_pnl_curve)
        current = recent_pnl_curve[-1]
        drawdown = max_so_far - current

        if drawdown > 50:
            # Large drawdown - reduce risk
            self.config.max_risk_fraction *= 0.8
            print(f"Reducing risk to {self.config.max_risk_fraction:.3f}")
```

## Adding Learning Algorithms

Extend AutoPredict with custom learning algorithms.

### Reinforcement Learning

Use RL to learn optimal execution strategy:

```python
# learning/rl_agent.py
import numpy as np

class RLExecutionAgent:
    """RL agent for learning execution strategy."""

    def __init__(self):
        # Q-table: state -> action -> value
        self.q_table = {}
        self.learning_rate = 0.1
        self.discount_factor = 0.95
        self.epsilon = 0.1  # Exploration rate

    def get_state(self, market):
        """Convert market to discrete state."""
        edge_bucket = int(abs(market.fair_prob - market.market_prob) * 20)
        spread_bucket = int(market.order_book.get_spread() * 50)
        return (edge_bucket, spread_bucket)

    def choose_action(self, state):
        """Choose action (market or limit order)."""

        # Initialize state if new
        if state not in self.q_table:
            self.q_table[state] = {"market": 0.0, "limit": 0.0}

        # Epsilon-greedy
        if np.random.random() < self.epsilon:
            return np.random.choice(["market", "limit"])
        else:
            return max(self.q_table[state], key=self.q_table[state].get)

    def update(self, state, action, reward, next_state):
        """Update Q-value based on experience."""

        if state not in self.q_table:
            self.q_table[state] = {"market": 0.0, "limit": 0.0}
        if next_state not in self.q_table:
            self.q_table[next_state] = {"market": 0.0, "limit": 0.0}

        # Q-learning update
        current_q = self.q_table[state][action]
        max_next_q = max(self.q_table[next_state].values())

        new_q = current_q + self.learning_rate * (reward + self.discount_factor * max_next_q - current_q)

        self.q_table[state][action] = new_q

    def train(self, episodes):
        """Train on historical data."""
        # Load historical markets
        # For each market:
        #   - Get state
        #   - Choose action
        #   - Execute (simulate)
        #   - Calculate reward (negative slippage + PnL)
        #   - Update Q-values
        pass
```

### Imitation Learning

Learn from expert demonstrations:

```python
class ImitationLearner:
    """Learn strategy by imitating expert trades."""

    def __init__(self):
        self.examples = []

    def add_expert_trade(self, market_state, action):
        """Record expert decision."""
        self.examples.append((market_state, action))

    def train_classifier(self):
        """Train classifier to predict expert actions."""
        from sklearn.ensemble import RandomForestClassifier

        # Extract features
        X = []
        y = []

        for market, action in self.examples:
            features = [
                market.fair_prob - market.market_prob,
                market.order_book.get_spread(),
                market.order_book.get_total_depth(),
                market.time_to_expiry_hours
            ]
            X.append(features)
            y.append(1 if action.order_type == "market" else 0)

        # Train
        clf = RandomForestClassifier()
        clf.fit(X, y)

        return clf

    def predict_action(self, market):
        """Predict what expert would do."""
        features = [
            market.fair_prob - market.market_prob,
            market.order_book.get_spread(),
            market.order_book.get_total_depth(),
            market.time_to_expiry_hours
        ]

        prediction = self.clf.predict([features])[0]
        return "market" if prediction == 1 else "limit"
```

### Feature Learning

Automatically discover useful features:

```python
def discover_features(trades):
    """Discover predictive features for PnL."""
    from sklearn.ensemble import RandomForestRegressor
    import pandas as pd

    # Create feature matrix
    features = []
    targets = []

    for trade in trades:
        features.append({
            "edge": trade["edge"],
            "abs_edge": abs(trade["edge"]),
            "spread_pct": trade["spread_pct"],
            "edge_to_spread": abs(trade["edge"]) / max(trade["spread_pct"], 0.001),
            "liquidity": trade["liquidity"],
            "time_to_expiry": trade["time_to_expiry_hours"],
            "order_type": 1 if trade["order_type"] == "market" else 0
        })
        targets.append(trade["pnl"])

    # Train regression model
    df = pd.DataFrame(features)
    rf = RandomForestRegressor(n_estimators=100)
    rf.fit(df, targets)

    # Feature importance
    importance = sorted(
        zip(df.columns, rf.feature_importances_),
        key=lambda x: x[1],
        reverse=True
    )

    print("Feature importance:")
    for feature, score in importance:
        print(f"  {feature}: {score:.3f}")

    return importance
```

## Meta-Learning

Learn how to learn better.

### Strategy Portfolio

Combine multiple strategies:

```python
class StrategyPortfolio:
    """Portfolio of multiple strategies."""

    def __init__(self, strategies: list):
        self.strategies = strategies
        self.weights = [1.0 / len(strategies)] * len(strategies)

    def evaluate_market(self, market, bankroll):
        """Combine strategy decisions."""

        orders = []

        for strategy in self.strategies:
            order = strategy.evaluate_market(market, bankroll)
            if order:
                orders.append(order)

        if not orders:
            return None

        # Weight orders
        total_size = sum(o.size * w for o, w in zip(orders, self.weights) if o)
        # ... combine logic

    def update_weights(self, performance_by_strategy):
        """Update weights based on performance."""

        # Example: Softmax of recent Sharpe ratios
        sharpes = [p["sharpe"] for p in performance_by_strategy]
        exp_sharpes = [np.exp(s) for s in sharpes]
        total = sum(exp_sharpes)
        self.weights = [e / total for e in exp_sharpes]

        print("Updated weights:", self.weights)
```

### Cross-Validation for Strategy Selection

```python
def cross_validate_strategies(strategies, dataset, n_folds=5):
    """Cross-validate multiple strategies."""

    # Load data
    markets = load_markets(dataset)

    # Split into folds
    fold_size = len(markets) // n_folds
    results = {s.name: [] for s in strategies}

    for fold in range(n_folds):
        # Test set for this fold
        test_start = fold * fold_size
        test_end = test_start + fold_size
        test_markets = markets[test_start:test_end]

        # Test each strategy
        for strategy in strategies:
            metrics = run_backtest(strategy, test_markets)
            results[strategy.name].append(metrics["sharpe"])

    # Average results
    for name, sharpes in results.items():
        avg_sharpe = sum(sharpes) / len(sharpes)
        std_sharpe = (sum((s - avg_sharpe)**2 for s in sharpes) / len(sharpes)) ** 0.5
        print(f"{name}: {avg_sharpe:.2f} ± {std_sharpe:.2f}")

    return results
```

## Online Learning

Learn during live trading (advanced).

### Incremental Updates

Update model after each trade:

```python
class OnlineLearningAgent(AutoPredictAgent):
    """Agent that learns online during trading."""

    def __init__(self, config):
        super().__init__(config)
        self.trade_history = []

    def record_outcome(self, trade, outcome):
        """Record trade outcome and update model."""

        self.trade_history.append({
            "trade": trade,
            "outcome": outcome,
            "pnl": calculate_pnl(trade, outcome)
        })

        # Update model every 10 trades
        if len(self.trade_history) % 10 == 0:
            self._update_model()

    def _update_model(self):
        """Update internal model based on recent trades."""

        # Example: Adjust min_edge based on recent calibration
        recent = self.trade_history[-20:]

        forecast_errors = [
            abs(t["trade"]["fair_prob"] - t["outcome"])
            for t in recent
        ]

        avg_error = sum(forecast_errors) / len(forecast_errors)

        # If forecasts are overconfident, increase min_edge
        if avg_error > 0.15:
            self.config.min_edge = min(self.config.min_edge * 1.05, 0.15)
            print(f"Calibration poor - increasing min_edge to {self.config.min_edge:.3f}")
```

### Regret Minimization

Minimize cumulative regret vs optimal strategy:

```python
class RegretMinimizer:
    """Online learning via regret minimization."""

    def __init__(self, strategies):
        self.strategies = strategies
        self.cumulative_rewards = [0.0] * len(strategies)
        self.counts = [0] * len(strategies)

    def select_strategy(self):
        """Select strategy using UCB1 algorithm."""

        total_count = sum(self.counts)

        if total_count < len(self.strategies):
            # Explore each strategy at least once
            return self.counts.index(0)

        # UCB1: balance exploitation and exploration
        ucb_scores = []

        for i in range(len(self.strategies)):
            avg_reward = self.cumulative_rewards[i] / max(self.counts[i], 1)
            exploration_bonus = (2 * np.log(total_count) / max(self.counts[i], 1)) ** 0.5
            ucb_scores.append(avg_reward + exploration_bonus)

        return np.argmax(ucb_scores)

    def update(self, strategy_idx, reward):
        """Update after observing reward."""
        self.cumulative_rewards[strategy_idx] += reward
        self.counts[strategy_idx] += 1
```

## Learning Checklist

Before deploying a learning agent:

- [ ] Learning loop is well-defined (clear objective function)
- [ ] Updates are validated before deployment
- [ ] Learning rate is conservative (avoid overfitting to recent data)
- [ ] Performance is monitored (detect degradation)
- [ ] Kill switch exists (halt learning if performance degrades)
- [ ] Learned parameters are version controlled
- [ ] Out-of-sample validation after each update

## Next Steps

- Read **BACKTESTING.md** for rigorous validation of learned strategies
- Read **DEPLOYMENT.md** for deploying learning agents to production
- Read **CONTRIBUTING.md** to contribute learning algorithms back to AutoPredict
- Explore **notebooks/04_parameter_tuning.ipynb** for hands-on tuning examples

## Further Reading

- [Reinforcement Learning: An Introduction](http://incompleteideas.net/book/the-book.html) by Sutton & Barto
- [Online Learning and Online Convex Optimization](https://www.cs.huji.ac.il/~shais/papers/OLsurvey.pdf) by Shai Shalev-Shwartz
- [Bandit Algorithms](https://tor-lattimore.com/downloads/book/book.pdf) by Lattimore & Szepesvári
- [AutoML: Methods, Systems, Challenges](https://www.automl.org/book/) - automated machine learning techniques
