"""Provider-to-strategy shadow engine with durable, fail-closed execution."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

from autopredict.config.shadow import ShadowConfig
from autopredict.core.types import (
    MarketCategory,
    MarketState,
    Order,
    OrderSide,
    OrderType,
    Portfolio,
    Position,
)
from autopredict.forecasting import (
    ForecastAbstention,
    ForecastOrderBook,
    ForecastPriceLevel,
    ForecastProvider,
    ForecastRequest,
    ForecastResult,
    ObservationProvenance,
    invoke_provider,
)
from autopredict.prediction_market import (
    MarketSignal,
    MarketSnapshot,
    PredictionMarketStrategy,
    StrategyContext,
    VenueConfig,
    VenueName,
)

from .clock import ReplayClock, ShadowClock
from .contracts import (
    PRICE_SCALE,
    QUANTITY_SCALE,
    BookObservation,
    BreakerReason,
    FeedFault,
    FeedMarker,
    ShadowFeedEvent,
    ShadowOrder,
    ShadowOrderType,
    ShadowSide,
    TradePrint,
    canonical_json,
    from_fixed,
    stable_id,
    to_fixed,
    utc_text,
)
from .fills import DeterministicFillModel
from .risk import check_order, split_reduce_open
from .store import ShadowStateStore


class ShadowEdgeStrategy:
    """Small maintained strategy that turns a provider edge into one marketable limit."""

    name = "shadow_edge_v1"

    def __init__(self, *, min_edge: float, quantity: float) -> None:
        self.min_edge = min_edge
        self.quantity = quantity

    def generate_signal(
        self, snapshot: MarketSnapshot, context: StrategyContext
    ) -> MarketSignal | None:
        del snapshot, context
        raise RuntimeError("ShadowEngine supplies the typed forecast signal directly")

    def build_orders(
        self, snapshot: MarketSnapshot, signal: MarketSignal, context: StrategyContext
    ) -> list[Order]:
        del context
        edge = signal.edge_against(snapshot.market.market_prob)
        if abs(edge) < self.min_edge:
            return []
        side = OrderSide.BUY if edge > 0 else OrderSide.SELL
        price = snapshot.market.best_ask if side is OrderSide.BUY else snapshot.market.best_bid
        return [
            Order(
                market_id=snapshot.market_id,
                side=side,
                order_type=OrderType.LIMIT,
                size=self.quantity,
                limit_price=price,
                timestamp=snapshot.observed_at,
                metadata={"reduce_only": False, "strategy": self.name},
            )
        ]


class ShadowEngine:
    def __init__(
        self,
        *,
        config: ShadowConfig,
        store: ShadowStateStore,
        clock: ShadowClock,
        provider: ForecastProvider,
        strategy: PredictionMarketStrategy,
        fill_model: DeterministicFillModel | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.clock = clock
        self.provider = provider
        self.strategy = strategy
        self.fill_model = fill_model or DeterministicFillModel()
        self.marks: dict[str, int] = {}

    def reconcile_startup(self) -> None:
        self.store.reconcile_startup()
        self._check_daily_loss()

    def run(self, events: Any) -> int:
        processed = 0
        for event in events:
            if isinstance(self.clock, ReplayClock):
                self.clock.advance_to(event.observed_at)
            self.process(event)
            processed += 1
        return processed

    def process(self, event: ShadowFeedEvent) -> None:
        payload = _event_payload(event)
        cursor = self.store.feed_cursor()
        try:
            inserted = self.store.record_feed_event(
                event_id=event.event_id,
                capture_sequence=event.capture_sequence,
                event_type=type(event).__name__,
                observed_at=event.observed_at,
                payload=payload,
            )
        except Exception as exc:
            self._break(BreakerReason.INTEGRITY, str(exc))
            raise
        if inserted and cursor and event.capture_sequence != cursor["capture_sequence"] + 1:
            self._break(BreakerReason.GAP, "non-contiguous capture sequence")
            return
        if isinstance(event, FeedFault):
            self._break(event.reason, event.detail)
            return
        if isinstance(event, FeedMarker):
            return
        if self.store.breaker()["breaker_active"]:
            return
        if isinstance(event, TradePrint):
            self._process_trade(event)
            return
        self._process_book(event)

    def _process_book(self, book: BookObservation) -> None:
        age = (self.clock.now() - book.observed_at).total_seconds()
        if age < 0:
            self._break(BreakerReason.OUT_OF_ORDER, "observation is in the future")
            return
        if age > self.config.stale_after_seconds:
            self._break(BreakerReason.STALE, f"observation age {age:.3f}s exceeds limit")
            return
        if book.reconnected:
            self._break(BreakerReason.RECONNECT, "feed reconnected")
            return
        self.marks[book.market_id] = book.market_probability_nanos
        request = _forecast_request(book)
        decision_key = stable_id(
            "shadow-decision-key",
            {
                "feed_event_id": book.event_id,
                "provider": self.provider.provenance.to_dict(),
                "strategy": _strategy_identity(self.strategy),
            },
        )
        decision_id = stable_id("shadow-decision", {"decision_key": decision_key})
        stored = self.store.decision_by_key(decision_key)
        if stored and stored["status"] != "approved":
            return
        if stored:
            probability = float(stored["payload"]["forecast_probability"])
            confidence = float(stored["payload"]["confidence"])
            provider_identity = stored["payload"]["provider"]
        else:
            try:
                forecast = invoke_provider(self.provider, request)
            except Exception as exc:
                self.store.record_decision(
                    decision_id=decision_id,
                    decision_key=decision_key,
                    status="provider_error",
                    payload={"error_type": type(exc).__name__},
                    at=book.observed_at,
                )
                self._break(BreakerReason.ERROR, f"provider failed: {type(exc).__name__}")
                return
            if isinstance(forecast, ForecastAbstention):
                self.store.record_decision(
                    decision_id=decision_id,
                    decision_key=decision_key,
                    status="abstained",
                    payload={"reason": forecast.reason, "provider": forecast.provenance.to_dict()},
                    at=book.observed_at,
                )
                return
            assert isinstance(forecast, ForecastResult)
            probability = forecast.probability
            confidence = forecast.confidence
            provider_identity = forecast.provenance.to_dict()
        signal = MarketSignal(
            fair_prob=probability,
            confidence=confidence,
            rationale="typed forecast provider output",
            metadata={"provider": provider_identity},
        )
        snapshot, context = self._strategy_context(book)
        try:
            candidate_orders = self.strategy.build_orders(snapshot, signal, context)
        except Exception as exc:
            self._break(BreakerReason.ERROR, f"strategy failed: {type(exc).__name__}")
            return
        decision_payload = {
            "forecast_probability": probability,
            "confidence": confidence,
            "order_count": len(candidate_orders),
            "provider": provider_identity,
            "strategy": _strategy_identity(self.strategy),
        }
        self.store.record_decision(
            decision_id=decision_id,
            decision_key=decision_key,
            status="approved" if candidate_orders else "hold",
            payload=decision_payload,
            at=book.observed_at,
        )
        for order_index, candidate in enumerate(candidate_orders):
            self._submit_candidate(
                candidate,
                decision_id=decision_id,
                order_index=order_index,
                book=book,
            )

    def _submit_candidate(
        self, candidate: Order, *, decision_id: str, order_index: int, book: BookObservation
    ) -> None:
        if candidate.market_id != book.market_id:
            self._break(BreakerReason.ERROR, "strategy order market mismatch")
            return
        side = ShadowSide(candidate.side.value)
        quantity = to_fixed(candidate.size, QUANTITY_SCALE, field="order size")
        current = self.store.positions().get(book.market_id, 0)
        reduce_quantity, open_quantity = split_reduce_open(
            position_micros=current,
            side=side,
            quantity_micros=quantity,
        )
        parts = [(reduce_quantity, True), (open_quantity, False)]
        for part_index, (part_quantity, reduce_only) in enumerate(parts):
            if not part_quantity:
                continue
            limit = (
                to_fixed(candidate.limit_price, PRICE_SCALE, field="limit price")
                if candidate.limit_price is not None
                else None
            )
            identity = {
                "schema": "autopredict.shadow.order.v1",
                "venue": "polymarket",
                "decision_id": decision_id,
                "order_index": order_index,
                "part_index": part_index,
                "market_id": book.market_id,
                "side": side.value,
                "order_type": candidate.order_type.value,
                "quantity_micros": part_quantity,
                "limit_price_nanos": limit,
                "reduce_only": reduce_only,
                "provider": self.provider.provenance.to_dict(),
                "strategy": self.strategy.name,
            }
            order = ShadowOrder(
                client_order_id=stable_id("shadow-order", identity),
                decision_id=decision_id,
                market_id=book.market_id,
                side=side,
                order_type=ShadowOrderType(candidate.order_type.value),
                quantity_micros=part_quantity,
                limit_price_nanos=limit,
                reduce_only=reduce_only,
                created_at=book.observed_at,
            )
            rejection_id = stable_id("shadow-rejection", identity)
            if self.store.rejection(rejection_id) is not None:
                continue
            risk = check_order(
                order,
                positions=self.store.positions(),
                reservations=self.store.reservations(),
                reserved_exposure=self.store.reservation_exposure(),
                marks=self.marks,
                limits=self.config.risk_limits,
            )
            if not risk.accepted:
                rejection_payload = {
                    "order_identity": identity,
                    "positions": self.store.positions(),
                    "reservations": self.store.reservations(),
                }
                self.store.record_rejection(
                    rejection_id=rejection_id,
                    decision_id=decision_id,
                    reason=risk.reason,
                    payload=rejection_payload,
                    at=book.observed_at,
                )
                continue
            fills, resting, queue = self.fill_model.submit(order, book)
            self.store.submit_order(order, queue_ahead_micros=queue)
            for fill in fills:
                self.store.apply_fill(fill)
                self._check_daily_loss()
                if self.store.breaker()["breaker_active"]:
                    break
            if not resting:
                self.store.cancel_order(
                    order.client_order_id,
                    at=book.observed_at,
                    reason="ioc_unfilled_remainder",
                )

    def _process_trade(self, trade: TradePrint) -> None:
        if self.store.trade_application(trade.event_id) is not None:
            # The allocation and its accounting commit atomically, while the
            # breaker latch is deliberately a subsequent durable action.  A
            # crash between them must therefore be healed on replay.
            self._check_daily_loss()
            return
        fills, queues = self.fill_model.apply_trade(
            trade, [dict(row) for row in self.store.open_orders(trade.market_id)]
        )
        self.store.apply_trade_plan(
            source_event_id=trade.event_id,
            queue_changes=queues,
            fills=fills,
            at=trade.observed_at,
        )
        self._check_daily_loss()

    def _check_daily_loss(self) -> None:
        limit = self.config.risk_limits.max_daily_loss_cash_micros
        if not limit:
            return
        realized = sum(
            detail["realized_pnl_cash_micros"] for detail in self.store.position_details().values()
        )
        if realized <= -limit and not self.store.breaker()["breaker_active"]:
            self._break(
                BreakerReason.DAILY_LOSS,
                f"realized P&L {realized} breached daily loss limit {-limit}",
            )

    def _strategy_context(self, book: BookObservation) -> tuple[MarketSnapshot, StrategyContext]:
        category = (
            MarketCategory(book.category.lower())
            if book.category.lower() in {item.value for item in MarketCategory}
            else MarketCategory.OTHER
        )
        market = MarketState(
            market_id=book.market_id,
            question=book.question,
            market_prob=float(from_fixed(book.market_probability_nanos, PRICE_SCALE)),
            expiry=book.expiry,
            category=category,
            best_bid=float(from_fixed(book.bids[0].price_nanos, PRICE_SCALE)),
            best_ask=float(from_fixed(book.asks[0].price_nanos, PRICE_SCALE)),
            bid_liquidity=float(sum(level.quantity_micros for level in book.bids) / QUANTITY_SCALE),
            ask_liquidity=float(sum(level.quantity_micros for level in book.asks) / QUANTITY_SCALE),
        )
        positions: dict[str, Position] = {}
        for market_id, detail in self.store.position_details().items():
            if detail["quantity_micros"]:
                positions[market_id] = Position(
                    market_id=market_id,
                    size=detail["quantity_micros"] / QUANTITY_SCALE,
                    entry_price=detail["avg_entry_price_nanos"] / PRICE_SCALE,
                    current_price=self.marks.get(market_id, detail["mark_price_nanos"])
                    / PRICE_SCALE,
                )
        portfolio = Portfolio(cash=0.0, positions=positions, starting_capital=0.0)
        snapshot = MarketSnapshot(
            market=market,
            venue=VenueConfig(name=VenueName.POLYMARKET),
            observed_at=book.observed_at,
            features={},
            labels={},
        )
        return snapshot, StrategyContext(
            portfolio=portfolio,
            position=positions.get(book.market_id),
            metadata={"shadow": True},
        )

    def cancel_all(self, *, reason: str) -> int:
        return self.store.cancel_all(at=self.clock.now(), reason=reason)

    def _break(self, reason: BreakerReason, detail: str) -> None:
        self.store.latch_breaker(reason=reason.value, detail=detail, at=self.clock.now())


def _forecast_request(book: BookObservation) -> ForecastRequest:
    return ForecastRequest(
        record_id=book.event_id,
        event_id=book.event_market_id,
        market_id=book.market_id,
        question=book.question,
        category=book.category,
        observed_at=book.observed_at,
        expiry=book.expiry,
        market_probability=float(from_fixed(book.market_probability_nanos, PRICE_SCALE)),
        order_book=ForecastOrderBook(
            bids=tuple(
                ForecastPriceLevel(
                    price=float(from_fixed(level.price_nanos, PRICE_SCALE)),
                    size=float(from_fixed(level.quantity_micros, QUANTITY_SCALE)),
                )
                for level in book.bids
            ),
            asks=tuple(
                ForecastPriceLevel(
                    price=float(from_fixed(level.price_nanos, PRICE_SCALE)),
                    size=float(from_fixed(level.quantity_micros, QUANTITY_SCALE)),
                )
                for level in book.asks
            ),
        ),
        provenance=ObservationProvenance(
            source=book.source,
            source_record_id=book.source_record_id,
        ),
    )


def _event_payload(event: ShadowFeedEvent) -> dict[str, Any]:
    if isinstance(event, BookObservation):
        return {
            "event_market_id": event.event_market_id,
            "market_id": event.market_id,
            "question": event.question,
            "category": event.category,
            "observed_at": utc_text(event.observed_at),
            "expiry": utc_text(event.expiry),
            "market_probability_nanos": event.market_probability_nanos,
            "source": event.source,
            "source_record_id": event.source_record_id,
            "reconnected": event.reconnected,
            "bids": [[level.price_nanos, level.quantity_micros] for level in event.bids],
            "asks": [[level.price_nanos, level.quantity_micros] for level in event.asks],
        }
    if isinstance(event, TradePrint):
        return {
            "trade_id": event.trade_id,
            "market_id": event.market_id,
            "side": event.side.value,
            "price_nanos": event.price_nanos,
            "quantity_micros": event.quantity_micros,
            "executed_at": utc_text(event.executed_at),
        }
    if isinstance(event, FeedFault):
        return {"reason": event.reason.value, "detail": event.detail}
    return {"kind": event.kind}


def _strategy_identity(strategy: PredictionMarketStrategy) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for key, value in sorted(vars(strategy).items()):
        if key.startswith("_"):
            continue
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("shadow strategy configuration must use scalar JSON values")
        config[key] = value
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "name": strategy.name,
        "implementation": f"{type(strategy).__module__}.{type(strategy).__qualname__}",
        "config_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }
