"""Fixed market environment primitives for prediction market backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
import math
import statistics

# Constants for epsilon values and calculation precision
EPSILON = 1e-9
BPS_MULTIPLIER = 10_000.0

# Default price values for empty order books
DEFAULT_MID_PRICE = 0.5
DEFAULT_BID_PRICE = 0.0
DEFAULT_ASK_PRICE = 1.0
DEFAULT_SPREAD = 1.0

# Fill rate parameters for passive orders
BASE_FILL_RATE = 0.15
AT_TOP_BONUS = 0.2
IMPROVED_BONUS = 0.25
SPREAD_BONUS_RATIO = 0.1
MAX_FILL_RATE = 0.75


@dataclass(frozen=True)
class BookLevel:
    """Single price level in a binary market order book.

    Represents one price level with available liquidity. Frozen (immutable) to
    prevent accidental modification.

    Attributes:
        price: Price at this level (0-1 for binary markets).
        size: Available liquidity at this price (in units or dollars).

    Example:
        >>> bid = BookLevel(price=0.50, size=100.0)
        >>> ask = BookLevel(price=0.51, size=75.0)
    """

    price: float
    size: float


@dataclass
class OrderBook:
    """Minimal order book with depth-aware execution helpers.

    Represents a single-sided order book for a binary market. Maintains sorted
    bids (descending) and asks (ascending) for O(1) best price lookups.

    Attributes:
        market_id: Unique identifier for this market.
        bids: List of BookLevels on the buy side (sorted descending by price).
        asks: List of BookLevels on the sell side (sorted ascending by price).
        trade_history: List of past trades (for future analysis).
        depth_levels: Maximum number of levels to keep (default 10).

    Example:
        >>> book = OrderBook(
        ...     market_id="politics-2025-03",
        ...     bids=[BookLevel(0.50, 100), BookLevel(0.48, 50)],
        ...     asks=[BookLevel(0.51, 75), BookLevel(0.53, 25)]
        ... )
        >>> book.get_spread()
        0.01
        >>> book.get_mid_price()
        0.505
    """

    market_id: str
    bids: list[BookLevel] = field(default_factory=list)
    asks: list[BookLevel] = field(default_factory=list)
    trade_history: list[dict[str, float | str]] = field(default_factory=list)
    depth_levels: int = 10

    def __post_init__(self) -> None:
        self.bids = sorted(self.bids, key=lambda level: level.price, reverse=True)[: self.depth_levels]
        self.asks = sorted(self.asks, key=lambda level: level.price)[: self.depth_levels]

    def clone(self) -> "OrderBook":
        """Return a cheap copy for non-mutating simulations."""

        return OrderBook(
            market_id=self.market_id,
            bids=[BookLevel(level.price, level.size) for level in self.bids],
            asks=[BookLevel(level.price, level.size) for level in self.asks],
            trade_history=list(self.trade_history),
            depth_levels=self.depth_levels,
        )

    def get_liquidity_at_price(self, price: float, side: str) -> float:
        """Return available liquidity at an exact level.

        Args:
            price: The price level to check
            side: "buy" or "sell"

        Returns:
            Total liquidity available at the exact price level
        """

        levels = self.asks if side == "buy" else self.bids
        return sum(level.size for level in levels if math.isclose(level.price, price, rel_tol=0.0, abs_tol=EPSILON))

    def get_total_depth(self, side: str | None = None) -> float:
        """Return total visible depth for one side or both sides."""

        if side == "buy":
            return sum(level.size for level in self.asks)
        if side == "sell":
            return sum(level.size for level in self.bids)
        return sum(level.size for level in self.bids) + sum(level.size for level in self.asks)

    def get_spread(self) -> float:
        """Return best ask minus best bid.

        Returns:
            Spread in absolute terms (ask - bid), or DEFAULT_SPREAD if book is empty
        """

        if not self.bids or not self.asks:
            return DEFAULT_SPREAD
        return max(self.asks[0].price - self.bids[0].price, 0.0)

    def get_mid_price(self) -> float:
        """Return midpoint price.

        Returns:
            Mid price (bid + ask) / 2, or DEFAULT_MID_PRICE if book is empty
        """

        if not self.bids or not self.asks:
            return DEFAULT_MID_PRICE
        return (self.bids[0].price + self.asks[0].price) / 2.0

    def estimate_market_impact(self, size: float, side: str) -> float:
        """Estimate price impact in basis points for a given order size.

        Args:
            size: Order size to estimate impact for
            side: "buy" or "sell"

        Returns:
            Estimated market impact in basis points
        """

        simulated = self.clone()
        before_mid = simulated.get_mid_price()
        filled, _, _ = simulated.walk_book(size=size, side=side, mutate=True)
        after_mid = simulated.get_mid_price()
        if filled <= EPSILON or before_mid <= EPSILON:
            return 0.0
        return abs(after_mid - before_mid) / before_mid * BPS_MULTIPLIER

    def walk_book(
        self,
        size: float,
        side: str,
        *,
        limit_price: float | None = None,
        mutate: bool = False,
    ) -> tuple[float, float | None, list[tuple[float, float]]]:
        """Consume visible depth from the opposite side of the book.

        Args:
            size: Order size to fill
            side: "buy" or "sell"
            limit_price: Optional limit price constraint
            mutate: If True, modify the order book in place

        Returns:
            Tuple of (filled_amount, average_fill_price, list of (price, size) fills)
        """

        if size <= EPSILON:
            return 0.0, None, []

        levels = self.asks if side == "buy" else self.bids
        remaining = size
        notional = 0.0
        fills: list[tuple[float, float]] = []

        for index, level in enumerate(levels):
            if limit_price is not None:
                if side == "buy" and level.price > limit_price:
                    break
                if side == "sell" and level.price < limit_price:
                    break

            take = min(remaining, level.size)
            if take <= EPSILON:
                continue

            remaining -= take
            notional += take * level.price
            fills.append((level.price, take))

            if mutate:
                updated_size = level.size - take
                if updated_size <= EPSILON:
                    levels[index] = BookLevel(level.price, 0.0)
                else:
                    levels[index] = BookLevel(level.price, updated_size)

            if remaining <= EPSILON:
                break

        if mutate:
            cleaned = [level for level in levels if level.size > EPSILON]
            if side == "buy":
                self.asks = cleaned
            else:
                self.bids = cleaned

        filled = size - remaining
        average_fill = (notional / filled) if filled > EPSILON else None
        return filled, average_fill, fills


@dataclass
class ExecutionReport:
    """Normalized execution result."""

    market_id: str
    order_type: str
    side: str
    requested_size: float
    filled_size: float
    average_fill_price: float | None
    reference_mid_price: float
    slippage_bps: float
    market_impact_bps: float
    implementation_shortfall_bps: float
    fill_rate: float
    queued_size: float
    spread_capture_bps: float
    notes: list[str] = field(default_factory=list)


class ExecutionEngine:
    """Execution simulator for market and limit orders."""

    def __init__(self, *, maker_fee_bps: float = 0.0, taker_fee_bps: float = 0.0) -> None:
        self._maker_fee_bps = maker_fee_bps
        self._taker_fee_bps = taker_fee_bps

    def execute_market_order(self, size: float, side: str, order_book: OrderBook) -> ExecutionReport:
        """Walk the book immediately and mutate visible depth.

        Args:
            size: Order size
            side: "buy" or "sell"
            order_book: Order book to walk

        Returns:
            ExecutionReport with filled details
        """

        before_mid = order_book.get_mid_price()
        filled, average_fill, _ = order_book.walk_book(size=size, side=side, mutate=True)
        after_mid = order_book.get_mid_price()
        return self._build_report(
            market_id=order_book.market_id,
            order_type="market",
            side=side,
            requested_size=size,
            filled_size=filled,
            average_fill_price=average_fill,
            reference_mid_price=before_mid,
            after_mid_price=after_mid,
            queued_size=max(size - filled, 0.0),
            passive=False,
        )

    def execute_limit_order(
        self,
        price: float,
        size: float,
        side: str,
        order_book: OrderBook,
        time_in_force: str = "GTC",
    ) -> ExecutionReport:
        """Simulate marketable and passive limit order behavior.

        Args:
            price: Limit order price
            size: Order size
            side: "buy" or "sell"
            order_book: Order book to trade against
            time_in_force: "GTC" (Good Till Cancelled) or "IOC" (Immediate or Cancel)

        Returns:
            ExecutionReport with filled details
        """

        before_mid = order_book.get_mid_price()
        best_bid = order_book.bids[0].price if order_book.bids else DEFAULT_BID_PRICE
        best_ask = order_book.asks[0].price if order_book.asks else DEFAULT_ASK_PRICE

        is_marketable = (side == "buy" and price >= best_ask) or (side == "sell" and price <= best_bid)
        if is_marketable:
            filled, average_fill, _ = order_book.walk_book(
                size=size,
                side=side,
                limit_price=price,
                mutate=True,
            )
            after_mid = order_book.get_mid_price()
            return self._build_report(
                market_id=order_book.market_id,
                order_type="limit",
                side=side,
                requested_size=size,
                filled_size=filled,
                average_fill_price=average_fill,
                reference_mid_price=before_mid,
                after_mid_price=after_mid,
                queued_size=max(size - filled, 0.0),
                passive=False,
            )

        if time_in_force == "IOC":
            return self._build_report(
                market_id=order_book.market_id,
                order_type="limit",
                side=side,
                requested_size=size,
                filled_size=0.0,
                average_fill_price=None,
                reference_mid_price=before_mid,
                after_mid_price=before_mid,
                queued_size=size,
                passive=True,
                notes=["ioc_expired"],
            )

        # Passive order fill rate calculation
        spread = order_book.get_spread()
        same_side_anchor = best_bid if side == "buy" else best_ask
        improved = (side == "buy" and price > best_bid) or (side == "sell" and price < best_ask)
        at_top = math.isclose(price, same_side_anchor, rel_tol=0.0, abs_tol=EPSILON)

        base_fill_rate = BASE_FILL_RATE
        if at_top:
            base_fill_rate += AT_TOP_BONUS
        if improved:
            base_fill_rate += IMPROVED_BONUS
        # Fix: only add spread bonus if spread is positive
        if spread > EPSILON:
            base_fill_rate += min(spread / max(before_mid, EPSILON), SPREAD_BONUS_RATIO)

        filled = min(size, size * min(base_fill_rate, MAX_FILL_RATE))
        average_fill = price if filled > EPSILON else None
        notes = ["passive_queue_fill"] if filled > EPSILON else ["queued"]
        return self._build_report(
            market_id=order_book.market_id,
            order_type="limit",
            side=side,
            requested_size=size,
            filled_size=filled,
            average_fill_price=average_fill,
            reference_mid_price=before_mid,
            after_mid_price=before_mid,
            queued_size=max(size - filled, 0.0),
            passive=True,
            notes=notes,
        )

    def calculate_execution_quality(self, execution_report: ExecutionReport) -> dict[str, float]:
        """Return normalized execution quality metrics.

        Args:
            execution_report: ExecutionReport to extract metrics from

        Returns:
            Dictionary of execution quality metrics
        """

        return {
            "slippage_bps": execution_report.slippage_bps,
            "market_impact_bps": execution_report.market_impact_bps,
            "fill_rate": execution_report.fill_rate,
            "implementation_shortfall_bps": execution_report.implementation_shortfall_bps,
            "spread_capture_bps": execution_report.spread_capture_bps,
        }

    def _build_report(
        self,
        *,
        market_id: str,
        order_type: str,
        side: str,
        requested_size: float,
        filled_size: float,
        average_fill_price: float | None,
        reference_mid_price: float,
        after_mid_price: float,
        queued_size: float,
        passive: bool,
        notes: list[str] | None = None,
    ) -> ExecutionReport:
        """Build an ExecutionReport from order execution details.

        Args:
            market_id: Market identifier
            order_type: "market" or "limit"
            side: "buy" or "sell"
            requested_size: Original requested order size
            filled_size: Actual filled size
            average_fill_price: Average execution price, None if no fill
            reference_mid_price: Mid price at time of order
            after_mid_price: Mid price after execution
            queued_size: Unfilled amount
            passive: Whether this was a passive (maker) order
            notes: Optional notes about the execution

        Returns:
            ExecutionReport with calculated metrics
        """

        fill_rate = (filled_size / requested_size) if requested_size > EPSILON else 0.0
        if average_fill_price is None or filled_size <= EPSILON or reference_mid_price <= EPSILON:
            slippage_bps = 0.0
            shortfall_bps = 0.0
            spread_capture_bps = 0.0
        else:
            if side == "buy":
                slippage_bps = (average_fill_price - reference_mid_price) / reference_mid_price * BPS_MULTIPLIER
                spread_capture_bps = (reference_mid_price - average_fill_price) / reference_mid_price * BPS_MULTIPLIER
            else:
                slippage_bps = (reference_mid_price - average_fill_price) / reference_mid_price * BPS_MULTIPLIER
                spread_capture_bps = (average_fill_price - reference_mid_price) / reference_mid_price * BPS_MULTIPLIER

            fee_bps = self._maker_fee_bps if passive else self._taker_fee_bps
            shortfall_bps = slippage_bps + fee_bps

        if reference_mid_price <= EPSILON:
            market_impact_bps = 0.0
        else:
            market_impact_bps = abs(after_mid_price - reference_mid_price) / reference_mid_price * BPS_MULTIPLIER

        return ExecutionReport(
            market_id=market_id,
            order_type=order_type,
            side=side,
            requested_size=requested_size,
            filled_size=filled_size,
            average_fill_price=average_fill_price,
            reference_mid_price=reference_mid_price,
            slippage_bps=slippage_bps,
            market_impact_bps=market_impact_bps,
            implementation_shortfall_bps=shortfall_bps,
            fill_rate=fill_rate,
            queued_size=queued_size,
            spread_capture_bps=spread_capture_bps,
            notes=notes or [],
        )


@dataclass
class ForecastRecord:
    """Agent forecast for calibration scoring."""

    market_id: str
    probability: float
    outcome: int


@dataclass
class TradeRecord:
    """Executed trade plus realized outcome and forward mid."""

    market_id: str
    side: str
    order_type: str
    requested_size: float
    filled_size: float
    fill_price: float
    mid_at_decision: float
    next_mid_price: float
    outcome: int
    pnl: float
    slippage_bps: float
    market_impact_bps: float
    implementation_shortfall_bps: float
    fill_rate: float


class ExecutionMetrics:
    """Aggregate execution-quality metrics over realized trades."""

    @staticmethod
    def calculate_slippage(trades: list[TradeRecord]) -> float | None:
        """Calculate average absolute slippage in basis points.

        Args:
            trades: List of executed trades

        Returns:
            Average slippage, or None if no trades
        """
        if not trades:
            return None
        return statistics.fmean(abs(trade.slippage_bps) for trade in trades)

    @staticmethod
    def calculate_market_impact(trades: list[TradeRecord]) -> float | None:
        """Calculate average market impact in basis points.

        Args:
            trades: List of executed trades

        Returns:
            Average market impact, or None if no trades
        """
        if not trades:
            return None
        return statistics.fmean(trade.market_impact_bps for trade in trades)

    @staticmethod
    def calculate_fill_rate(trades: list[TradeRecord]) -> float | None:
        """Calculate average fill rate.

        Args:
            trades: List of executed trades

        Returns:
            Average fill rate, or None if no trades
        """
        if not trades:
            return None
        return statistics.fmean(trade.fill_rate for trade in trades)

    @staticmethod
    def calculate_spread_capture(trades: list[TradeRecord]) -> float | None:
        """Calculate average spread capture in basis points for passive fills.

        Args:
            trades: List of executed trades

        Returns:
            Average spread capture, or None if no passive fills
        """
        passive_fills = [
            (trade.mid_at_decision - trade.fill_price) / trade.mid_at_decision * BPS_MULTIPLIER
            if trade.side == "buy"
            else (trade.fill_price - trade.mid_at_decision) / trade.mid_at_decision * BPS_MULTIPLIER
            for trade in trades
            if trade.order_type == "limit" and trade.fill_price > EPSILON and trade.mid_at_decision > EPSILON
        ]
        if not passive_fills:
            return None
        return statistics.fmean(passive_fills)

    @staticmethod
    def calculate_adverse_selection_rate(trades: list[TradeRecord]) -> float | None:
        """Calculate rate of adverse selection on limit orders.

        Args:
            trades: List of executed trades

        Returns:
            Adverse selection rate, or None if no limit fills
        """
        relevant = [trade for trade in trades if trade.order_type == "limit" and trade.filled_size > EPSILON]
        if not relevant:
            return None
        adverse = 0
        for trade in relevant:
            if trade.side == "buy" and trade.next_mid_price < trade.fill_price:
                adverse += 1
            if trade.side == "sell" and trade.next_mid_price > trade.fill_price:
                adverse += 1
        return adverse / len(relevant)

    @staticmethod
    def calculate_implementation_shortfall(trades: list[TradeRecord]) -> float | None:
        """Calculate average implementation shortfall in basis points.

        Args:
            trades: List of executed trades

        Returns:
            Average implementation shortfall, or None if no trades
        """
        if not trades:
            return None
        return statistics.fmean(abs(trade.implementation_shortfall_bps) for trade in trades)


def _brier_score(forecasts: list[ForecastRecord]) -> float:
    """Calculate Brier score (mean squared error) of probability forecasts.

    Args:
        forecasts: List of probability forecasts and outcomes

    Returns:
        Brier score (lower is better)
    """
    if not forecasts:
        return 0.0
    errors = [(forecast.probability - forecast.outcome) ** 2 for forecast in forecasts]
    return statistics.fmean(errors)


def _calibration_by_bucket(forecasts: list[ForecastRecord]) -> dict[str, dict[str, float]]:
    """Analyze calibration by grouping forecasts into probability buckets.

    Args:
        forecasts: List of probability forecasts and outcomes

    Returns:
        Dictionary mapping bucket ranges to calibration stats
    """
    buckets: dict[str, list[ForecastRecord]] = {}
    for forecast in forecasts:
        lower = min(int(forecast.probability * 10), 9) / 10.0
        upper = lower + 0.1
        key = f"{lower:.1f}-{upper:.1f}"
        buckets.setdefault(key, []).append(forecast)

    output: dict[str, dict[str, float]] = {}
    for key, items in sorted(buckets.items()):
        avg_prob = statistics.fmean(item.probability for item in items)
        hit_rate = statistics.fmean(item.outcome for item in items)
        output[key] = {
            "count": float(len(items)),
            "avg_probability": avg_prob,
            "realized_rate": hit_rate,
        }
    return output


def _financial_metrics(trades: list[TradeRecord]) -> dict[str, float]:
    """Calculate financial metrics from trades.

    Args:
        trades: List of executed trades

    Returns:
        Dictionary of financial metrics
    """
    if not trades:
        return {
            "total_pnl": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "num_trades": 0.0,
            "win_rate": 0.0,
        }

    pnl_series = [trade.pnl for trade in trades]
    total_pnl = sum(pnl_series)
    num_trades = float(len(trades))
    wins = sum(1 for pnl in pnl_series if pnl > 0)
    win_rate = wins / len(trades)

    if len(pnl_series) < 2:
        sharpe = 0.0
    else:
        std = statistics.pstdev(pnl_series)
        # Keep this unannualized so strategy ranking does not mechanically improve
        # just because one configuration trades more frequently than another.
        sharpe = (statistics.fmean(pnl_series) / std) if std > EPSILON else 0.0

    running = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnl_series:
        running += pnl
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)

    return {
        "total_pnl": total_pnl,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "num_trades": num_trades,
        "win_rate": win_rate,
    }


def evaluate_all(forecasts: list[ForecastRecord], trades: list[TradeRecord]) -> dict[str, Any]:
    """Return epistemic, financial, and execution metrics together.

    Args:
        forecasts: List of probability forecasts and outcomes
        trades: List of executed trades

    Returns:
        Dictionary of all calculated metrics
    """

    metrics = _financial_metrics(trades)
    metrics["brier_score"] = _brier_score(forecasts)
    metrics["calibration_by_bucket"] = _calibration_by_bucket(forecasts)
    # Note: These may be None if trades list is empty
    metrics["avg_slippage_bps"] = ExecutionMetrics.calculate_slippage(trades)
    metrics["market_impact_bps"] = ExecutionMetrics.calculate_market_impact(trades)
    metrics["fill_rate"] = ExecutionMetrics.calculate_fill_rate(trades)
    metrics["spread_capture_bps"] = ExecutionMetrics.calculate_spread_capture(trades)
    metrics["adverse_selection_rate"] = ExecutionMetrics.calculate_adverse_selection_rate(trades)
    metrics["implementation_shortfall_bps"] = ExecutionMetrics.calculate_implementation_shortfall(trades)
    return metrics


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _normalize_against_baseline(value: float, baseline: float) -> float:
    """Normalize a metric against the baseline with equal performance = 1.0."""

    if abs(baseline) <= EPSILON:
        if abs(value) <= EPSILON:
            return 1.0
        return 2.0 if value > 0 else 0.0

    return _clamp(1.0 + ((value - baseline) / abs(baseline)), 0.0, 2.0)


def calculate_composite_score(
    metrics: Mapping[str, float | int],
    baseline_metrics: Mapping[str, float | int],
) -> float:
    """Combine forecast, execution, and financial metrics into one scalar score."""

    sharpe = _normalize_against_baseline(
        float(metrics.get("sharpe", 0.0) or 0.0),
        float(baseline_metrics.get("sharpe", 0.0) or 0.0),
    )
    pnl = _normalize_against_baseline(
        float(metrics.get("total_pnl", 0.0) or 0.0),
        float(baseline_metrics.get("total_pnl", 0.0) or 0.0),
    )
    drawdown = _normalize_against_baseline(
        float(metrics.get("max_drawdown", 0.0) or 0.0),
        float(baseline_metrics.get("max_drawdown", 0.0) or 0.0),
    )
    brier = _clamp(float(metrics.get("brier_score", 1.0) or 1.0), 0.0, 1.0)
    fill_rate = _clamp(float(metrics.get("fill_rate", 0.0) or 0.0), 0.0, 1.0)

    return (
        0.30 * sharpe
        + 0.25 * (1.0 - brier)
        + 0.20 * pnl
        + 0.15 * fill_rate
        + 0.10 * (1.0 - drawdown)
    )
