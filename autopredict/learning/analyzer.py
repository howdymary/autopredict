"""Performance analysis tools for trade logs.

Analyzes historical trading decisions to identify patterns, failure modes,
and opportunities for improvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import statistics
from collections import defaultdict

from .logger import TradeLog


@dataclass
class PerformanceReport:
    """Comprehensive performance analysis report.

    Attributes:
        total_trades: Total number of trades (excluding passes)
        total_pnl: Total profit/loss across all resolved trades
        win_rate: Fraction of profitable trades
        avg_win: Average profit on winning trades
        avg_loss: Average loss on losing trades
        sharpe_ratio: Risk-adjusted return measure (if applicable)
        by_market: Performance metrics grouped by market
        by_category: Performance metrics grouped by market category
        by_decision: Breakdown of buy/sell/pass decisions
        failure_regimes: Identified systematic failure patterns
        calibration_error: Mean absolute error between model_prob and outcome
        edge_capture_rate: Fraction of predicted edge actually captured
        recommendations: List of suggested parameter adjustments
    """

    total_trades: int
    total_pnl: float
    win_rate: float
    avg_win: float
    avg_loss: float
    sharpe_ratio: float | None
    by_market: dict[str, dict[str, Any]]
    by_category: dict[str, dict[str, Any]]
    by_decision: dict[str, int]
    failure_regimes: list[str]
    calibration_error: float
    edge_capture_rate: float
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "total_trades": self.total_trades,
            "total_pnl": self.total_pnl,
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "sharpe_ratio": self.sharpe_ratio,
            "by_market": self.by_market,
            "by_category": self.by_category,
            "by_decision": self.by_decision,
            "failure_regimes": self.failure_regimes,
            "calibration_error": self.calibration_error,
            "edge_capture_rate": self.edge_capture_rate,
            "recommendations": self.recommendations,
        }


class PerformanceAnalyzer:
    """Analyzes trade logs to identify performance patterns and failure modes.

    Example:
        >>> logs = logger.load_recent(days=30)
        >>> analyzer = PerformanceAnalyzer(logs)
        >>> report = analyzer.generate_report()
        >>> print(f"Win rate: {report.win_rate:.2%}")
        >>> print(f"Total PnL: ${report.total_pnl:.2f}")
        >>>
        >>> # Analyze specific dimensions
        >>> market_stats = analyzer.analyze_by_market()
        >>> category_stats = analyzer.analyze_by_category("category")
        >>> failures = analyzer.identify_failure_regimes()
    """

    def __init__(self, logs: list[TradeLog]):
        """Initialize analyzer with trade logs.

        Args:
            logs: List of TradeLog entries to analyze
        """
        self.logs = logs
        self.resolved_logs = [log for log in logs if log.outcome is not None]
        self.trade_logs = [log for log in logs if log.decision != "pass"]

    def analyze_by_market(self) -> dict[str, dict[str, Any]]:
        """Analyze performance grouped by individual market.

        Returns:
            Dictionary mapping market_id to performance metrics:
            {
                "market_id": {
                    "trades": 5,
                    "pnl": 12.5,
                    "win_rate": 0.8,
                    "avg_edge": 0.12,
                    "calibration_error": 0.05
                }
            }
        """
        market_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "trades": 0,
                "pnl": 0.0,
                "wins": 0,
                "edges": [],
                "errors": [],
            }
        )

        for log in self.resolved_logs:
            if log.decision == "pass":
                continue

            stats = market_stats[log.market_id]
            stats["trades"] += 1

            if log.pnl is not None:
                stats["pnl"] += log.pnl
                if log.pnl > 0:
                    stats["wins"] += 1

            stats["edges"].append(abs(log.edge))

            # Calibration: error between model prediction and actual outcome
            if log.outcome is not None:
                error = abs(log.model_prob - log.outcome)
                stats["errors"].append(error)

        # Compute derived metrics
        result = {}
        for market_id, stats in market_stats.items():
            result[market_id] = {
                "trades": stats["trades"],
                "pnl": stats["pnl"],
                "win_rate": stats["wins"] / stats["trades"] if stats["trades"] > 0 else 0.0,
                "avg_edge": statistics.mean(stats["edges"]) if stats["edges"] else 0.0,
                "calibration_error": statistics.mean(stats["errors"]) if stats["errors"] else 0.0,
            }

        return result

    def analyze_by_category(self, feature: str = "category") -> dict[str, dict[str, Any]]:
        """Analyze performance grouped by a categorical feature.

        Args:
            feature: Key in log.rationale to group by (default: "category")

        Returns:
            Dictionary mapping feature value to performance metrics
        """
        category_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "trades": 0,
                "pnl": 0.0,
                "wins": 0,
                "edges": [],
                "errors": [],
            }
        )

        for log in self.resolved_logs:
            if log.decision == "pass":
                continue

            # Extract category from rationale
            category = log.rationale.get(feature, "unknown")
            stats = category_stats[category]
            stats["trades"] += 1

            if log.pnl is not None:
                stats["pnl"] += log.pnl
                if log.pnl > 0:
                    stats["wins"] += 1

            stats["edges"].append(abs(log.edge))

            if log.outcome is not None:
                error = abs(log.model_prob - log.outcome)
                stats["errors"].append(error)

        # Compute derived metrics
        result = {}
        for category, stats in category_stats.items():
            result[category] = {
                "trades": stats["trades"],
                "pnl": stats["pnl"],
                "win_rate": stats["wins"] / stats["trades"] if stats["trades"] > 0 else 0.0,
                "avg_edge": statistics.mean(stats["edges"]) if stats["edges"] else 0.0,
                "calibration_error": statistics.mean(stats["errors"]) if stats["errors"] else 0.0,
            }

        return result

    def identify_failure_regimes(self) -> list[str]:
        """Identify systematic failure patterns in trading strategy.

        Analyzes where strategy consistently loses money or has poor calibration.

        Returns:
            List of human-readable failure regime descriptions:
            [
                "Wide spreads (>5%): -$15.2 PnL over 8 trades",
                "Low liquidity (<50): -$8.4 PnL over 5 trades",
                "Sports category: calibration error 0.18 over 12 trades"
            ]
        """
        failures = []

        # Analyze by spread width
        wide_spread_logs = [
            log for log in self.resolved_logs
            if log.decision != "pass" and log.rationale.get("spread_pct", 0) > 0.05
        ]
        if wide_spread_logs:
            pnl = sum(log.pnl for log in wide_spread_logs if log.pnl is not None)
            if pnl < -5.0:  # Threshold for significant loss
                failures.append(
                    f"Wide spreads (>5%): ${pnl:.1f} PnL over {len(wide_spread_logs)} trades"
                )

        # Analyze by liquidity
        low_liquidity_logs = [
            log for log in self.resolved_logs
            if log.decision != "pass" and log.rationale.get("liquidity_depth", float('inf')) < 50
        ]
        if low_liquidity_logs:
            pnl = sum(log.pnl for log in low_liquidity_logs if log.pnl is not None)
            if pnl < -5.0:
                failures.append(
                    f"Low liquidity (<50): ${pnl:.1f} PnL over {len(low_liquidity_logs)} trades"
                )

        # Analyze by category calibration
        category_stats = self.analyze_by_category("category")
        for category, stats in category_stats.items():
            if stats["trades"] >= 5 and stats["calibration_error"] > 0.15:
                failures.append(
                    f"{category} category: calibration error {stats['calibration_error']:.2f} "
                    f"over {stats['trades']} trades"
                )

        # Analyze by time to expiry
        short_expiry_logs = [
            log for log in self.resolved_logs
            if log.decision != "pass" and log.rationale.get("time_to_expiry_hours", float('inf')) < 6
        ]
        if short_expiry_logs:
            pnl = sum(log.pnl for log in short_expiry_logs if log.pnl is not None)
            if pnl < -5.0:
                failures.append(
                    f"Short expiry (<6h): ${pnl:.1f} PnL over {len(short_expiry_logs)} trades"
                )

        return failures

    def calculate_calibration_error(self) -> float:
        """Calculate mean absolute calibration error.

        Measures how well model probabilities match actual outcomes.

        Returns:
            Mean absolute error between model_prob and outcome (0 = perfect)
        """
        errors = []
        for log in self.resolved_logs:
            if log.outcome is not None:
                error = abs(log.model_prob - log.outcome)
                errors.append(error)

        return statistics.mean(errors) if errors else 0.0

    def calculate_edge_capture_rate(self) -> float:
        """Calculate what fraction of predicted edge was actually captured.

        Compares realized PnL to predicted edge value.

        Returns:
            Ratio of actual PnL to theoretical edge (1.0 = perfect capture)
        """
        actual_pnl = 0.0
        theoretical_pnl = 0.0

        for log in self.resolved_logs:
            if log.decision == "pass" or log.pnl is None:
                continue

            actual_pnl += log.pnl
            # Theoretical PnL = size * edge (if edge prediction was perfect)
            theoretical_pnl += log.size * abs(log.edge)

        if theoretical_pnl > 0:
            return actual_pnl / theoretical_pnl
        return 0.0

    def generate_recommendations(self) -> list[str]:
        """Generate actionable recommendations based on performance analysis.

        Returns:
            List of recommended parameter adjustments
        """
        recommendations = []
        failure_regimes = self.identify_failure_regimes()

        # Wide spread failures -> increase max_spread_pct threshold
        if any("Wide spreads" in regime for regime in failure_regimes):
            recommendations.append(
                "Reduce max_spread_pct threshold (currently allowing spreads that hurt performance)"
            )

        # Low liquidity failures -> increase min_book_liquidity
        if any("Low liquidity" in regime for regime in failure_regimes):
            recommendations.append(
                "Increase min_book_liquidity threshold (thin order books causing losses)"
            )

        # Poor calibration -> increase min_edge threshold
        calibration_error = self.calculate_calibration_error()
        if calibration_error > 0.15:
            recommendations.append(
                f"Model calibration error high ({calibration_error:.2%}). "
                "Consider increasing min_edge threshold or improving model."
            )

        # Low edge capture -> use more limit orders
        edge_capture = self.calculate_edge_capture_rate()
        if edge_capture < 0.5:
            recommendations.append(
                f"Edge capture rate low ({edge_capture:.2%}). "
                "Consider using more limit orders or reducing aggressive_edge threshold."
            )

        # Low win rate -> be more selective
        if self.trade_logs:
            wins = sum(1 for log in self.resolved_logs if log.pnl and log.pnl > 0)
            win_rate = wins / len(self.resolved_logs) if self.resolved_logs else 0
            if win_rate < 0.45:
                recommendations.append(
                    f"Win rate low ({win_rate:.2%}). Increase min_edge threshold to be more selective."
                )

        return recommendations

    def generate_report(self) -> PerformanceReport:
        """Generate comprehensive performance report.

        Returns:
            PerformanceReport with all metrics and analysis
        """
        # Basic metrics
        total_trades = len(self.trade_logs)
        resolved_trades = [log for log in self.resolved_logs if log.decision != "pass"]

        total_pnl = sum(log.pnl for log in resolved_trades if log.pnl is not None)

        wins = [log for log in resolved_trades if log.pnl and log.pnl > 0]
        losses = [log for log in resolved_trades if log.pnl and log.pnl < 0]

        win_rate = len(wins) / len(resolved_trades) if resolved_trades else 0.0
        avg_win = statistics.mean(log.pnl for log in wins) if wins else 0.0
        avg_loss = statistics.mean(log.pnl for log in losses) if losses else 0.0

        # Sharpe ratio (if we have enough data)
        pnls = [log.pnl for log in resolved_trades if log.pnl is not None]
        sharpe_ratio = None
        if len(pnls) > 1:
            mean_pnl = statistics.mean(pnls)
            std_pnl = statistics.stdev(pnls)
            sharpe_ratio = mean_pnl / std_pnl if std_pnl > 0 else 0.0

        # Decision breakdown
        by_decision = {
            "buy": sum(1 for log in self.logs if log.decision == "buy"),
            "sell": sum(1 for log in self.logs if log.decision == "sell"),
            "pass": sum(1 for log in self.logs if log.decision == "pass"),
        }

        return PerformanceReport(
            total_trades=total_trades,
            total_pnl=total_pnl,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            sharpe_ratio=sharpe_ratio,
            by_market=self.analyze_by_market(),
            by_category=self.analyze_by_category(),
            by_decision=by_decision,
            failure_regimes=self.identify_failure_regimes(),
            calibration_error=self.calculate_calibration_error(),
            edge_capture_rate=self.calculate_edge_capture_rate(),
            recommendations=self.generate_recommendations(),
        )
