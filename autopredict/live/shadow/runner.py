"""Construction and operator helpers for capture-backed shadow runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from autopredict.config.shadow import ShadowConfig
from autopredict.forecasting import MarketBaselineProvider, RecalibrationProvider

from .clock import ReplayClock
from .contracts import stable_id
from .engine import ShadowEdgeStrategy, ShadowEngine
from .feed import CaptureReplayFeed
from .store import ShadowStateStore


def run_shadow(config: ShadowConfig) -> dict[str, Any]:
    feed = CaptureReplayFeed(config.capture_manifest)
    events = list(feed.events())
    if not events:
        raise ValueError("capture contains no shadow feed events")
    clock = ReplayClock(events[0].observed_at)
    provider = (
        MarketBaselineProvider()
        if config.provider == "market-baseline"
        else RecalibrationProvider()
    )
    strategy = ShadowEdgeStrategy(
        min_edge=config.min_edge,
        quantity=config.order_quantity_micros / 1_000_000,
    )
    store = ShadowStateStore.open(config.state_path)
    run_id = stable_id(
        "shadow-run",
        {
            "config_sha256": config.sha256,
            "capture_id": feed.manifest.capture_id,
        },
    )
    store.start_run(
        run_id=run_id,
        at=clock.now(),
        config_sha256=config.sha256,
        provider_sha256=provider.provenance.config_sha256,
    )
    try:
        engine = ShadowEngine(
            config=config,
            store=store,
            clock=clock,
            provider=provider,
            strategy=strategy,
        )
        engine.reconcile_startup()
        processed = engine.run(events)
    except BaseException:
        _finish_failed(store, run_id, clock.now())
        store.close()
        raise
    else:
        try:
            store.end_run(run_id, clock.now())
            return {"processed_events": processed, **store.status()}
        finally:
            store.close()


def cancel_shadow_state(state_path: str, reason: str) -> int:
    store = ShadowStateStore.open(state_path)
    now = datetime.now(timezone.utc)
    run_id = stable_id("shadow-admin", {"action": "cancel-all", "at": now.isoformat()})
    store.start_run(run_id=run_id, at=now, config_sha256="0" * 64, provider_sha256="0" * 64)
    try:
        count = store.cancel_all(at=now, reason=reason)
        store.latch_breaker(reason="manual", detail=reason, at=now)
        store.end_run(run_id, now)
        return count
    except BaseException:
        _finish_failed(store, run_id, now)
        raise
    finally:
        store.close()


def reset_shadow_state(state_path: str, reason: str, freshness_seconds: int) -> None:
    store = ShadowStateStore.open(state_path)
    now = datetime.now(timezone.utc)
    run_id = stable_id("shadow-admin", {"action": "reset", "at": now.isoformat()})
    store.start_run(run_id=run_id, at=now, config_sha256="0" * 64, provider_sha256="0" * 64)
    try:
        store.reset_breaker(at=now, freshness_seconds=freshness_seconds, reason=reason)
        store.end_run(run_id, now)
    except BaseException:
        _finish_failed(store, run_id, now)
        raise
    finally:
        store.close()


def inspect_shadow_state(state_path: str) -> dict[str, Any]:
    store = ShadowStateStore.open(state_path)
    now = datetime.now(timezone.utc)
    run_id = stable_id("shadow-admin", {"action": "status", "at": now.isoformat()})
    store.start_run(
        run_id=run_id,
        at=now,
        config_sha256="0" * 64,
        provider_sha256="0" * 64,
    )
    try:
        store.reconcile()
        store.end_run(run_id, now)
        return store.status()
    except BaseException:
        _finish_failed(store, run_id, now)
        raise
    finally:
        store.close()


def _finish_failed(store: ShadowStateStore, run_id: str, at: datetime) -> None:
    """Best-effort cleanup that never masks the active exception."""

    try:
        store.end_run(run_id, at, status="failed")
    except Exception:
        try:
            store.release_lease(run_id)
        except Exception:
            pass
