"""Grouped reporting helpers for domain, market-family, and regime slices."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Sequence

from autopredict.evaluation.backtest import BacktestResult, BacktestTrade
from autopredict.evaluation.scoring import BinaryForecast, ProperScoringRules

SUPPORTED_GROUP_KEYS = {"domain", "market_family", "regime"}
SPARSE_SUPPORT_THRESHOLD = 3
NARROW_PROBABILITY_STD_THRESHOLD = 0.05
HIGH_CALIBRATION_GAP_THRESHOLD = 0.20


@dataclass(frozen=True)
class DomainSliceSummary:
    """Grouped summary for one domain or market-condition slice."""

    group: str
    count: int
    brier_score: float
    log_score: float
    spherical_score: float
    total_pnl: float
    avg_slippage_bps: float
    mean_absolute_calibration_gap: float
    max_absolute_calibration_gap: float
    mean_absolute_error: float
    forecast_count: int
    trade_count: int
    base_rate: float
    mean_probability: float
    probability_stddev: float
    calibration_bucket_count: int
    warning_flags: tuple[str, ...] = ()
    group_by: str = "domain"

    @property
    def group_value(self) -> str:
        """Backward-compatible alias for the grouped value."""

        return self.group

    def to_dict(self) -> dict[str, Any]:
        """Serialize the summary to a plain dictionary."""

        return {
            "group": self.group,
            "group_by": self.group_by,
            "count": self.count,
            "brier_score": self.brier_score,
            "log_score": self.log_score,
            "spherical_score": self.spherical_score,
            "total_pnl": self.total_pnl,
            "avg_slippage_bps": self.avg_slippage_bps,
            "mean_absolute_calibration_gap": self.mean_absolute_calibration_gap,
            "max_absolute_calibration_gap": self.max_absolute_calibration_gap,
            "mean_absolute_error": self.mean_absolute_error,
            "forecast_count": self.forecast_count,
            "trade_count": self.trade_count,
            "base_rate": self.base_rate,
            "mean_probability": self.mean_probability,
            "probability_stddev": self.probability_stddev,
            "calibration_bucket_count": self.calibration_bucket_count,
            "warning_flags": list(self.warning_flags),
        }


def summarize_domain_slices(
    forecasts: Sequence[BinaryForecast],
    trades: Sequence[BacktestTrade],
    *,
    group_by: str = "domain",
    default_group: str = "unknown",
) -> tuple[DomainSliceSummary, ...]:
    """Group forecast and trade outputs by a metadata label."""

    return _summarize_grouped(
        forecasts,
        trades,
        group_by=group_by,
        default_group=default_group,
    )


def summarize_backtest_slices(
    result: BacktestResult,
    *,
    group_by: str = "domain",
    default_group: str = "unknown",
) -> tuple[DomainSliceSummary, ...]:
    """Group one backtest result by a metadata label."""

    return summarize_domain_slices(
        result.forecasts,
        result.trades,
        group_by=group_by,
        default_group=default_group,
    )


def summarize_forecasts_by_metadata(
    forecasts: Sequence[BinaryForecast],
    *,
    group_by: str,
    default_group: str = "unknown",
) -> tuple[DomainSliceSummary, ...]:
    """Group forecast-only summaries by metadata key."""

    return _summarize_grouped(
        forecasts,
        (),
        group_by=group_by,
        default_group=default_group,
    )


def summarize_trades_by_metadata(
    trades: Sequence[BacktestTrade],
    *,
    group_by: str,
    default_group: str = "unknown",
) -> tuple[DomainSliceSummary, ...]:
    """Group trade-only summaries by metadata key."""

    return _summarize_grouped(
        (),
        trades,
        group_by=group_by,
        default_group=default_group,
    )


def summarize_backtest_by_metadata(
    result: BacktestResult,
    *,
    group_by: str,
    default_group: str = "unknown",
) -> tuple[DomainSliceSummary, ...]:
    """Backward-compatible alias for metadata-grouped backtest summaries."""

    return summarize_backtest_slices(
        result,
        group_by=group_by,
        default_group=default_group,
    )


def _summarize_grouped(
    forecasts: Sequence[BinaryForecast],
    trades: Sequence[BacktestTrade],
    *,
    group_by: str,
    default_group: str,
) -> tuple[DomainSliceSummary, ...]:
    group_by = _validate_group_by(group_by)
    grouped_forecasts: dict[str, list[BinaryForecast]] = {}
    grouped_trades: dict[str, list[BacktestTrade]] = {}

    for forecast in forecasts:
        group = _group_value(forecast.metadata, group_by, default_group)
        grouped_forecasts.setdefault(group, []).append(forecast)
    for trade in trades:
        group = _group_value(trade.metadata, group_by, default_group)
        grouped_trades.setdefault(group, []).append(trade)

    summaries: list[DomainSliceSummary] = []
    for group in sorted(set(grouped_forecasts) | set(grouped_trades)):
        group_forecasts = grouped_forecasts.get(group, [])
        group_trades = grouped_trades.get(group, [])
        scoring = ProperScoringRules.evaluate_binary_forecasts(group_forecasts)
        filled_trades = [trade for trade in group_trades if trade.is_filled]
        probabilities = [forecast.probability for forecast in group_forecasts]
        absolute_errors = [
            abs(forecast.probability - float(forecast.outcome))
            for forecast in group_forecasts
        ]
        probability_stddev = (
            statistics.pstdev(probabilities)
            if len(probabilities) > 1
            else 0.0
        )
        warning_flags = _warning_flags(
            group_forecasts,
            scoring.calibration.mean_absolute_gap,
            scoring.calibration.max_absolute_gap,
            probability_stddev,
        )
        summaries.append(
            DomainSliceSummary(
                group=group,
                group_by=group_by,
                count=max(len(group_forecasts), len(group_trades)),
                brier_score=scoring.brier_score,
                log_score=scoring.log_score,
                spherical_score=scoring.spherical_score,
                total_pnl=sum(trade.pnl for trade in filled_trades),
                avg_slippage_bps=(
                    statistics.fmean(trade.slippage_bps for trade in filled_trades)
                    if filled_trades
                    else 0.0
                ),
                mean_absolute_calibration_gap=scoring.calibration.mean_absolute_gap,
                max_absolute_calibration_gap=scoring.calibration.max_absolute_gap,
                mean_absolute_error=(
                    statistics.fmean(absolute_errors)
                    if absolute_errors
                    else 0.0
                ),
                forecast_count=len(group_forecasts),
                trade_count=len(group_trades),
                base_rate=scoring.calibration.base_rate,
                mean_probability=(
                    statistics.fmean(probabilities)
                    if probabilities
                    else 0.0
                ),
                probability_stddev=probability_stddev,
                calibration_bucket_count=len(scoring.calibration.buckets),
                warning_flags=warning_flags,
            )
        )
    return tuple(summaries)


def _group_value(metadata: dict[str, Any], key: str, default_group: str) -> str:
    value: Any = metadata
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return default_group
        value = value[part]
    return str(value)


def _validate_group_by(group_by: str) -> str:
    if group_by not in SUPPORTED_GROUP_KEYS:
        raise ValueError(
            f"group_by must be one of {sorted(SUPPORTED_GROUP_KEYS)}, got {group_by}"
        )
    return group_by


def _warning_flags(
    forecasts: Sequence[BinaryForecast],
    mean_gap: float,
    max_gap: float,
    probability_stddev: float,
) -> tuple[str, ...]:
    flags: list[str] = []
    if len(forecasts) < SPARSE_SUPPORT_THRESHOLD:
        flags.append("sparse_support")
    outcomes = {forecast.outcome for forecast in forecasts}
    if forecasts and len(outcomes) == 1:
        flags.append("single_class_outcomes")
    if forecasts and probability_stddev < NARROW_PROBABILITY_STD_THRESHOLD:
        flags.append("narrow_probability_band")
    if max_gap >= HIGH_CALIBRATION_GAP_THRESHOLD or mean_gap >= HIGH_CALIBRATION_GAP_THRESHOLD:
        flags.append("high_calibration_gap")
    return tuple(flags)
