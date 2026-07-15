"""Acceptance matrix for durable deterministic shadow execution."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest

from autopredict.config.shadow import ShadowConfig, load_shadow_config
from autopredict.core.types import Order, OrderSide, OrderType
from autopredict.forecasting import CallableForecastProvider, ForecastResult
from autopredict.live.shadow import (
    BookLevel,
    BookObservation,
    BreakerReason,
    CaptureReplayFeed,
    DeterministicFillModel,
    FeedFault,
    FeedMarker,
    ReplayClock,
    ShadowEngine,
    ShadowFill,
    ShadowIntegrityError,
    ShadowOrder,
    ShadowOrderType,
    ShadowRiskLimits,
    ShadowSide,
    ShadowStateStore,
    ShadowValidationError,
    TradePrint,
)
from autopredict.live.shadow.risk import check_order

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
CAPTURE = Path(__file__).parent / "fixtures/recording/polymarket-v1/manifest.json"


def _book(sequence: int = 1, event_id: str = "event-1") -> BookObservation:
    return BookObservation(
        event_id=event_id,
        capture_sequence=sequence,
        market_id="market-1",
        event_market_id="event-market-1",
        question="Will it happen?",
        category="politics",
        observed_at=NOW + timedelta(seconds=sequence),
        expiry=NOW + timedelta(days=1),
        market_probability_nanos=500_000_000,
        bids=(BookLevel(490_000_000, 10_000_000),),
        asks=(BookLevel(510_000_000, 10_000_000),),
        source="fixture",
        source_record_id=event_id,
    )


def _config(tmp_path: Path) -> ShadowConfig:
    return ShadowConfig(
        state_path=tmp_path / "shadow.db",
        capture_manifest=CAPTURE,
        provider="market-baseline",
        min_edge=0.01,
        order_quantity_micros=1_000_000,
        stale_after_seconds=30,
        risk_limits=ShadowRiskLimits(100_000_000, 100_000_000, 10),
    )


class FixedStrategy:
    name = "fixed-test"

    def __init__(self, *, side: str = "buy", price: float = 0.51, size: float = 2.0) -> None:
        self.side = side
        self.price = price
        self.size = size

    def generate_signal(self, snapshot, context):
        raise AssertionError("engine must supply provider signal")

    def build_orders(self, snapshot, signal, context):
        del signal, context
        return [
            Order(
                market_id=snapshot.market_id,
                side=OrderSide(self.side),
                order_type=OrderType.LIMIT,
                size=self.size,
                limit_price=self.price,
                timestamp=snapshot.observed_at,
            )
        ]


def _provider(book: BookObservation):
    provider = None

    def callback(request):
        return ForecastResult(
            probability=0.75,
            confidence=0.9,
            as_of=request.observed_at,
            provenance=provider.provenance,
        )

    provider = CallableForecastProvider(
        callback=callback, name="fixed", version="1", config={"probability": 0.75}
    )
    return provider


def _engine(tmp_path: Path, *, strategy=None):
    book = _book()
    store = ShadowStateStore.open(tmp_path / "state.db")
    store.start_run(
        run_id="test-run",
        at=book.observed_at,
        config_sha256="a" * 64,
        provider_sha256="b" * 64,
    )
    engine = ShadowEngine(
        config=_config(tmp_path),
        store=store,
        clock=ReplayClock(book.observed_at),
        provider=_provider(book),
        strategy=strategy or FixedStrategy(),
    )
    return book, store, engine


def _leased_store(tmp_path: Path, name: str = "direct") -> ShadowStateStore:
    store = ShadowStateStore.open(tmp_path / f"{name}.db")
    store.start_run(
        run_id=name,
        at=NOW,
        config_sha256="a" * 64,
        provider_sha256="b" * 64,
    )
    return store


def test_contracts_reject_bool_float_and_untyped_enums() -> None:
    with pytest.raises(ShadowValidationError, match="integer"):
        BookLevel(0.5, 1)
    with pytest.raises(ShadowValidationError, match="integer"):
        BookLevel(1, True)
    order = ShadowOrder("o", "d", "m", ShadowSide.BUY, ShadowOrderType.MARKET, 1, None, False, NOW)
    with pytest.raises(ShadowValidationError, match="boolean"):
        replace(order, reduce_only=1)
    with pytest.raises(ShadowValidationError, match="non-empty"):
        replace(order, client_order_id="   ")
    with pytest.raises(ShadowValidationError, match="datetime"):
        replace(order, created_at="2026-01-01T00:00:00Z")


def test_capture_replay_preserves_every_sequence_and_source_time() -> None:
    events = list(CaptureReplayFeed(CAPTURE).events())
    assert [event.capture_sequence for event in events] == list(range(1, 7))
    trade = next(event for event in events if isinstance(event, TradePrint))
    assert trade.executed_at < trade.observed_at


def test_engine_walks_depth_and_restart_is_exactly_once(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path)
    engine.process(book)
    assert store.positions()[book.market_id] == 2_000_000
    first_hash = store.state_sha256()
    engine.process(book)
    assert store.positions()[book.market_id] == 2_000_000
    assert store.state_sha256() == first_hash
    store.close()


def test_crash_after_order_before_fill_recovers_without_provider_call(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path)
    original = store.apply_fill
    calls = 0

    def crash_once(fill):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("crash")
        return original(fill)

    store.apply_fill = crash_once
    with pytest.raises(RuntimeError, match="crash"):
        engine.process(book)
    store.apply_fill = original

    original_provider = engine.provider

    class ForbiddenProvider:
        provenance = original_provider.provenance

        def forecast(self, _request):
            raise AssertionError("provider was re-invoked")

    engine.provider = ForbiddenProvider()
    engine.process(book)
    assert store.positions()[book.market_id] == 2_000_000
    store.close()


def test_passive_fill_requires_later_trade_and_consumes_queue(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path, strategy=FixedStrategy(price=0.49, size=12.0))
    engine.process(book)
    order = store.open_orders()[0]
    assert order["queue_ahead_micros"] == 10_000_000
    trade = TradePrint(
        event_id="trade-event",
        capture_sequence=2,
        trade_id="trade-1",
        market_id=book.market_id,
        observed_at=book.observed_at + timedelta(seconds=2),
        executed_at=book.observed_at + timedelta(seconds=1),
        side=ShadowSide.SELL,
        price_nanos=490_000_000,
        quantity_micros=11_000_000,
    )
    engine.process(trade)
    assert store.positions()[book.market_id] == 1_000_000
    first_hash = store.state_sha256()
    engine.process(trade)
    assert store.positions()[book.market_id] == 1_000_000
    assert store.state_sha256() == first_hash
    store.close()


def test_trade_captured_later_but_executed_before_order_cannot_fill(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path, strategy=FixedStrategy(price=0.49))
    engine.process(book)
    trade = TradePrint(
        "trade-event",
        2,
        "old",
        book.market_id,
        book.observed_at + timedelta(seconds=2),
        book.observed_at - timedelta(seconds=1),
        ShadowSide.SELL,
        490_000_000,
        100_000_000,
    )
    engine.process(trade)
    assert store.positions().get(book.market_id, 0) == 0
    store.close()


def test_reduce_only_accounts_for_pending_closes_and_bypasses_caps() -> None:
    limits = ShadowRiskLimits(1, 1, 1)
    first = ShadowOrder(
        "1", "d", "m", ShadowSide.SELL, ShadowOrderType.LIMIT, 6, 500_000_000, True, NOW
    )
    second = replace(first, client_order_id="2", quantity_micros=5)
    assert check_order(
        first, positions={"m": 10}, reservations={}, marks={"m": 500_000_000}, limits=limits
    ).accepted
    assert not check_order(
        second,
        positions={"m": 10},
        reservations={"m": (0, 6)},
        marks={"m": 500_000_000},
        limits=limits,
    ).accepted


def test_pending_limit_price_is_reserved_conservatively() -> None:
    order = ShadowOrder(
        "1", "d", "m", ShadowSide.BUY, ShadowOrderType.LIMIT, 100, 1_000_000_000, False, NOW
    )
    result = check_order(
        order,
        positions={},
        reservations={},
        reserved_exposure={},
        marks={"m": 0},
        limits=ShadowRiskLimits(1000, 10, 2),
    )
    assert not result.accepted


def test_projection_tamper_is_repaired_but_authoritative_tamper_fails(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path)
    engine.process(book)
    store.connection.execute("UPDATE positions SET quantity_micros=999")
    store.reconcile()
    assert store.positions()[book.market_id] == 2_000_000
    store.connection.execute("UPDATE orders SET quantity_micros=999")
    with pytest.raises(ShadowIntegrityError, match="contradicts intent"):
        store.reconcile()
    store.close()


def test_writer_fencing_rejects_second_and_expired_owner(tmp_path: Path) -> None:
    lease_now = [NOW]
    clock = lambda: lease_now[0]
    first = ShadowStateStore.open(tmp_path / "state.db", lease_clock=clock)
    second = ShadowStateStore.open(tmp_path / "state.db", lease_clock=clock)
    first.start_run(run_id="a", at=NOW, config_sha256="a", provider_sha256="b", lease_seconds=1)
    with pytest.raises(ShadowIntegrityError, match="another"):
        second.start_run(run_id="a", at=NOW, config_sha256="a", provider_sha256="b")
    lease_now[0] = NOW + timedelta(seconds=2)
    with pytest.raises(ShadowIntegrityError, match="expired"):
        first.renew_lease("a", at=NOW + timedelta(seconds=2))
    second.start_run(
        run_id="b", at=NOW + timedelta(seconds=2), config_sha256="a", provider_sha256="b"
    )
    with pytest.raises(ShadowIntegrityError, match="fencing"):
        first.record_feed_event(
            event_id="e", capture_sequence=1, event_type="x", observed_at=NOW, payload={}
        )
    second.end_run("b", NOW + timedelta(seconds=2))
    with pytest.raises(ShadowIntegrityError, match="missing"):
        first.cancel_all(at=NOW + timedelta(seconds=2), reason="stale writer")
    first.close()
    second.close()


def test_feed_gap_latches_breaker_and_cancel_all_is_idempotent(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path, strategy=FixedStrategy(price=0.49))
    engine.process(book)
    assert len(store.open_orders()) == 1
    fault = FeedFault("gap", 2, book.observed_at + timedelta(seconds=1), BreakerReason.GAP, "lost")
    engine.process(fault)
    assert store.breaker()["breaker_active"] == 1
    assert store.cancel_all(at=fault.observed_at, reason="repeat") == 0
    store.close()


def test_stale_observation_fails_closed(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path)
    engine.clock.advance_to(book.observed_at + timedelta(seconds=31))
    engine.process(book)
    assert store.breaker()["breaker_reason"] == "stale"
    assert not store.open_orders()
    store.close()


def test_realized_daily_loss_latches_and_cancels(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path)
    engine.config = replace(
        engine.config,
        risk_limits=replace(engine.config.risk_limits, max_daily_loss_cash_micros=10_000),
    )
    engine.process(book)
    engine.strategy = FixedStrategy(side="sell", price=0.49, size=2.0)
    second = _book(sequence=2, event_id="event-2")
    engine.clock.advance_to(second.observed_at)
    engine.process(second)
    assert store.breaker()["breaker_reason"] == "daily_loss"
    assert not store.open_orders()
    store.close()


def test_applied_trade_replay_heals_crash_before_daily_loss_latch(tmp_path: Path) -> None:
    book, store, engine = _engine(
        tmp_path, strategy=FixedStrategy(side="buy", price=0.51, size=1.0)
    )
    engine.config = replace(
        engine.config,
        risk_limits=replace(engine.config.risk_limits, max_daily_loss_cash_micros=10_000),
    )
    engine.process(book)

    engine.strategy = FixedStrategy(side="sell", price=0.49, size=1.0)
    second = replace(
        _book(sequence=2, event_id="event-2"),
        bids=(BookLevel(480_000_000, 10_000_000),),
        asks=(BookLevel(520_000_000, 10_000_000),),
    )
    engine.clock.advance_to(second.observed_at)
    engine.process(second)
    trade = TradePrint(
        "loss-trade",
        3,
        "loss-trade-id",
        book.market_id,
        NOW + timedelta(seconds=3),
        NOW + timedelta(seconds=2, milliseconds=500),
        ShadowSide.BUY,
        490_000_000,
        1_000_000,
    )
    engine.clock.advance_to(trade.observed_at)
    original = store.apply_trade_plan

    def crash_after_apply(**kwargs):
        original(**kwargs)
        raise RuntimeError("crash after trade apply")

    store.apply_trade_plan = crash_after_apply
    with pytest.raises(RuntimeError, match="crash after trade apply"):
        engine.process(trade)
    store.apply_trade_plan = original
    assert store.position_details()[book.market_id]["realized_pnl_cash_micros"] == -20_000
    assert store.breaker()["breaker_active"] == 0

    engine.process(trade)
    assert store.breaker()["breaker_reason"] == "daily_loss"
    store.close()


def test_shadow_config_rejects_credentials_before_env_expansion(tmp_path: Path) -> None:
    path = tmp_path / "shadow.yaml"
    path.write_text(
        "schema_version: autopredict.shadow.config.v1\nmode: shadow\nstate_path: x\n"
        "capture_manifest: y\napi_key: ${DANGER}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="credential-bearing"):
        load_shadow_config(path)


def test_shadow_feed_has_no_network_or_order_capability_surface() -> None:
    forbidden = {
        "submit_order",
        "place_order",
        "create_order",
        "post_order",
        "get_api_keys",
        "get_balance",
        "get_position",
        "validate_credentials",
    }
    assert all(not hasattr(CaptureReplayFeed, name) for name in forbidden)


def test_accounting_handles_close_and_reversal(tmp_path: Path) -> None:
    store = ShadowStateStore.open(tmp_path / "state.db")
    store.start_run(
        run_id="accounting",
        at=NOW,
        config_sha256="a" * 64,
        provider_sha256="b" * 64,
    )
    store.record_feed_event(
        event_id="feed",
        capture_sequence=1,
        event_type="BookObservation",
        observed_at=NOW,
        payload={"market_id": "m"},
    )
    store.record_decision(decision_id="d", decision_key="k", status="approved", payload={}, at=NOW)
    buy = ShadowOrder("buy", "d", "m", ShadowSide.BUY, ShadowOrderType.MARKET, 10, None, False, NOW)
    store.submit_order(buy)
    store.apply_fill(
        ShadowFill("f1", "buy", "m", ShadowSide.BUY, 10, 400_000_000, "feed:depth:0", NOW)
    )
    sell = ShadowOrder(
        "sell", "d", "m", ShadowSide.SELL, ShadowOrderType.MARKET, 15, None, False, NOW
    )
    store.submit_order(sell)
    store.apply_fill(
        ShadowFill("f2", "sell", "m", ShadowSide.SELL, 15, 600_000_000, "feed:depth:0", NOW)
    )
    detail = store.position_details()["m"]
    assert detail["quantity_micros"] == -5
    assert detail["avg_entry_price_nanos"] == 600_000_000
    assert detail["realized_pnl_cash_micros"] == 2
    store.close()


def test_trade_plan_is_atomic_across_two_orders_and_crash(tmp_path: Path) -> None:
    store = _leased_store(tmp_path, "atomic")
    book = _book()
    store.record_feed_event(
        event_id=book.event_id,
        capture_sequence=1,
        event_type="BookObservation",
        observed_at=book.observed_at,
        payload={"market_id": book.market_id},
    )
    store.record_decision(
        decision_id="decision",
        decision_key="decision-key",
        status="approved",
        payload={},
        at=book.observed_at,
    )
    for index in range(2):
        store.submit_order(
            ShadowOrder(
                f"order-{index}",
                "decision",
                book.market_id,
                ShadowSide.BUY,
                ShadowOrderType.LIMIT,
                10_000_000,
                480_000_000,
                False,
                book.observed_at,
            )
        )
    trade = TradePrint(
        "trade-event",
        2,
        "trade-id",
        book.market_id,
        book.observed_at + timedelta(seconds=2),
        book.observed_at + timedelta(seconds=1),
        ShadowSide.SELL,
        480_000_000,
        15_000_000,
    )
    store.record_feed_event(
        event_id=trade.event_id,
        capture_sequence=2,
        event_type="TradePrint",
        observed_at=trade.observed_at,
        payload={"market_id": trade.market_id},
    )
    model = DeterministicFillModel()
    fills, queues = model.apply_trade(
        trade, [dict(row) for row in store.open_orders(book.market_id)]
    )
    assert [fill.quantity_micros for fill in fills] == [10_000_000, 5_000_000]
    original = store._apply_fill_locked
    calls = 0

    def crash_on_second(fill):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("mid-plan crash")
        return original(fill)

    store._apply_fill_locked = crash_on_second
    with pytest.raises(RuntimeError, match="mid-plan"):
        store.apply_trade_plan(
            source_event_id=trade.event_id,
            queue_changes=queues,
            fills=fills,
            at=trade.observed_at,
        )
    assert store.connection.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 0
    assert store.trade_application(trade.event_id) is None
    assert [row["remaining_micros"] for row in store.open_orders()] == [10_000_000] * 2
    store._apply_fill_locked = original
    assert store.apply_trade_plan(
        source_event_id=trade.event_id,
        queue_changes=queues,
        fills=fills,
        at=trade.observed_at,
    )
    assert store.positions()[book.market_id] == 15_000_000
    assert not store.apply_trade_plan(
        source_event_id=trade.event_id,
        queue_changes=queues,
        fills=fills,
        at=trade.observed_at,
    )
    store.connection.execute(
        "UPDATE fills SET application_sequence=99 WHERE application_sequence=2"
    )
    with pytest.raises(ShadowIntegrityError, match="application sequence|digest"):
        store.reconcile()
    store.close()


def test_existing_position_without_mark_fails_closed() -> None:
    order = ShadowOrder(
        "1", "d", "new", ShadowSide.BUY, ShadowOrderType.LIMIT, 1, 500_000_000, False, NOW
    )
    result = check_order(
        order,
        positions={"existing": 10},
        reservations={},
        reserved_exposure={},
        marks={"new": 500_000_000},
        limits=ShadowRiskLimits(1000, 1000, 2),
    )
    assert result.reason == "missing_mark:existing"


def test_decision_payload_tamper_fails_authoritative_reconciliation(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path)
    engine.process(book)
    decision = store.connection.execute("SELECT decision_id FROM decisions").fetchone()[0]
    store.connection.execute(
        "UPDATE decisions SET payload_json=? WHERE decision_id=?",
        ('{"forecast_probability":0.99}', decision),
    )
    with pytest.raises(ShadowIntegrityError, match="decision payload digest"):
        store.reconcile()
    store.close()


@pytest.mark.parametrize(
    "extra",
    [
        "live: true\n",
        "execution: {}\n",
        "venue_adapter: unsafe\n",
        "network: {}\n",
        "unknown: 1\n",
        "strategy:\n  min_edge: 0.1\n  unexpected: true\n",
    ],
)
def test_shadow_config_is_strict_allowlist(tmp_path: Path, extra: str) -> None:
    path = tmp_path / "shadow.yaml"
    path.write_text(
        "schema_version: autopredict.shadow.config.v1\nmode: shadow\n"
        "state_path: x\ncapture_manifest: y\n" + extra,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown shadow config"):
        load_shadow_config(path)


def test_first_feed_sequence_requires_one_or_explicit_fault(tmp_path: Path) -> None:
    store = _leased_store(tmp_path, "sequence")
    with pytest.raises(ShadowIntegrityError, match="initial feed sequence"):
        store.record_feed_event(
            event_id="late",
            capture_sequence=2,
            event_type="BookObservation",
            observed_at=NOW,
            payload={"market_id": "m"},
        )
    assert store.record_feed_event(
        event_id="initial-gap",
        capture_sequence=2,
        event_type="FeedFault",
        observed_at=NOW,
        payload={"reason": "gap"},
    )
    store.close()


def test_risk_rejection_is_terminal_across_replay(tmp_path: Path) -> None:
    book, store, engine = _engine(tmp_path)
    engine.config = replace(
        engine.config,
        risk_limits=replace(engine.config.risk_limits, max_position_micros=1),
    )
    engine.process(book)
    assert store.connection.execute("SELECT COUNT(*) FROM rejections").fetchone()[0] == 1
    engine.config = replace(
        engine.config,
        risk_limits=replace(engine.config.risk_limits, max_position_micros=100_000_000),
    )
    engine.process(book)
    assert store.connection.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 0
    store.close()


def test_fill_source_type_market_and_time_are_enforced(tmp_path: Path) -> None:
    store = _leased_store(tmp_path, "causality")
    store.record_feed_event(
        event_id="marker",
        capture_sequence=1,
        event_type="FeedMarker",
        observed_at=NOW,
        payload={"market_id": "other"},
    )
    store.record_decision(decision_id="d", decision_key="k", status="approved", payload={}, at=NOW)
    store.submit_order(
        ShadowOrder("o", "d", "m", ShadowSide.BUY, ShadowOrderType.MARKET, 1, None, False, NOW)
    )
    with pytest.raises(ShadowIntegrityError, match="invalid type"):
        store.apply_fill(ShadowFill("f", "o", "m", ShadowSide.BUY, 1, 500_000_000, "marker", NOW))
    store.close()

    for name, payload, observed_at, message in (
        ("wrong-market", {"market_id": "other"}, NOW, "source market"),
        ("future-source", {"market_id": "m"}, NOW + timedelta(seconds=1), "source event"),
    ):
        candidate = _leased_store(tmp_path, name)
        candidate.record_feed_event(
            event_id="book",
            capture_sequence=1,
            event_type="BookObservation",
            observed_at=observed_at,
            payload=payload,
        )
        candidate.record_decision(
            decision_id="d", decision_key="k", status="approved", payload={}, at=NOW
        )
        candidate.submit_order(
            ShadowOrder("o", "d", "m", ShadowSide.BUY, ShadowOrderType.MARKET, 1, None, False, NOW)
        )
        with pytest.raises(ShadowIntegrityError, match=message):
            candidate.apply_fill(
                ShadowFill(
                    "f",
                    "o",
                    "m",
                    ShadowSide.BUY,
                    1,
                    500_000_000,
                    "book:depth:0",
                    NOW,
                )
            )
        candidate.close()


def test_restart_episodes_are_explicit(tmp_path: Path) -> None:
    store = ShadowStateStore.open(tmp_path / "episodes.db")
    for _ in range(2):
        store.start_run(
            run_id="same",
            at=NOW,
            config_sha256="a" * 64,
            provider_sha256="b" * 64,
        )
        store.end_run("same", NOW)
    episodes = list(
        store.connection.execute(
            "SELECT episode_number,status FROM run_episodes ORDER BY episode_number"
        )
    )
    assert [tuple(row) for row in episodes] == [(1, "completed"), (2, "completed")]
    store.close()


def test_shadow_feed_import_is_network_lean() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import autopredict.live.shadow.feed; "
            "print('autopredict.recording.recorder' in sys.modules); "
            "print('requests' in sys.modules)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.splitlines() == ["False", "False"]
