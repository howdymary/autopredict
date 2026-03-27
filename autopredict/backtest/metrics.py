"""Prediction market specific metrics for backtest analysis.

This module provides metrics tailored to prediction markets, including
calibration analysis, Brier score decomposition, and time-decay analysis.
"""

from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from market_env import ForecastRecord, TradeRecord

EPSILON = 1e-9


@dataclass
class CalibrationBucket:
    """Calibration statistics for a probability bucket.

    Attributes:
        range_str: Bucket range as string (e.g., "0.4-0.5")
        lower: Lower bound of bucket
        upper: Upper bound of bucket
        count: Number of forecasts in this bucket
        avg_probability: Average predicted probability
        realized_rate: Actual outcome rate
        calibration_error: Absolute difference between predicted and realized
        brier_contribution: Contribution to overall Brier score
    """

    range_str: str
    lower: float
    upper: float
    count: int
    avg_probability: float
    realized_rate: float
    calibration_error: float
    brier_contribution: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "range": self.range_str,
            "lower": self.lower,
            "upper": self.upper,
            "count": self.count,
            "avg_probability": self.avg_probability,
            "realized_rate": self.realized_rate,
            "calibration_error": self.calibration_error,
            "brier_contribution": self.brier_contribution,
        }


@dataclass
class BrierDecomposition:
    """Brier score decomposition into reliability, resolution, and uncertainty.

    The Brier score can be decomposed as:
    Brier = Reliability - Resolution + Uncertainty

    - Reliability: How well-calibrated the probabilities are (lower is better)
    - Resolution: How much the forecasts vary from base rate (higher is better)
    - Uncertainty: Inherent uncertainty from base rate (constant for dataset)

    Attributes:
        brier_score: Overall Brier score (mean squared error)
        reliability: Calibration component (how far off predictions are)
        resolution: Discrimination component (how well predictions separate outcomes)
        uncertainty: Base rate uncertainty component
    """

    brier_score: float
    reliability: float
    resolution: float
    uncertainty: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "brier_score": self.brier_score,
            "reliability": self.reliability,
            "resolution": self.resolution,
            "uncertainty": self.uncertainty,
            "interpretation": {
                "reliability_quality": "good" if self.reliability < 0.05 else "needs_improvement",
                "resolution_quality": "good" if self.resolution > 0.05 else "weak",
                "note": "Reliability should be low, Resolution should be high",
            },
        }


@dataclass
class CalibrationAnalysis:
    """Comprehensive calibration analysis for probability forecasts.

    Attributes:
        buckets: Calibration statistics by probability bucket
        brier_decomposition: Brier score breakdown
        overall_brier: Overall Brier score
        num_forecasts: Total number of forecasts
        mean_absolute_calibration_error: Average calibration error across buckets
        max_calibration_error: Maximum calibration error in any bucket
    """

    buckets: list[CalibrationBucket]
    brier_decomposition: BrierDecomposition
    overall_brier: float
    num_forecasts: int
    mean_absolute_calibration_error: float
    max_calibration_error: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "overall_brier": self.overall_brier,
            "num_forecasts": self.num_forecasts,
            "mean_absolute_calibration_error": self.mean_absolute_calibration_error,
            "max_calibration_error": self.max_calibration_error,
            "buckets": [bucket.to_dict() for bucket in self.buckets],
            "brier_decomposition": self.brier_decomposition.to_dict(),
        }


@dataclass
class TimeDecayAnalysis:
    """Analysis of how edge and profitability vary with time to expiry.

    Attributes:
        buckets: Map of time bucket to metrics
        overall_stats: Aggregate statistics across all time buckets
    """

    buckets: dict[str, dict[str, float]]
    overall_stats: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "buckets": self.buckets,
            "overall_stats": self.overall_stats,
        }


@dataclass
class LiquidityRegimeAnalysis:
    """Analysis of performance across different liquidity regimes.

    Attributes:
        thin_markets: Metrics for thin markets (low liquidity)
        thick_markets: Metrics for thick markets (high liquidity)
        threshold: Liquidity threshold separating thin from thick
    """

    thin_markets: dict[str, float]
    thick_markets: dict[str, float]
    threshold: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "threshold": self.threshold,
            "thin_markets": self.thin_markets,
            "thick_markets": self.thick_markets,
        }


class PredictionMarketMetrics:
    """Comprehensive metrics calculator for prediction market backtests.

    This class computes all prediction market specific metrics including:
    - Calibration curves and Brier score decomposition
    - Market-by-market profit attribution
    - Time-to-expiry analysis
    - Liquidity regime analysis
    """

    @staticmethod
    def calculate_calibration(forecasts: list[ForecastRecord], num_buckets: int = 10) -> CalibrationAnalysis:
        """Calculate calibration analysis with buckets and Brier decomposition.

        Args:
            forecasts: List of probability forecasts with outcomes
            num_buckets: Number of probability buckets (default 10)

        Returns:
            CalibrationAnalysis with detailed calibration metrics

        Raises:
            ValueError: If forecasts list is empty
        """
        if not forecasts:
            raise ValueError("Cannot calculate calibration with empty forecasts list")

        # Compute overall Brier score
        brier_score = statistics.fmean(
            (forecast.probability - forecast.outcome) ** 2 for forecast in forecasts
        )

        # Create probability buckets
        bucket_size = 1.0 / num_buckets
        buckets_data: dict[int, list[ForecastRecord]] = {i: [] for i in range(num_buckets)}

        for forecast in forecasts:
            bucket_idx = min(int(forecast.probability / bucket_size), num_buckets - 1)
            buckets_data[bucket_idx].append(forecast)

        # Calculate calibration for each bucket
        buckets: list[CalibrationBucket] = []
        calibration_errors: list[float] = []

        for idx in range(num_buckets):
            bucket_forecasts = buckets_data[idx]
            if not bucket_forecasts:
                continue

            lower = idx * bucket_size
            upper = (idx + 1) * bucket_size
            range_str = f"{lower:.2f}-{upper:.2f}"

            avg_prob = statistics.fmean(f.probability for f in bucket_forecasts)
            realized_rate = statistics.fmean(float(f.outcome) for f in bucket_forecasts)
            calibration_error = abs(avg_prob - realized_rate)
            brier_contrib = statistics.fmean(
                (f.probability - f.outcome) ** 2 for f in bucket_forecasts
            )

            bucket = CalibrationBucket(
                range_str=range_str,
                lower=lower,
                upper=upper,
                count=len(bucket_forecasts),
                avg_probability=avg_prob,
                realized_rate=realized_rate,
                calibration_error=calibration_error,
                brier_contribution=brier_contrib,
            )
            buckets.append(bucket)
            calibration_errors.append(calibration_error)

        # Brier score decomposition
        base_rate = statistics.fmean(float(f.outcome) for f in forecasts)
        uncertainty = base_rate * (1 - base_rate)

        # Reliability: weighted calibration error
        reliability = 0.0
        for bucket in buckets:
            weight = bucket.count / len(forecasts)
            reliability += weight * (bucket.avg_probability - bucket.realized_rate) ** 2

        # Resolution: how well predictions discriminate
        resolution = 0.0
        for bucket in buckets:
            weight = bucket.count / len(forecasts)
            resolution += weight * (bucket.realized_rate - base_rate) ** 2

        decomposition = BrierDecomposition(
            brier_score=brier_score,
            reliability=reliability,
            resolution=resolution,
            uncertainty=uncertainty,
        )

        return CalibrationAnalysis(
            buckets=buckets,
            brier_decomposition=decomposition,
            overall_brier=brier_score,
            num_forecasts=len(forecasts),
            mean_absolute_calibration_error=statistics.fmean(calibration_errors) if calibration_errors else 0.0,
            max_calibration_error=max(calibration_errors) if calibration_errors else 0.0,
        )

    @staticmethod
    def calculate_market_attribution(trades: list[TradeRecord]) -> dict[str, dict[str, float]]:
        """Calculate profit attribution by market.

        Groups trades by market and computes per-market statistics.

        Args:
            trades: List of executed trades

        Returns:
            Dictionary mapping market_id to metrics (pnl, num_trades, win_rate, etc.)
        """
        if not trades:
            return {}

        market_groups: dict[str, list[TradeRecord]] = {}
        for trade in trades:
            if trade.market_id not in market_groups:
                market_groups[trade.market_id] = []
            market_groups[trade.market_id].append(trade)

        attribution: dict[str, dict[str, float]] = {}
        for market_id, market_trades in market_groups.items():
            total_pnl = sum(t.pnl for t in market_trades)
            wins = sum(1 for t in market_trades if t.pnl > 0)
            win_rate = wins / len(market_trades) if market_trades else 0.0

            attribution[market_id] = {
                "total_pnl": total_pnl,
                "num_trades": float(len(market_trades)),
                "win_rate": win_rate,
                "avg_pnl": total_pnl / len(market_trades),
                "avg_fill_rate": statistics.fmean(t.fill_rate for t in market_trades),
                "avg_slippage_bps": statistics.fmean(abs(t.slippage_bps) for t in market_trades),
            }

        return attribution

    @staticmethod
    def calculate_time_decay_analysis(
        trades: list[TradeRecord],
        time_buckets: list[tuple[float, float]] | None = None,
    ) -> TimeDecayAnalysis:
        """Analyze how performance varies with time to expiry.

        Args:
            trades: List of executed trades (must have time_to_expiry in metadata)
            time_buckets: Custom time buckets as (min_hours, max_hours) tuples

        Returns:
            TimeDecayAnalysis with performance by time bucket

        Note:
            This requires trades to have time_to_expiry_hours in their metadata.
            If not available, returns empty analysis.
        """
        if not trades:
            return TimeDecayAnalysis(buckets={}, overall_stats={})

        # Default time buckets: <6h, 6-24h, 24-72h, >72h
        if time_buckets is None:
            time_buckets = [
                (0, 6),
                (6, 24),
                (24, 72),
                (72, float("inf")),
            ]

        # This is a simplified version - in practice you'd need time_to_expiry
        # stored in TradeRecord or passed separately
        buckets_data: dict[str, list[TradeRecord]] = {
            f"{low}h-{high}h" if high != float("inf") else f"{low}h+": []
            for low, high in time_buckets
        }

        # Since TradeRecord doesn't have time_to_expiry, return overall stats only
        overall_stats = {
            "total_pnl": sum(t.pnl for t in trades),
            "num_trades": float(len(trades)),
            "avg_pnl": statistics.fmean(t.pnl for t in trades),
            "win_rate": sum(1 for t in trades if t.pnl > 0) / len(trades),
        }

        return TimeDecayAnalysis(
            buckets={},
            overall_stats=overall_stats,
        )

    @staticmethod
    def calculate_liquidity_regime_analysis(
        trades: list[TradeRecord],
        threshold: float = 100.0,
    ) -> LiquidityRegimeAnalysis:
        """Analyze performance across liquidity regimes.

        Args:
            trades: List of executed trades
            threshold: Liquidity threshold separating thin from thick markets

        Returns:
            LiquidityRegimeAnalysis with metrics by regime

        Note:
            This requires liquidity information to be stored with trades.
            Current implementation uses fill_rate as a proxy for liquidity.
        """
        if not trades:
            return LiquidityRegimeAnalysis(
                thin_markets={},
                thick_markets={},
                threshold=threshold,
            )

        # Use fill_rate as proxy for liquidity
        # High fill rate suggests thick market, low fill rate suggests thin market
        thin_trades = [t for t in trades if t.fill_rate < 0.5]
        thick_trades = [t for t in trades if t.fill_rate >= 0.5]

        def _compute_stats(trade_list: list[TradeRecord]) -> dict[str, float]:
            if not trade_list:
                return {
                    "num_trades": 0.0,
                    "total_pnl": 0.0,
                    "avg_pnl": 0.0,
                    "win_rate": 0.0,
                    "avg_slippage_bps": 0.0,
                    "avg_fill_rate": 0.0,
                }
            return {
                "num_trades": float(len(trade_list)),
                "total_pnl": sum(t.pnl for t in trade_list),
                "avg_pnl": statistics.fmean(t.pnl for t in trade_list),
                "win_rate": sum(1 for t in trade_list if t.pnl > 0) / len(trade_list),
                "avg_slippage_bps": statistics.fmean(abs(t.slippage_bps) for t in trade_list),
                "avg_fill_rate": statistics.fmean(t.fill_rate for t in trade_list),
            }

        return LiquidityRegimeAnalysis(
            thin_markets=_compute_stats(thin_trades),
            thick_markets=_compute_stats(thick_trades),
            threshold=threshold,
        )

    @staticmethod
    def calculate_hit_rate_by_confidence(
        forecasts: list[ForecastRecord],
        confidence_threshold: float = 0.6,
    ) -> dict[str, float]:
        """Calculate hit rate for high vs low confidence forecasts.

        Args:
            forecasts: List of probability forecasts with outcomes
            confidence_threshold: Threshold for high confidence (default 0.6)

        Returns:
            Dictionary with hit rates for confident and non-confident forecasts
        """
        if not forecasts:
            return {
                "high_confidence_hit_rate": 0.0,
                "low_confidence_hit_rate": 0.0,
                "high_confidence_count": 0.0,
                "low_confidence_count": 0.0,
            }

        # High confidence: prob > threshold or prob < (1 - threshold)
        high_conf = [
            f for f in forecasts
            if f.probability > confidence_threshold or f.probability < (1 - confidence_threshold)
        ]
        low_conf = [
            f for f in forecasts
            if (1 - confidence_threshold) >= f.probability >= confidence_threshold
        ]

        def _hit_rate(forecast_list: list[ForecastRecord]) -> float:
            if not forecast_list:
                return 0.0
            # For high probability forecasts, hit = outcome 1
            # For low probability forecasts, hit = outcome 0
            hits = sum(
                1 for f in forecast_list
                if (f.probability > 0.5 and f.outcome == 1) or (f.probability <= 0.5 and f.outcome == 0)
            )
            return hits / len(forecast_list)

        return {
            "high_confidence_hit_rate": _hit_rate(high_conf),
            "low_confidence_hit_rate": _hit_rate(low_conf),
            "high_confidence_count": float(len(high_conf)),
            "low_confidence_count": float(len(low_conf)),
        }

    @staticmethod
    def calculate_edge_realization(
        trades: list[TradeRecord],
    ) -> dict[str, float]:
        """Calculate how much of theoretical edge was realized.

        Compares expected value (based on fill price vs outcome) to actual PnL
        to measure execution quality and edge capture.

        Args:
            trades: List of executed trades

        Returns:
            Dictionary with edge realization metrics
        """
        if not trades:
            return {
                "theoretical_edge": 0.0,
                "realized_edge": 0.0,
                "edge_capture_rate": 0.0,
                "execution_cost_bps": 0.0,
            }

        theoretical_pnl = 0.0
        realized_pnl = 0.0
        total_execution_cost = 0.0

        for trade in trades:
            # Theoretical edge: what you'd make with perfect execution at mid price
            if trade.side == "buy":
                theoretical = (trade.outcome - trade.mid_at_decision) * trade.filled_size
            else:
                theoretical = (trade.mid_at_decision - trade.outcome) * trade.filled_size

            theoretical_pnl += theoretical
            realized_pnl += trade.pnl
            total_execution_cost += abs(trade.slippage_bps) * trade.filled_size

        edge_capture_rate = (realized_pnl / theoretical_pnl) if abs(theoretical_pnl) > EPSILON else 0.0
        avg_execution_cost_bps = (
            (total_execution_cost / len(trades)) if trades else 0.0
        )

        return {
            "theoretical_edge": theoretical_pnl,
            "realized_edge": realized_pnl,
            "edge_capture_rate": edge_capture_rate,
            "execution_cost_bps": avg_execution_cost_bps,
            "num_trades": float(len(trades)),
        }
