"""Parameter tuning via grid search and backtesting.

Provides tools for automatically tuning strategy parameters by running
backtests over parameter grids and selecting configurations that maximize
performance on validation data.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .logger import TradeLog


@dataclass
class ParameterGrid:
    """Defines a grid of parameter values to search over.

    Example:
        >>> grid = ParameterGrid({
        ...     "min_edge": [0.03, 0.05, 0.08, 0.10],
        ...     "aggressive_edge": [0.10, 0.12, 0.15],
        ...     "max_risk_fraction": [0.01, 0.02, 0.03],
        ... })
        >>> for params in grid:
        ...     print(params)
        {'min_edge': 0.03, 'aggressive_edge': 0.10, 'max_risk_fraction': 0.01}
        {'min_edge': 0.03, 'aggressive_edge': 0.10, 'max_risk_fraction': 0.02}
        ...
    """

    param_ranges: dict[str, list[Any]]

    def __iter__(self):
        """Iterate over all parameter combinations in the grid."""
        param_names = list(self.param_ranges.keys())
        param_values = [self.param_ranges[name] for name in param_names]

        for values in itertools.product(*param_values):
            yield dict(zip(param_names, values))

    def __len__(self) -> int:
        """Total number of parameter combinations."""
        count = 1
        for values in self.param_ranges.values():
            count *= len(values)
        return count


@dataclass
class BacktestResult:
    """Results from a single backtest run.

    Attributes:
        params: Parameter configuration tested
        total_pnl: Total profit/loss
        sharpe_ratio: Risk-adjusted return metric
        win_rate: Fraction of winning trades
        total_trades: Number of trades executed
        calibration_error: Mean absolute calibration error
        edge_capture_rate: Fraction of predicted edge captured
    """

    params: dict[str, Any]
    total_pnl: float
    sharpe_ratio: float | None
    win_rate: float
    total_trades: int
    calibration_error: float
    edge_capture_rate: float

    def score(self, scoring_fn: Callable[[BacktestResult], float] | None = None) -> float:
        """Calculate score for this result.

        Args:
            scoring_fn: Custom scoring function (default: Sharpe ratio with fallbacks)

        Returns:
            Numeric score (higher is better)
        """
        if scoring_fn is not None:
            return scoring_fn(self)

        # Default scoring: prioritize Sharpe, fallback to PnL
        if self.sharpe_ratio is not None and self.total_trades >= 10:
            return self.sharpe_ratio
        elif self.total_trades > 0:
            # Penalize low trade counts
            trade_penalty = min(1.0, self.total_trades / 10.0)
            return self.total_pnl * trade_penalty
        else:
            return -1000.0  # No trades = bad

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "params": self.params,
            "total_pnl": self.total_pnl,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "calibration_error": self.calibration_error,
            "edge_capture_rate": self.edge_capture_rate,
            "score": self.score(),
        }


class GridSearchTuner:
    """Grid search parameter tuner using backtesting.

    Systematically tests all combinations in a parameter grid and selects
    the configuration that maximizes a scoring metric on validation data.

    Example:
        >>> param_grid = ParameterGrid({
        ...     "min_edge": [0.03, 0.05, 0.08],
        ...     "aggressive_edge": [0.10, 0.12, 0.15],
        ... })
        >>>
        >>> tuner = GridSearchTuner(
        ...     param_grid=param_grid,
        ...     backtest_fn=run_backtest_with_params,
        ...     scoring_fn=lambda r: r.sharpe_ratio or 0.0
        ... )
        >>>
        >>> best_params, best_result = tuner.tune()
        >>> print(f"Best params: {best_params}")
        >>> print(f"Best Sharpe: {best_result.sharpe_ratio}")
    """

    def __init__(
        self,
        param_grid: ParameterGrid,
        backtest_fn: Callable[[dict[str, Any]], BacktestResult],
        scoring_fn: Callable[[BacktestResult], float] | None = None,
        verbose: bool = True,
    ):
        """Initialize grid search tuner.

        Args:
            param_grid: Grid of parameter values to search
            backtest_fn: Function that runs backtest with given params and returns BacktestResult
            scoring_fn: Function to score results (default: Sharpe ratio)
            verbose: Print progress during search
        """
        self.param_grid = param_grid
        self.backtest_fn = backtest_fn
        self.scoring_fn = scoring_fn
        self.verbose = verbose
        self.results: list[BacktestResult] = []

    def tune(self) -> tuple[dict[str, Any], BacktestResult]:
        """Run grid search and return best parameters.

        Returns:
            Tuple of (best_params, best_result)
        """
        if self.verbose:
            print(f"Starting grid search over {len(self.param_grid)} configurations...")

        best_score = float('-inf')
        best_params = None
        best_result = None

        for i, params in enumerate(self.param_grid, 1):
            if self.verbose:
                print(f"[{i}/{len(self.param_grid)}] Testing: {params}")

            # Run backtest with these parameters
            result = self.backtest_fn(params)
            self.results.append(result)

            # Score this result
            score = result.score(self.scoring_fn)

            if self.verbose:
                print(f"  Score: {score:.4f}, PnL: ${result.total_pnl:.2f}, "
                      f"Trades: {result.total_trades}, Sharpe: {result.sharpe_ratio}")

            # Track best
            if score > best_score:
                best_score = score
                best_params = params
                best_result = result

                if self.verbose:
                    print(f"  *** New best! ***")

        if self.verbose:
            print(f"\nGrid search complete. Best score: {best_score:.4f}")
            print(f"Best params: {best_params}")

        if best_params is None or best_result is None:
            raise ValueError("Grid search failed to find any valid results")

        return best_params, best_result

    def get_top_n(self, n: int = 5) -> list[tuple[dict[str, Any], BacktestResult]]:
        """Get top N parameter configurations by score.

        Args:
            n: Number of top results to return

        Returns:
            List of (params, result) tuples, sorted by score descending
        """
        scored_results = [
            (result.params, result, result.score(self.scoring_fn))
            for result in self.results
        ]
        scored_results.sort(key=lambda x: x[2], reverse=True)

        return [(params, result) for params, result, _ in scored_results[:n]]

    def save_results(self, output_path: Path) -> None:
        """Save all grid search results to JSON file.

        Args:
            output_path: Path to save results
        """
        data = {
            "param_grid": self.param_grid.param_ranges,
            "total_configs": len(self.param_grid),
            "results": [result.to_dict() for result in self.results],
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        if self.verbose:
            print(f"Results saved to {output_path}")


class BayesianTuner:
    """Placeholder for future Bayesian optimization tuning.

    Uses intelligent search strategies (e.g., Optuna, scikit-optimize) to
    efficiently explore parameter space without exhaustive grid search.

    This is a stub for future implementation. For now, use GridSearchTuner.

    Example future usage:
        >>> from optuna import create_study
        >>> tuner = BayesianTuner(
        ...     param_space={
        ...         "min_edge": (0.01, 0.20),  # Continuous range
        ...         "aggressive_edge": (0.05, 0.30),
        ...         "max_risk_fraction": (0.005, 0.05),
        ...     },
        ...     backtest_fn=run_backtest_with_params,
        ...     n_trials=100  # Much more efficient than grid search
        ... )
        >>> best_params = tuner.tune()
    """

    def __init__(
        self,
        param_space: dict[str, tuple[float, float]],
        backtest_fn: Callable[[dict[str, Any]], BacktestResult],
        n_trials: int = 100,
    ):
        """Initialize Bayesian tuner (placeholder).

        Args:
            param_space: Map of param_name -> (min, max) ranges
            backtest_fn: Function to run backtest and return result
            n_trials: Number of trials to run
        """
        self.param_space = param_space
        self.backtest_fn = backtest_fn
        self.n_trials = n_trials

    def tune(self) -> dict[str, Any]:
        """Run Bayesian optimization (not yet implemented).

        Returns:
            Best parameters found

        Raises:
            NotImplementedError: Always (this is a placeholder)
        """
        raise NotImplementedError(
            "BayesianTuner is a placeholder for future implementation. "
            "Use GridSearchTuner for now, or implement with Optuna/scikit-optimize."
        )


def create_param_grid_from_current(
    current_params: dict[str, float],
    perturbation_factor: float = 0.2,
    n_steps: int = 3,
) -> ParameterGrid:
    """Create a parameter grid centered on current parameters.

    Useful for local search around known-good configurations.

    Args:
        current_params: Current parameter values
        perturbation_factor: How much to vary each param (0.2 = ±20%)
        n_steps: Number of steps above/below current value

    Returns:
        ParameterGrid for local search

    Example:
        >>> current = {"min_edge": 0.05, "aggressive_edge": 0.12}
        >>> grid = create_param_grid_from_current(current, perturbation_factor=0.3, n_steps=3)
        >>> # Creates grid around current values:
        >>> # min_edge: [0.035, 0.0425, 0.05, 0.0575, 0.065]
        >>> # aggressive_edge: [0.084, 0.102, 0.12, 0.138, 0.156]
    """
    param_ranges = {}

    for param_name, current_value in current_params.items():
        # Create range centered on current value
        step_size = current_value * perturbation_factor / n_steps
        values = []

        for i in range(-n_steps, n_steps + 1):
            value = current_value + i * step_size
            # Keep positive
            if value > 0:
                values.append(round(value, 6))

        param_ranges[param_name] = sorted(set(values))

    return ParameterGrid(param_ranges)


def default_scoring_function(result: BacktestResult) -> float:
    """Default scoring function for parameter tuning.

    Prioritizes:
    1. Sharpe ratio (if enough trades)
    2. Total PnL (penalized for low trade count)
    3. Heavy penalty for no trades

    Args:
        result: Backtest result to score

    Returns:
        Numeric score (higher is better)
    """
    # Need minimum trade count for reliable Sharpe
    if result.sharpe_ratio is not None and result.total_trades >= 20:
        # Bonus for calibration
        calibration_bonus = max(0, 1.0 - result.calibration_error)
        return result.sharpe_ratio * (1.0 + calibration_bonus * 0.2)

    # Fallback to PnL with trade count penalty
    if result.total_trades > 0:
        trade_penalty = min(1.0, result.total_trades / 20.0)
        return result.total_pnl * trade_penalty
    else:
        return -1000.0  # Heavily penalize no-trade configs
