"""Credential-free shadow feeds, including deterministic Packet 5 capture replay."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterator, Protocol

from autopredict.recording.contracts import CaptureRecord, load_capture

from .contracts import (
    BookLevel,
    BookObservation,
    BreakerReason,
    FeedFault,
    FeedMarker,
    ShadowFeedEvent,
    ShadowSide,
    TradePrint,
    parse_utc,
    to_fixed,
    PRICE_SCALE,
    QUANTITY_SCALE,
)


class ShadowFeed(Protocol):
    def events(self) -> Iterator[ShadowFeedEvent]: ...


class CaptureReplayFeed:
    """Replay every capture sequence exactly once in canonical file order."""

    def __init__(self, manifest: str | Path) -> None:
        self.manifest, self.records = load_capture(manifest)

    def events(self) -> Iterator[ShadowFeedEvent]:
        snapshots: dict[str, dict[str, CaptureRecord]] = {}
        for record in self.records:
            if record.snapshot_id is not None:
                snapshots.setdefault(record.snapshot_id, {})[record.record_type] = record
            if record.record_type == "order_book":
                assert record.snapshot_id is not None
                yield _book_observation(record, snapshots[record.snapshot_id])
            elif record.record_type == "trade":
                yield _trade(record)
            elif record.record_type == "gap":
                payload = record.payload()
                detail = (
                    str(payload.get("kind", "capture gap"))
                    if isinstance(payload, dict)
                    else "capture gap"
                )
                reason = BreakerReason.RECONNECT if detail == "reconnect" else BreakerReason.GAP
                yield FeedFault(
                    event_id=record.capture_id,
                    capture_sequence=record.capture_sequence,
                    observed_at=record.received_at,
                    reason=reason,
                    detail=detail,
                )
            else:
                yield FeedMarker(
                    event_id=record.capture_id,
                    capture_sequence=record.capture_sequence,
                    observed_at=record.received_at,
                    kind=record.record_type,
                )


def _book_observation(record: CaptureRecord, group: dict[str, CaptureRecord]) -> BookObservation:
    missing = {"event", "market_metadata"} - set(group)
    if missing:
        raise ValueError(f"order book snapshot missing prior records: {sorted(missing)}")
    event = group["event"].payload()
    market = group["market_metadata"].payload()
    book = record.payload()
    if not all(isinstance(value, dict) for value in (event, market, book)):
        raise ValueError("capture snapshot payloads must be objects")
    market_id = str(market.get("market_id", ""))
    if book.get("market_id") != market_id or market.get("event_id") != event.get("event_id"):
        raise ValueError("capture snapshot identity mismatch")
    return BookObservation(
        event_id=record.capture_id,
        capture_sequence=record.capture_sequence,
        market_id=market_id,
        event_market_id=str(event["event_id"]),
        question=str(market["question"]),
        category=str(market.get("category", event.get("category", "other"))),
        observed_at=record.source_at or record.received_at,
        expiry=parse_utc(str(market["expiry"])),
        market_probability_nanos=to_fixed(
            market["market_probability"], PRICE_SCALE, field="market_probability"
        ),
        bids=_levels(book.get("bids"), reverse=True),
        asks=_levels(book.get("asks"), reverse=False),
        source="polymarket-capture-v1",
        source_record_id=record.capture_id,
    )


def _levels(value: object, *, reverse: bool) -> tuple[BookLevel, ...]:
    if not isinstance(value, list):
        raise ValueError("book levels must be arrays")
    levels: list[BookLevel] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("book level must be [price, size]")
        levels.append(
            BookLevel(
                to_fixed(item[0], PRICE_SCALE, field="book price"),
                to_fixed(item[1], QUANTITY_SCALE, field="book quantity"),
            )
        )
    return tuple(sorted(levels, key=lambda level: level.price_nanos, reverse=reverse))


def _trade(record: CaptureRecord) -> TradePrint:
    payload = record.payload()
    if not isinstance(payload, dict):
        raise ValueError("trade payload must be an object")
    side = ShadowSide(str(payload["side"]).lower())
    executed_at: datetime
    if record.source_at is not None:
        executed_at = record.source_at
    elif isinstance(payload.get("executed_at"), str):
        executed_at = parse_utc(payload["executed_at"])
    else:
        executed_at = record.received_at
    return TradePrint(
        event_id=record.capture_id,
        capture_sequence=record.capture_sequence,
        trade_id=str(payload["trade_id"]),
        market_id=str(payload["market_id"]),
        observed_at=record.received_at,
        executed_at=executed_at,
        side=side,
        price_nanos=to_fixed(payload["price"], PRICE_SCALE, field="trade price"),
        quantity_micros=to_fixed(payload["size"], QUANTITY_SCALE, field="trade size"),
    )
