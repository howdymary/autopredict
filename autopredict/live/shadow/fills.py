"""Deterministic displayed-depth and later-trade shadow fill model."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from .contracts import (
    BookLevel,
    BookObservation,
    ShadowFill,
    ShadowOrder,
    ShadowOrderType,
    ShadowSide,
    TradePrint,
    stable_id,
)


class DeterministicFillModel:
    """No-RNG model: cross displayed depth now; rest only on later prints."""

    def submit(
        self, order: ShadowOrder, book: BookObservation
    ) -> tuple[tuple[ShadowFill, ...], int, int]:
        levels = book.asks if order.side is ShadowSide.BUY else book.bids
        fills: list[ShadowFill] = []
        remaining = order.quantity_micros
        for index, level in enumerate(levels):
            if not self._crosses(order, level):
                break
            quantity = min(remaining, level.quantity_micros)
            fills.append(
                self._fill(
                    order,
                    quantity=quantity,
                    price=level.price_nanos,
                    source=f"{book.event_id}:depth:{index}",
                    at=book.observed_at,
                )
            )
            remaining -= quantity
            if remaining == 0:
                break
        # Market and crossing limit orders are IOC. Only a non-crossing limit may rest.
        resting = remaining if order.order_type is ShadowOrderType.LIMIT and not fills else 0
        queue = self._queue_ahead(order, book) if resting else 0
        return tuple(fills), resting, queue

    def apply_trade(
        self, trade: TradePrint, open_orders: Iterable[Mapping[str, Any]]
    ) -> tuple[tuple[ShadowFill, ...], dict[str, int]]:
        available = trade.quantity_micros
        fills: list[ShadowFill] = []
        queues: dict[str, int] = {}
        for row in sorted(
            open_orders, key=lambda item: (item["created_at"], item["client_order_id"])
        ):
            if available <= 0 or row["market_id"] != trade.market_id:
                continue
            created_at = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
            if created_at >= trade.executed_at:
                continue
            side = ShadowSide(row["side"])
            limit = row["limit_price_nanos"]
            eligible = (
                side is ShadowSide.BUY
                and trade.side is ShadowSide.SELL
                and limit >= trade.price_nanos
            ) or (
                side is ShadowSide.SELL
                and trade.side is ShadowSide.BUY
                and limit <= trade.price_nanos
            )
            if not eligible:
                continue
            queue = int(row["queue_ahead_micros"])
            consumed_queue = min(queue, available)
            queue -= consumed_queue
            available -= consumed_queue
            queues[row["client_order_id"]] = queue
            if queue or available <= 0:
                continue
            quantity = min(int(row["remaining_micros"]), available)
            order = _order_from_row(row, created_at)
            fills.append(
                self._fill(
                    order,
                    quantity=quantity,
                    price=trade.price_nanos,
                    source=trade.event_id,
                    at=trade.observed_at,
                )
            )
            available -= quantity
        return tuple(fills), queues

    @staticmethod
    def _crosses(order: ShadowOrder, level: BookLevel) -> bool:
        if order.order_type is ShadowOrderType.MARKET:
            return True
        assert order.limit_price_nanos is not None
        if order.side is ShadowSide.BUY:
            return order.limit_price_nanos >= level.price_nanos
        return order.limit_price_nanos <= level.price_nanos

    @staticmethod
    def _queue_ahead(order: ShadowOrder, book: BookObservation) -> int:
        assert order.limit_price_nanos is not None
        same_side = book.bids if order.side is ShadowSide.BUY else book.asks
        return sum(
            level.quantity_micros
            for level in same_side
            if level.price_nanos == order.limit_price_nanos
        )

    @staticmethod
    def _fill(
        order: ShadowOrder, *, quantity: int, price: int, source: str, at: datetime
    ) -> ShadowFill:
        identity = {
            "client_order_id": order.client_order_id,
            "quantity_micros": quantity,
            "price_nanos": price,
            "source_event_id": source,
        }
        return ShadowFill(
            fill_id=stable_id("shadow-fill", identity),
            client_order_id=order.client_order_id,
            market_id=order.market_id,
            side=order.side,
            quantity_micros=quantity,
            price_nanos=price,
            source_event_id=source,
            filled_at=at,
        )


def _order_from_row(row: Mapping[str, Any], created_at: datetime) -> ShadowOrder:
    return ShadowOrder(
        client_order_id=row["client_order_id"],
        decision_id=row["decision_id"],
        market_id=row["market_id"],
        side=ShadowSide(row["side"]),
        order_type=ShadowOrderType(row["order_type"]),
        quantity_micros=row["quantity_micros"],
        limit_price_nanos=row["limit_price_nanos"],
        reduce_only=bool(row["reduce_only"]),
        created_at=created_at,
    )
