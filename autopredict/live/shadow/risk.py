"""Signed, reservation-aware worst-case risk for shadow orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contracts import PRICE_SCALE, ShadowOrder, ShadowRiskLimits, ShadowSide


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    reason: str


def split_reduce_open(
    *, position_micros: int, side: ShadowSide, quantity_micros: int
) -> tuple[int, int]:
    """Return quantities that reduce current inventory and open/increase risk."""

    if quantity_micros <= 0:
        raise ValueError("quantity must be positive")
    reduces = (position_micros > 0 and side is ShadowSide.SELL) or (
        position_micros < 0 and side is ShadowSide.BUY
    )
    reduce_quantity = min(abs(position_micros), quantity_micros) if reduces else 0
    return reduce_quantity, quantity_micros - reduce_quantity


def worst_case_bounds(
    position_micros: int, reserved_buys_micros: int, reserved_sells_micros: int
) -> tuple[int, int]:
    return position_micros - reserved_sells_micros, position_micros + reserved_buys_micros


def binary_exposure_cash_micros(quantity_micros: int, price_nanos: int) -> int:
    if quantity_micros >= 0:
        numerator = quantity_micros * price_nanos
    else:
        numerator = abs(quantity_micros) * (PRICE_SCALE - price_nanos)
    return (numerator + PRICE_SCALE - 1) // PRICE_SCALE


def check_order(
    order: ShadowOrder,
    *,
    positions: Mapping[str, int],
    reservations: Mapping[str, tuple[int, int]],
    reserved_exposure: Mapping[str, int] | None = None,
    marks: Mapping[str, int],
    limits: ShadowRiskLimits,
) -> RiskDecision:
    current = positions.get(order.market_id, 0)
    buys, sells = reservations.get(order.market_id, (0, 0))
    if order.reduce_only:
        if current > 0 and order.side is ShadowSide.SELL:
            closeable = max(0, current - sells)
        elif current < 0 and order.side is ShadowSide.BUY:
            closeable = max(0, abs(current) - buys)
        else:
            closeable = 0
        if order.quantity_micros > closeable:
            return RiskDecision(False, "reduce_only_would_open_or_flip")
        # A valid close can never increase worst-case risk. It remains blocked by
        # feed/breaker/integrity gates in the engine, but bypasses ordinary caps.
        return RiskDecision(True, "accepted_reduce_only")
    if order.side is ShadowSide.BUY:
        buys += order.quantity_micros
    else:
        sells += order.quantity_micros
    low, high = worst_case_bounds(current, buys, sells)
    if max(abs(low), abs(high)) > limits.max_position_micros:
        return RiskDecision(False, "max_position_exceeded")

    markets = set(positions) | set(reservations) | {order.market_id}
    open_count = 0
    total = 0
    for market_id in markets:
        position = positions.get(market_id, 0)
        market_buys, market_sells = reservations.get(market_id, (0, 0))
        if market_id == order.market_id:
            market_buys, market_sells = buys, sells
        qlow, qhigh = worst_case_bounds(position, market_buys, market_sells)
        if qlow or qhigh:
            open_count += 1
        if (position or market_buys or market_sells) and market_id not in marks:
            return RiskDecision(False, f"missing_mark:{market_id}")
        mark = marks.get(market_id)
        if mark is None:
            # The candidate has no inventory yet; its executable price below is
            # sufficient. Use zero only for the zero-valued position term.
            mark = 0
        position_exposure = binary_exposure_cash_micros(position, mark)
        pending_exposure = (
            reserved_exposure.get(market_id, 0)
            if reserved_exposure is not None
            else market_buys + market_sells
        )
        if market_id == order.market_id:
            price = order.limit_price_nanos
            if price is None:
                price = PRICE_SCALE if order.side is ShadowSide.BUY else 0
            pending_exposure += binary_exposure_cash_micros(
                order.quantity_micros * order.side.sign, price
            )
        total += position_exposure + pending_exposure
    if open_count > limits.max_open_markets:
        return RiskDecision(False, "max_open_markets_exceeded")
    if total > limits.max_total_exposure_cash_micros:
        return RiskDecision(False, "max_total_exposure_exceeded")
    return RiskDecision(True, "accepted")
