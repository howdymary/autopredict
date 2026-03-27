"""Performance analysis and reporting for backtest results.

This module provides comprehensive analysis and reporting capabilities
for backtest results, including performance attribution and visualization helpers.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from .metrics import (
    CalibrationAnalysis,
    LiquidityRegimeAnalysis,
    PredictionMarketMetrics,
    TimeDecayAnalysis,
)
from market_env import ForecastRecord, TradeRecord

EPSILON = 1e-9


@dataclass
class PerformanceReport:
    """Comprehensive performance report for a backtest.

    Contains all metrics organized by category for easy analysis.

    Attributes:
        financial_metrics: PnL, Sharpe, drawdown, win rate
        execution_metrics: Slippage, fill rate, market impact
        epistemic_metrics: Brier score, calibration analysis
        attribution: Market-by-market and time-based attribution
        risk_metrics: Drawdown analysis, volatility, risk-adjusted returns
        summary: High-level summary statistics
    """

    financial_metrics: dict[str, float]
    execution_metrics: dict[str, float]
    epistemic_metrics: dict[str, Any]
    attribution: dict[str, Any]
    risk_metrics: dict[str, float]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for serialization."""
        return {
            "financial_metrics": self.financial_metrics,
            "execution_metrics": self.execution_metrics,
            "epistemic_metrics": self.epistemic_metrics,
            "attribution": self.attribution,
            "risk_metrics": self.risk_metrics,
            "summary": self.summary,
        }

    def save(self, path: str | Path) -> None:
        """Save performance report to JSON file.

        Args:
            path: Output file path
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)

    def print_summary(self) -> None:
        """Print formatted summary to console."""
        print("\n" + "=" * 70)
        print("BACKTEST PERFORMANCE SUMMARY")
        print("=" * 70)

        print("\n📊 FINANCIAL METRICS")
        print("-" * 70)
        for key, value in self.financial_metrics.items():
            if isinstance(value, (int, float)):
                if "pnl" in key.lower() or "bankroll" in key.lower():
                    print(f"  {key:30s}: ${value:>12.2f}")
                elif "rate" in key.lower() or "sharpe" in key.lower():
                    print(f"  {key:30s}: {value:>12.4f}")
                else:
                    print(f"  {key:30s}: {value:>12.2f}")

        print("\n⚡ EXECUTION METRICS")
        print("-" * 70)
        for key, value in self.execution_metrics.items():
            if isinstance(value, (int, float)):
                if "bps" in key.lower():
                    print(f"  {key:30s}: {value:>12.2f} bps")
                elif "rate" in key.lower():
                    print(f"  {key:30s}: {value:>12.2%}")
                else:
                    print(f"  {key:30s}: {value:>12.4f}")

        print("\n🎯 EPISTEMIC METRICS")
        print("-" * 70)
        if "calibration_analysis" in self.epistemic_metrics:
            cal = self.epistemic_metrics["calibration_analysis"]
            print(f"  {'brier_score':30s}: {cal.get('overall_brier', 0):>12.4f}")
            print(f"  {'mean_calibration_error':30s}: {cal.get('mean_absolute_calibration_error', 0):>12.4f}")
            print(f"  {'max_calibration_error':30s}: {cal.get('max_calibration_error', 0):>12.4f}")

        print("\n📈 RISK METRICS")
        print("-" * 70)
        for key, value in self.risk_metrics.items():
            if isinstance(value, (int, float)):
                if "pnl" in key.lower() or "drawdown" in key.lower():
                    print(f"  {key:30s}: ${value:>12.2f}")
                else:
                    print(f"  {key:30s}: {value:>12.4f}")

        print("\n💡 SUMMARY")
        print("-" * 70)
        for key, value in self.summary.items():
            if isinstance(value, str):
                print(f"  {key:30s}: {value}")
            elif isinstance(value, (int, float)):
                print(f"  {key:30s}: {value:>12.2f}")

        print("\n" + "=" * 70 + "\n")


class PerformanceAnalyzer:
    """Analyzer for generating comprehensive performance reports.

    Takes backtest results and computes detailed analysis including
    all financial, execution, and epistemic metrics.

    Example:
        >>> analyzer = PerformanceAnalyzer()
        >>> report = analyzer.analyze(forecasts, trades, starting_bankroll, ending_bankroll)
        >>> report.print_summary()
        >>> report.save("results/performance_report.json")
    """

    def analyze(
        self,
        forecasts: list[ForecastRecord],
        trades: list[TradeRecord],
        starting_bankroll: float,
        ending_bankroll: float,
        additional_metrics: dict[str, Any] | None = None,
    ) -> PerformanceReport:
        """Generate comprehensive performance report.

        Args:
            forecasts: All probability forecasts made during backtest
            trades: All executed trades
            starting_bankroll: Starting capital
            ending_bankroll: Ending capital
            additional_metrics: Optional additional metrics to include

        Returns:
            PerformanceReport with all metrics organized by category
        """
        # Financial metrics
        financial = self._calculate_financial_metrics(
            trades, starting_bankroll, ending_bankroll
        )

        # Execution metrics
        execution = self._calculate_execution_metrics(trades)

        # Epistemic metrics (calibration, Brier score)
        epistemic = self._calculate_epistemic_metrics(forecasts, trades)

        # Attribution analysis
        attribution = self._calculate_attribution(forecasts, trades)

        # Risk metrics
        risk = self._calculate_risk_metrics(trades, starting_bankroll)

        # Summary
        summary = self._generate_summary(
            financial, execution, epistemic, risk, len(forecasts), len(trades)
        )

        # Merge additional metrics if provided
        if additional_metrics:
            for category in ["financial", "execution", "epistemic", "risk"]:
                if category in additional_metrics:
                    target = {
                        "financial": financial,
                        "execution": execution,
                        "epistemic": epistemic,
                        "risk": risk,
                    }[category]
                    target.update(additional_metrics[category])

        return PerformanceReport(
            financial_metrics=financial,
            execution_metrics=execution,
            epistemic_metrics=epistemic,
            attribution=attribution,
            risk_metrics=risk,
            summary=summary,
        )

    def _calculate_financial_metrics(
        self,
        trades: list[TradeRecord],
        starting_bankroll: float,
        ending_bankroll: float,
    ) -> dict[str, float]:
        """Calculate financial performance metrics."""
        if not trades:
            return {
                "starting_bankroll": starting_bankroll,
                "ending_bankroll": ending_bankroll,
                "total_pnl": 0.0,
                "num_trades": 0.0,
                "win_rate": 0.0,
                "avg_pnl_per_trade": 0.0,
                "sharpe_ratio": 0.0,
                "return_pct": 0.0,
            }

        pnl_series = [t.pnl for t in trades]
        total_pnl = sum(pnl_series)
        wins = sum(1 for pnl in pnl_series if pnl > 0)
        win_rate = wins / len(trades)

        # Sharpe ratio (annualized, assuming daily trades)
        if len(pnl_series) >= 2:
            mean_pnl = statistics.fmean(pnl_series)
            std_pnl = statistics.stdev(pnl_series)
            sharpe = (mean_pnl / std_pnl) if std_pnl > EPSILON else 0.0
        else:
            sharpe = 0.0

        return_pct = (total_pnl / starting_bankroll) * 100 if starting_bankroll > 0 else 0.0

        return {
            "starting_bankroll": starting_bankroll,
            "ending_bankroll": ending_bankroll,
            "total_pnl": total_pnl,
            "num_trades": float(len(trades)),
            "win_rate": win_rate,
            "avg_pnl_per_trade": total_pnl / len(trades),
            "sharpe_ratio": sharpe,
            "return_pct": return_pct,
            "winners": float(wins),
            "losers": float(len(trades) - wins),
        }

    def _calculate_execution_metrics(self, trades: list[TradeRecord]) -> dict[str, float]:
        """Calculate execution quality metrics."""
        if not trades:
            return {
                "avg_slippage_bps": 0.0,
                "avg_market_impact_bps": 0.0,
                "avg_fill_rate": 0.0,
                "avg_implementation_shortfall_bps": 0.0,
                "total_execution_cost_bps": 0.0,
            }

        avg_slippage = statistics.fmean(abs(t.slippage_bps) for t in trades)
        avg_impact = statistics.fmean(t.market_impact_bps for t in trades)
        avg_fill = statistics.fmean(t.fill_rate for t in trades)
        avg_shortfall = statistics.fmean(abs(t.implementation_shortfall_bps) for t in trades)

        # Market vs limit order breakdown
        market_orders = [t for t in trades if t.order_type == "market"]
        limit_orders = [t for t in trades if t.order_type == "limit"]

        metrics = {
            "avg_slippage_bps": avg_slippage,
            "avg_market_impact_bps": avg_impact,
            "avg_fill_rate": avg_fill,
            "avg_implementation_shortfall_bps": avg_shortfall,
            "total_execution_cost_bps": avg_slippage + avg_impact,
            "num_market_orders": float(len(market_orders)),
            "num_limit_orders": float(len(limit_orders)),
            "market_order_pct": len(market_orders) / len(trades) if trades else 0.0,
        }

        # Add edge realization
        edge_metrics = PredictionMarketMetrics.calculate_edge_realization(trades)
        metrics.update(edge_metrics)

        return metrics

    def _calculate_epistemic_metrics(
        self,
        forecasts: list[ForecastRecord],
        trades: list[TradeRecord],
    ) -> dict[str, Any]:
        """Calculate epistemic (calibration, accuracy) metrics."""
        if not forecasts:
            return {
                "num_forecasts": 0,
                "calibration_analysis": {},
                "hit_rate_analysis": {},
            }

        # Calibration analysis
        calibration = PredictionMarketMetrics.calculate_calibration(forecasts)

        # Hit rate by confidence
        hit_rate_analysis = PredictionMarketMetrics.calculate_hit_rate_by_confidence(forecasts)

        return {
            "num_forecasts": len(forecasts),
            "calibration_analysis": calibration.to_dict(),
            "hit_rate_analysis": hit_rate_analysis,
        }

    def _calculate_attribution(
        self,
        forecasts: list[ForecastRecord],
        trades: list[TradeRecord],
    ) -> dict[str, Any]:
        """Calculate performance attribution."""
        attribution: dict[str, Any] = {}

        # Market-by-market attribution
        if trades:
            market_attr = PredictionMarketMetrics.calculate_market_attribution(trades)
            attribution["by_market"] = market_attr

            # Time decay analysis
            time_analysis = PredictionMarketMetrics.calculate_time_decay_analysis(trades)
            attribution["by_time"] = time_analysis.to_dict()

            # Liquidity regime analysis
            liquidity_analysis = PredictionMarketMetrics.calculate_liquidity_regime_analysis(trades)
            attribution["by_liquidity"] = liquidity_analysis.to_dict()

        return attribution

    def _calculate_risk_metrics(
        self,
        trades: list[TradeRecord],
        starting_bankroll: float,
    ) -> dict[str, float]:
        """Calculate risk and drawdown metrics."""
        if not trades:
            return {
                "max_drawdown": 0.0,
                "max_drawdown_pct": 0.0,
                "pnl_volatility": 0.0,
                "downside_volatility": 0.0,
                "sortino_ratio": 0.0,
            }

        pnl_series = [t.pnl for t in trades]

        # Drawdown calculation
        running = starting_bankroll
        peak = starting_bankroll
        max_drawdown = 0.0

        for pnl in pnl_series:
            running += pnl
            peak = max(peak, running)
            drawdown = peak - running
            max_drawdown = max(max_drawdown, drawdown)

        max_drawdown_pct = (max_drawdown / peak * 100) if peak > 0 else 0.0

        # Volatility metrics
        pnl_volatility = statistics.stdev(pnl_series) if len(pnl_series) >= 2 else 0.0

        # Downside volatility (only negative returns)
        downside_pnls = [pnl for pnl in pnl_series if pnl < 0]
        downside_volatility = statistics.stdev(downside_pnls) if len(downside_pnls) >= 2 else 0.0

        # Sortino ratio (risk-adjusted return using downside deviation)
        mean_pnl = statistics.fmean(pnl_series)
        sortino = (mean_pnl / downside_volatility) if downside_volatility > EPSILON else 0.0

        return {
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
            "pnl_volatility": pnl_volatility,
            "downside_volatility": downside_volatility,
            "sortino_ratio": sortino,
            "worst_trade": min(pnl_series),
            "best_trade": max(pnl_series),
        }

    def _generate_summary(
        self,
        financial: dict[str, float],
        execution: dict[str, float],
        epistemic: dict[str, Any],
        risk: dict[str, float],
        num_forecasts: int,
        num_trades: int,
    ) -> dict[str, Any]:
        """Generate high-level summary."""
        # Overall quality assessment
        quality_signals = []

        if financial.get("win_rate", 0) > 0.55:
            quality_signals.append("strong_win_rate")
        if financial.get("sharpe_ratio", 0) > 1.0:
            quality_signals.append("good_sharpe")
        if risk.get("max_drawdown_pct", 100) < 10:
            quality_signals.append("low_drawdown")

        cal_analysis = epistemic.get("calibration_analysis", {})
        if cal_analysis.get("overall_brier", 1.0) < 0.15:
            quality_signals.append("well_calibrated")

        if execution.get("avg_fill_rate", 0) > 0.6:
            quality_signals.append("good_fills")
        if execution.get("avg_slippage_bps", 100) < 10:
            quality_signals.append("low_slippage")

        # Generate assessment
        if len(quality_signals) >= 4:
            assessment = "excellent"
        elif len(quality_signals) >= 2:
            assessment = "good"
        elif len(quality_signals) >= 1:
            assessment = "moderate"
        else:
            assessment = "needs_improvement"

        # Key weaknesses
        weaknesses = []
        if financial.get("win_rate", 0) < 0.45:
            weaknesses.append("low_win_rate")
        if risk.get("max_drawdown_pct", 0) > 20:
            weaknesses.append("high_drawdown")
        if cal_analysis.get("overall_brier", 0) > 0.20:
            weaknesses.append("poor_calibration")
        if execution.get("avg_slippage_bps", 0) > 20:
            weaknesses.append("high_slippage")
        if execution.get("avg_fill_rate", 1) < 0.4:
            weaknesses.append("low_fill_rate")

        return {
            "overall_assessment": assessment,
            "quality_signals": quality_signals,
            "key_weaknesses": weaknesses,
            "num_forecasts": num_forecasts,
            "num_trades": num_trades,
            "profitability": "profitable" if financial.get("total_pnl", 0) > 0 else "unprofitable",
            "roi_pct": financial.get("return_pct", 0),
        }
