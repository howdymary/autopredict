# Contributing to AutoPredict

Thank you for your interest in contributing to AutoPredict! This guide will help you contribute effectively.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Workflow](#development-workflow)
4. [Code Style](#code-style)
5. [Testing](#testing)
6. [Pull Request Process](#pull-request-process)
7. [Adding New Features](#adding-new-features)
8. [Documentation](#documentation)

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Focus on what is best for the community
- Show empathy toward other community members
- Provide constructive feedback
- Accept constructive criticism gracefully

### Reporting Issues

If you experience or witness unacceptable behavior, please report it to the maintainers.

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Git for version control
- Basic understanding of prediction markets

### Setting Up Development Environment

1. **Fork and clone the repository**

```bash
git clone https://github.com/yourusername/autopredict.git
cd autopredict
```

2. **Create a virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install development dependencies**

```bash
# Core dependencies (stdlib only - no external deps)
# Install optional dev tools
pip install pytest pytest-cov black mypy
```

4. **Verify setup**

```bash
# Run tests
python -m pytest tests/ -v

# Run a backtest
python -m autopredict.cli backtest

# Should complete without errors
```

### Repository Structure

```
autopredict/
├── agent.py              # Mutable agent logic
├── market_env.py         # Fixed market simulation
├── cli.py                # Command-line interface
├── run_experiment.py     # Backtest harness
├── autopredict/          # Package structure
│   ├── core/             # Core components
│   ├── strategies/       # Strategy implementations
│   ├── markets/          # Market adapters
│   └── learning/         # Learning algorithms
├── tests/                # Test suite
├── examples/             # Example implementations
├── scripts/              # Utility scripts
└── docs/                 # Additional documentation
```

## Development Workflow

### Branching Strategy

- `main`: Stable release branch
- `develop`: Development branch for integration
- `feature/xxx`: Feature branches
- `bugfix/xxx`: Bug fix branches
- `docs/xxx`: Documentation updates

### Workflow Steps

1. **Create a feature branch**

```bash
git checkout -b feature/my-new-feature
```

2. **Make your changes**

Write code, add tests, update docs.

3. **Run tests**

```bash
python -m pytest tests/ -v --cov=. --cov-report=html
```

4. **Commit your changes**

```bash
git add .
git commit -m "Add feature: description of what you added"
```

5. **Push and create PR**

```bash
git push origin feature/my-new-feature
# Create pull request on GitHub
```

## Code Style

### Python Style Guide

AutoPredict follows **PEP 8** with some modifications:

- **Line length**: 120 characters (not 79)
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Double quotes for strings
- **Naming**:
  - Classes: `PascalCase`
  - Functions/methods: `snake_case`
  - Constants: `UPPER_SNAKE_CASE`
  - Private methods: `_leading_underscore`

### Code Formatting

Use **Black** for automatic formatting:

```bash
# Format all Python files
black . --line-length 120

# Check formatting without changing files
black . --check --line-length 120
```

### Type Hints

**All public functions must have type hints:**

```python
# Good
def calculate_trade_size(edge: float, bankroll: float, max_fraction: float) -> float:
    """Calculate position size."""
    return bankroll * max_fraction * edge

# Bad (no type hints)
def calculate_trade_size(edge, bankroll, max_fraction):
    return bankroll * max_fraction * edge
```

Use **mypy** for type checking:

```bash
mypy agent.py market_env.py --strict
```

### Docstrings

**All public classes and methods must have docstrings:**

Format: Google-style docstrings

```python
def evaluate_market(self, market: MarketState, bankroll: float) -> ProposedOrder | None:
    """Evaluate whether to trade a market.

    Analyzes market conditions and decides whether to propose a trade based on
    edge size, liquidity, spread, and risk constraints.

    Args:
        market: Market snapshot with price, order book, and metadata
        bankroll: Current available capital in currency units

    Returns:
        ProposedOrder if opportunity detected, None otherwise

    Raises:
        ValueError: If bankroll is negative

    Examples:
        >>> agent = AutoPredictAgent(config)
        >>> market = MarketState(...)
        >>> order = agent.evaluate_market(market, bankroll=1000.0)
        >>> if order:
        ...     print(f"Trade: {order.side} {order.size:.2f}")
    """
```

### Comments

- Use comments to explain **why**, not **what**
- Avoid obvious comments
- Use TODO comments for future improvements

```python
# Good
# Use Kelly criterion to avoid over-betting
size = kelly_position_size(edge, bankroll, kelly_fraction=0.25)

# Bad
# Calculate size
size = kelly_position_size(edge, bankroll, kelly_fraction=0.25)
```

## Testing

### Test Requirements

**All new features must include tests.**

- Unit tests for individual functions
- Integration tests for component interactions
- End-to-end tests for full workflows

### Writing Tests

Use **pytest** for all tests:

```python
# tests/test_agent.py
import pytest
from autopredict.agent import AutoPredictAgent, AgentConfig, MarketState
from autopredict.market_env import OrderBook, BookLevel

def test_agent_evaluates_market():
    """Test that agent correctly evaluates a market snapshot."""

    # Setup
    config = AgentConfig(min_edge=0.05)
    agent = AutoPredictAgent(config)

    market = MarketState(
        market_id="test-market",
        market_prob=0.45,
        fair_prob=0.60,  # 15% edge
        time_to_expiry_hours=24.0,
        order_book=OrderBook(
            market_id="test-market",
            bids=[BookLevel(0.44, 100.0)],
            asks=[BookLevel(0.46, 100.0)]
        )
    )

    # Execute
    order = agent.evaluate_market(market, bankroll=1000.0)

    # Verify
    assert order is not None
    assert order.side == "buy"
    assert order.size > 0


def test_agent_skips_low_edge():
    """Test that agent skips markets with insufficient edge."""

    config = AgentConfig(min_edge=0.10)
    agent = AutoPredictAgent(config)

    market = MarketState(
        market_id="test-market",
        market_prob=0.45,
        fair_prob=0.50,  # Only 5% edge (below 10% threshold)
        time_to_expiry_hours=24.0,
        order_book=OrderBook(
            market_id="test-market",
            bids=[BookLevel(0.44, 100.0)],
            asks=[BookLevel(0.46, 100.0)]
        )
    )

    order = agent.evaluate_market(market, bankroll=1000.0)

    assert order is None  # Should skip
```

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_agent.py -v

# Run specific test
python -m pytest tests/test_agent.py::test_agent_evaluates_market -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Coverage Requirements

- **Minimum 80% code coverage** for new features
- **100% coverage** for critical functions (order execution, PnL calculation, risk checks)

## Pull Request Process

### Before Submitting

Checklist:

- [ ] Code follows style guide (run `black`)
- [ ] Type hints added (run `mypy`)
- [ ] Docstrings added for all public APIs
- [ ] Tests added and passing (run `pytest`)
- [ ] Coverage >= 80% for new code
- [ ] Documentation updated (README, guides, etc.)
- [ ] Commit messages are clear and descriptive

### PR Title Format

Use conventional commits:

- `feat: Add new strategy type`
- `fix: Correct slippage calculation`
- `docs: Update STRATEGIES.md`
- `test: Add tests for market adapter`
- `refactor: Simplify order sizing logic`
- `perf: Optimize order book walking`

### PR Description Template

```markdown
## Description
Brief description of what this PR does.

## Motivation
Why is this change needed? What problem does it solve?

## Changes
- List of specific changes made
- Include any breaking changes

## Testing
How was this tested?
- [ ] Unit tests added
- [ ] Integration tests added
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guide
- [ ] Tests pass
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (if applicable)

## Screenshots (if applicable)
Add screenshots for UI changes.
```

### Review Process

1. **Automated checks**: CI runs tests and linting
2. **Code review**: Maintainer reviews code
3. **Discussion**: Address feedback and questions
4. **Approval**: Maintainer approves PR
5. **Merge**: PR is merged to develop branch

### After Merge

- Delete your feature branch
- Pull latest changes from develop
- Check that your feature works in develop

## Adding New Features

### Adding a New Strategy

1. **Create strategy config**

```json
// strategy_configs/my_strategy.json
{
  "name": "my_strategy_v1",
  "min_edge": 0.05,
  "aggressive_edge": 0.12,
  ...
}
```

2. **Implement strategy logic** (if needed)

```python
# autopredict/strategies/my_strategy.py
from autopredict.agent import AutoPredictAgent

class MyCustomStrategy(AutoPredictAgent):
    """Custom strategy implementation."""

    def evaluate_market(self, market, bankroll):
        # Custom logic here
        pass
```

3. **Add tests**

```python
# tests/test_my_strategy.py
def test_my_strategy():
    # Test your strategy
    pass
```

4. **Add documentation**

Update `STRATEGIES.md` with your strategy example.

5. **Create example**

Add example to `examples/my_strategy/` directory.

### Adding a New Market Adapter

1. **Create adapter class**

```python
# autopredict/markets/my_platform.py
from dataclasses import dataclass
from typing import List

@dataclass
class MyPlatformMarket:
    """Market data from MyPlatform API."""
    market_id: str
    price: float
    volume: float
    # ... platform-specific fields

class MyPlatformAdapter:
    """Adapter for MyPlatform prediction market."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch_markets(self) -> List[MyPlatformMarket]:
        """Fetch markets from API."""
        # Implement API calls
        pass

    def to_market_state(self, platform_market: MyPlatformMarket) -> MarketState:
        """Convert platform format to AutoPredict format."""
        # Implement conversion
        pass
```

2. **Add tests**

```python
# tests/test_my_platform.py
def test_adapter_fetches_markets():
    adapter = MyPlatformAdapter(api_key="test")
    markets = adapter.fetch_markets()
    assert len(markets) > 0
```

3. **Add documentation**

Create `docs/adapters/my_platform.md` with usage guide.

### Adding a New Metric

1. **Implement metric calculation**

```python
# In market_env.py
def calculate_my_metric(trades: List[Trade]) -> float:
    """Calculate my custom metric.

    Args:
        trades: List of executed trades

    Returns:
        Metric value
    """
    # Implementation
    return metric_value
```

2. **Add to evaluation**

```python
# In market_env.py evaluate_all()
def evaluate_all(trades, forecasts, outcomes):
    # ... existing metrics ...

    metrics["my_metric"] = calculate_my_metric(trades)

    return metrics
```

3. **Add tests**

```python
def test_my_metric():
    trades = [...]
    metric = calculate_my_metric(trades)
    assert metric >= 0  # Or whatever constraint
```

4. **Document metric**

Add to `METRICS.md` with interpretation guide.

### Adding a Learning Algorithm

1. **Create learning module**

```python
# autopredict/learning/my_algorithm.py
class MyLearningAlgorithm:
    """My custom learning algorithm."""

    def __init__(self, config):
        self.config = config

    def learn(self, trade_history):
        """Learn from trade history."""
        # Implementation
        pass

    def suggest_parameters(self):
        """Suggest new parameters based on learning."""
        return updated_config
```

2. **Add tests**

3. **Add example**

Create `examples/learning/my_algorithm_example.py`

4. **Document algorithm**

Add section to `LEARNING.md`

## Documentation

### Documentation Requirements

**All new features must be documented:**

- API documentation (docstrings)
- User guide (relevant .md file)
- Example usage
- Migration guide (if breaking changes)

### Documentation Files

- `README.md`: Project overview
- `QUICKSTART.md`: Getting started tutorial
- `ARCHITECTURE.md`: System design
- `STRATEGIES.md`: Strategy development
- `BACKTESTING.md`: Backtesting guide
- `DEPLOYMENT.md`: Production deployment
- `LEARNING.md`: Self-improvement guide
- `METRICS.md`: Metric reference
- `CONTRIBUTING.md`: This file

### Writing Good Documentation

**Principles**:
- Write for beginners, not experts
- Include code examples
- Show expected output
- Explain **why**, not just **how**
- Keep it up-to-date

**Example**:

```markdown
## How to Calculate Position Size

Position size determines how much capital to risk on a trade. AutoPredict uses
a configurable approach based on edge and bankroll.

### Example

```python
# Calculate position size based on edge
edge = 0.08  # 8% edge
bankroll = 1000.0
max_risk_fraction = 0.02  # Risk 2% per trade

size = bankroll * max_risk_fraction  # $20
```

**Output**: $20 position size

This limits your maximum loss to 2% of bankroll on this trade.
\```
```

## Community

### Getting Help

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions and share ideas
- **Discord** (if available): Chat with other developers

### Recognition

Contributors will be recognized in:
- `CONTRIBUTORS.md` file
- Release notes
- Project README

## License

By contributing to AutoPredict, you agree that your contributions will be licensed under the same license as the project (MIT License).

## Questions?

If you have questions about contributing:

1. Check existing documentation
2. Search GitHub Issues
3. Create a new Issue with your question
4. Tag it with "question"

Thank you for contributing to AutoPredict!
