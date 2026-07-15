"""Read-only recorder and deterministic replay tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import requests

from autopredict.evaluation import load_dataset_v1
from autopredict.evaluation.reporting import evaluate_market_baseline
from autopredict.recording import (
    CaptureBundle,
    CaptureRecord,
    CaptureValidationError,
    PolymarketRecorder,
    PublicResponse,
    ReadOnlyPolymarketSource,
    RequestsPublicJSONTransport,
    load_capture,
    replay_capture,
    write_capture,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures/recording/polymarket-v1/manifest.json"
OFFICIAL_SCHEMA_FIXTURE = (
    Path(__file__).parent / "fixtures/recording/polymarket-official-schema.json"
)


class FakeSource:
    def __init__(
        self,
        *,
        sequence_step: int = 1,
        reconnect_market_ids: frozenset[str] = frozenset(),
        include_resolution: bool = True,
    ) -> None:
        self.sequence_step = sequence_step
        self.reconnect_market_ids = reconnect_market_ids
        self.include_resolution = include_resolution
        self.calls: list[tuple[str, str]] = []
        self.dangerous_calls: list[str] = []
        self._market_number: dict[str, int] = {}

    def _number(self, market_id: str) -> int:
        if market_id not in self._market_number:
            self._market_number[market_id] = len(self._market_number) + 1
        return self._market_number[market_id]

    def _response(
        self,
        *,
        stream: str,
        market_id: str,
        payload: Any,
        suffix: str,
        reconnected: bool = False,
    ) -> PublicResponse:
        number = self._number(market_id)
        requested_at = START + timedelta(minutes=number, seconds=len(self.calls) * 2)
        received_at = requested_at + timedelta(seconds=1)
        sequence = 1 + (number - 1) * self.sequence_step
        self.calls.append((stream, market_id))
        return PublicResponse.create(
            stream=stream,
            endpoint=f"https://public.example/{stream}",
            requested_at=requested_at,
            received_at=received_at,
            source_record_id=f"{suffix}-{market_id}-{number}",
            payload=payload,
            source_sequence=sequence,
            reconnected=reconnected,
        )

    def fetch_gamma_market(self, market_id: str) -> PublicResponse:
        number = self._number(market_id)
        return self._response(
            stream="gamma",
            market_id=market_id,
            suffix="market",
            payload={
                "event": {
                    "category": "politics",
                    "event_id": f"event-{number}",
                    "title": f"Event {number}",
                },
                "market": {
                    "category": "politics",
                    "event_id": f"event-{number}",
                    "expiry": "2026-02-01T00:00:00Z",
                    "gamma_market_id": int(market_id),
                    "market_id": f"condition-{market_id}",
                    "market_probability": 0.4 + number / 10,
                    "question": f"Will event {number} happen?",
                    "yes_token_id": f"yes-condition-{market_id}",
                },
            },
        )

    def fetch_clob_book(self, condition_id: str, token_id: str) -> PublicResponse:
        market_id = condition_id.removeprefix("condition-")
        return self._response(
            stream="clob-book",
            market_id=market_id,
            suffix="book",
            payload={
                "asks": [[0.51, 80.0], [0.52, 20.0]],
                "bids": [[0.49, 90.0], [0.48, 30.0]],
                "market_id": condition_id,
                "token_id": token_id,
            },
        )

    def fetch_public_trades(self, condition_id: str) -> tuple[PublicResponse, ...]:
        market_id = condition_id.removeprefix("condition-")
        return (
            self._response(
                stream="clob-trades",
                market_id=market_id,
                suffix="trades",
                payload={
                    "trades": [
                        {
                            "executed_at": "2026-01-01T00:00:30Z",
                            "conditionId": condition_id,
                            "market_id": condition_id,
                            "price": 0.5,
                            "side": "buy",
                            "size": 2.0,
                            "trade_id": f"trade-{market_id}",
                        }
                    ]
                },
            ),
        )

    def fetch_gamma_resolution(self, market_id: str) -> PublicResponse | None:
        if not self.include_resolution:
            return None
        number = self._number(market_id)
        response = self._response(
            stream="gamma-resolution",
            market_id=market_id,
            suffix="resolution",
            payload={
                "resolution": {
                    "event_id": f"event-{number}",
                    "gamma_market_id": int(market_id),
                    "market_id": f"condition-{market_id}",
                    "outcome": number % 2,
                    "resolved_at": "2026-02-02T00:00:00Z",
                }
            },
            reconnected=market_id in self.reconnect_market_ids,
        )
        return PublicResponse.create(
            stream=response.stream,
            endpoint=response.endpoint,
            requested_at=datetime(2026, 2, 2, 0, 0, 1, tzinfo=timezone.utc),
            received_at=datetime(2026, 2, 2, 0, 0, 2, tzinfo=timezone.utc),
            source_record_id=response.source_record_id,
            payload=response.payload(),
            request_params=response.request_params(),
            source_sequence=response.source_sequence,
            reconnected=response.reconnected,
        )

    # These methods make accidental expansion of the recorder surface observable.
    def place_order(self, *_args, **_kwargs):
        self.dangerous_calls.append("place_order")
        raise AssertionError("recorder attempted an authenticated method")

    def cancel_order(self, *_args, **_kwargs):
        self.dangerous_calls.append("cancel_order")
        raise AssertionError("recorder attempted an authenticated method")

    def get_balance(self, *_args, **_kwargs):
        self.dangerous_calls.append("get_balance")
        raise AssertionError("recorder attempted an authenticated method")


def test_capture_replay_is_byte_deterministic_and_evaluation_ready(tmp_path: Path) -> None:
    source = FakeSource()
    recorder = PolymarketRecorder(source)
    recorder.capture_snapshot("1")
    assert recorder.capture_resolution("1") is True

    first_capture = write_capture(recorder.bundle(), tmp_path / "capture-a")
    second_capture = write_capture(recorder.bundle(), tmp_path / "capture-b")
    assert first_capture.read_bytes() == second_capture.read_bytes()
    assert (first_capture.parent / "capture.jsonl").read_bytes() == (
        second_capture.parent / "capture.jsonl"
    ).read_bytes()

    first_dataset = replay_capture(first_capture, tmp_path / "dataset-a")
    second_dataset = replay_capture(second_capture, tmp_path / "dataset-b")
    assert first_dataset.read_bytes() == second_dataset.read_bytes()
    assert (first_dataset.parent / "records.jsonl").read_bytes() == (
        second_dataset.parent / "records.jsonl"
    ).read_bytes()

    dataset = load_dataset_v1(first_dataset)
    report = evaluate_market_baseline(dataset)
    assert report["valid"] is True
    assert dataset.manifest.completeness == "complete"
    assert len(dataset.observations) == 1
    assert len(dataset.resolutions) == 1
    assert not hasattr(dataset.observations[0], "outcome")
    assert source.dangerous_calls == []
    assert {name for name, _market in source.calls} == {
        "gamma",
        "clob-book",
        "clob-trades",
        "gamma-resolution",
    }


def test_checked_in_capture_fixture_replays_through_canonical_loader(tmp_path: Path) -> None:
    manifest, records = load_capture(FIXTURE)
    dataset_path = replay_capture(FIXTURE, tmp_path / "dataset")
    dataset = load_dataset_v1(dataset_path)

    assert manifest.record_count == 6
    assert {record.record_type for record in records} == {
        "event",
        "market_metadata",
        "order_book",
        "trade",
        "trade_page",
        "resolution",
    }
    assert dataset.manifest.dataset_id == f"replay-{manifest.capture_id}"


def test_sequence_gaps_are_explicit_and_fail_closed_for_evaluation(tmp_path: Path) -> None:
    source = FakeSource(sequence_step=2)
    recorder = PolymarketRecorder(source)
    recorder.capture_snapshot("1")
    recorder.capture_resolution("1")
    recorder.capture_snapshot("2")
    recorder.capture_resolution("2")
    capture_path = write_capture(recorder.bundle(), tmp_path / "capture")

    capture_manifest, capture_records = load_capture(capture_path)
    assert capture_manifest.completeness == "partial"
    assert any(record.record_type == "gap" for record in capture_records)
    assert any("sequence_gap" in warning for warning in capture_manifest.warnings)

    dataset_path = replay_capture(capture_path, tmp_path / "dataset")
    dataset = load_dataset_v1(dataset_path)
    assert dataset.manifest.completeness == "partial"
    with pytest.raises(ValueError, match="complete dataset"):
        evaluate_market_baseline(dataset)
    assert source.dangerous_calls == []


def test_reconnect_is_explicit_and_reduces_completeness(tmp_path: Path) -> None:
    source = FakeSource(reconnect_market_ids=frozenset({"1"}))
    recorder = PolymarketRecorder(source)
    recorder.capture_snapshot("1")
    recorder.capture_resolution("1")
    manifest_path = write_capture(recorder.bundle(), tmp_path / "capture")

    manifest, records = load_capture(manifest_path)
    assert manifest.completeness == "partial"
    reconnects = [
        record
        for record in records
        if record.record_type == "gap" and record.payload()["kind"] == "reconnect"
    ]
    assert len(reconnects) == 1


def test_replay_requires_separate_resolution(tmp_path: Path) -> None:
    recorder = PolymarketRecorder(FakeSource(include_resolution=False))
    recorder.capture_snapshot("1")
    manifest_path = write_capture(recorder.bundle(), tmp_path / "capture")

    with pytest.raises(CaptureValidationError, match="separate captured resolution"):
        replay_capture(manifest_path, tmp_path / "dataset")
    assert not (tmp_path / "dataset").exists()


def test_capture_payloads_are_deeply_immutable() -> None:
    payload = {"nested": {"value": 1}}
    response = PublicResponse.create(
        stream="gamma",
        endpoint="https://public.example/gamma",
        requested_at=START,
        received_at=START + timedelta(seconds=1),
        source_record_id="immutable-1",
        payload=payload,
    )
    payload["nested"]["value"] = 999

    assert response.payload() == {"nested": {"value": 1}}


def test_polling_capture_does_not_claim_sequence_completeness(tmp_path: Path) -> None:
    response = PublicResponse.create(
        stream="rest-poll",
        endpoint="https://public.example/poll",
        requested_at=START,
        received_at=START + timedelta(seconds=1),
        source_record_id="poll-1",
        payload={"value": 1},
        request_params={"limit": "100", "offset": "0"},
        source_at=START,
    )
    record = CaptureRecord.create(
        record_type="event",
        capture_sequence=1,
        snapshot_id="snapshot-1",
        response=response,
        payload={"value": 1},
    )
    path = write_capture(
        CaptureBundle(
            venue="test",
            records=(record,),
            completeness="complete",
            warnings=(),
        ),
        tmp_path / "polling",
    )
    manifest, loaded = load_capture(path)
    assert manifest.sequence_completeness == "not_available_polling"
    assert manifest.source_started_at == START
    assert loaded[0].request_params_json == '{"limit":"100","offset":"0"}'


def test_recorder_rejects_future_resolution_leakage() -> None:
    class FutureResolutionSource(FakeSource):
        def fetch_gamma_resolution(self, market_id: str) -> PublicResponse:
            response = super().fetch_gamma_resolution(market_id)
            assert response is not None
            return PublicResponse.create(
                stream=response.stream,
                endpoint=response.endpoint,
                requested_at=START + timedelta(minutes=10),
                received_at=START + timedelta(minutes=10, seconds=1),
                source_record_id=response.source_record_id,
                payload=response.payload(),
                request_params=response.request_params(),
                source_sequence=response.source_sequence,
            )

    recorder = PolymarketRecorder(FutureResolutionSource())
    recorder.capture_snapshot("1")
    with pytest.raises(CaptureValidationError, match="before its resolved_at"):
        recorder.capture_resolution("1")
    assert all(record.record_type != "resolution" for record in recorder.bundle().records)


def test_capture_loader_rejects_tampering(tmp_path: Path) -> None:
    recorder = PolymarketRecorder(FakeSource())
    recorder.capture_snapshot("1")
    recorder.capture_resolution("1")
    manifest_path = write_capture(recorder.bundle(), tmp_path / "capture")
    records_path = manifest_path.parent / "capture.jsonl"
    records_path.write_bytes(records_path.read_bytes().replace(b'"price":0.5', b'"price":0.6'))

    with pytest.raises(CaptureValidationError, match="sha256 mismatch"):
        load_capture(manifest_path)


def test_capture_writer_prevalidates_forged_record_id_before_publish(tmp_path: Path) -> None:
    recorder = PolymarketRecorder(FakeSource())
    recorder.capture_snapshot("1")
    valid = recorder.bundle()
    forged = replace(valid.records[0], capture_id="capture-record-forged")
    destination = tmp_path / "forged"

    with pytest.raises(CaptureValidationError, match="record id mismatch"):
        write_capture(
            CaptureBundle(
                venue=valid.venue,
                records=(forged, *valid.records[1:]),
                completeness=valid.completeness,
                warnings=valid.warnings,
            ),
            destination,
        )
    assert not destination.exists()


def test_read_only_source_exposes_only_get_transport_and_separate_times() -> None:
    official = json.loads(OFFICIAL_SCHEMA_FIXTURE.read_text())

    class Transport:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str] | None]] = []

        def get_json(self, endpoint: str, *, params=None):
            self.calls.append((endpoint, params))
            if "gamma-api" in endpoint:
                return official["gamma_market"]
            if "data-api" in endpoint:
                return official["trades"]
            return official["book"]

    times = iter(
        (
            START,
            START + timedelta(milliseconds=10),
            START + timedelta(milliseconds=20),
            START + timedelta(milliseconds=30),
            START + timedelta(milliseconds=40),
            START + timedelta(milliseconds=50),
        )
    )
    transport = Transport()
    source = ReadOnlyPolymarketSource(transport=transport, clock=lambda: next(times))
    gamma_response = source.fetch_gamma_market("1")
    book_response = source.fetch_clob_book("condition-1", "yes-market-1")
    trades_response = source.fetch_public_trades("condition-1")[0]

    assert gamma_response.requested_at < gamma_response.received_at
    assert book_response.requested_at < book_response.received_at
    assert gamma_response.received_at < book_response.requested_at
    assert book_response.payload()["asks"] == [[0.51, 2.0], [0.52, 1.0]]
    assert book_response.payload()["bids"] == [[0.49, 4.0], [0.48, 3.0]]
    assert trades_response.payload()["trades"][0]["market_id"] == "condition-1"
    assert transport.calls == [
        ("https://gamma-api.polymarket.com/markets/1", None),
        ("https://clob.polymarket.com/book", {"token_id": "yes-market-1"}),
        (
            "https://data-api.polymarket.com/trades",
            {"limit": "100", "market": "condition-1", "offset": "0"},
        ),
    ]
    assert not hasattr(source, "place_order")
    assert not hasattr(source, "cancel_order")


def test_requests_transport_uses_only_public_get() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, bool]:
            return {"ok": True}

    class Session(requests.Session):
        def __init__(self) -> None:
            super().__init__()
            self.trust_env = False
            self.send_calls: list[tuple[str, float, bool]] = []
            self.dangerous_calls: list[str] = []

        def send(self, request, *, timeout: float, allow_redirects: bool, **_kwargs):
            self.send_calls.append((request.url, timeout, allow_redirects))
            return Response()

        def post(self, *_args, **_kwargs):
            self.dangerous_calls.append("post")
            raise AssertionError("read-only transport attempted POST")

    session = Session()
    transport = RequestsPublicJSONTransport(session=session, timeout_seconds=2.0)

    assert transport.get_json(
        "https://clob.polymarket.com/ok", params={"token_id": "public-token-id"}
    ) == {"ok": True}
    assert session.send_calls == [
        ("https://clob.polymarket.com/ok?token_id=public-token-id", 2.0, False)
    ]
    assert session.dangerous_calls == []


def test_real_clock_lifecycle_preserves_identity_and_never_fetches_label_early() -> None:
    source = FakeSource()
    recorder = PolymarketRecorder(source)

    recorder.capture_snapshot("1")
    assert "gamma-resolution" not in {name for name, _ in source.calls}
    metadata = next(
        record.payload()
        for record in recorder.bundle().records
        if record.record_type == "market_metadata"
    )
    assert metadata["gamma_market_id"] == 1
    assert metadata["event_id"] == "event-1"
    assert metadata["market_id"] == "condition-1"
    assert metadata["yes_token_id"] == "yes-condition-1"

    assert recorder.capture_resolution("1") is True
    resolution = next(
        record.payload()
        for record in recorder.bundle().records
        if record.record_type == "resolution"
    )
    assert (resolution["event_id"], resolution["market_id"]) == (
        "event-1",
        "condition-1",
    )


def test_lifecycle_identity_restores_from_persisted_bundle(tmp_path: Path) -> None:
    source = FakeSource()
    initial = PolymarketRecorder(source)
    initial.capture_snapshot("1")
    path = write_capture(initial.bundle(), tmp_path / "snapshot")
    manifest, records = load_capture(path)

    restored = PolymarketRecorder.from_bundle(
        source,
        CaptureBundle(
            venue=manifest.venue,
            records=records,
            completeness=manifest.completeness,
            warnings=manifest.warnings,
        ),
    )
    assert restored.capture_resolution("1") is True
    assert any(record.record_type == "resolution" for record in restored.bundle().records)


def test_restored_partial_capture_never_upgrades_to_complete(tmp_path: Path) -> None:
    source = FakeSource()
    initial = PolymarketRecorder(source)
    initial.capture_snapshot("1")
    prior = CaptureBundle(
        venue="polymarket-archive",
        records=initial.bundle().records,
        completeness="partial",
        warnings=("prior polling interval is incomplete",),
    )
    snapshot_path = write_capture(prior, tmp_path / "snapshot")
    manifest, records = load_capture(snapshot_path)

    restored = PolymarketRecorder.from_bundle(
        source,
        CaptureBundle(
            venue=manifest.venue,
            records=records,
            completeness=manifest.completeness,
            warnings=manifest.warnings,
        ),
    )
    assert restored.capture_resolution("1") is True
    final_bundle = restored.bundle()
    assert final_bundle.venue == "polymarket-archive"
    assert final_bundle.completeness == "partial"
    assert final_bundle.warnings == ("prior polling interval is incomplete",)

    final_capture = write_capture(final_bundle, tmp_path / "final-capture")
    final_manifest, _ = load_capture(final_capture)
    assert final_manifest.completeness == "partial"
    assert final_manifest.warnings == ("prior polling interval is incomplete",)
    dataset_path = replay_capture(final_capture, tmp_path / "dataset")
    dataset = load_dataset_v1(dataset_path)
    assert dataset.manifest.completeness == "partial"
    with pytest.raises(ValueError, match="complete dataset"):
        evaluate_market_baseline(dataset)


@pytest.mark.parametrize("completeness", ["", "PARTIAL", "unknown"])
def test_restore_rejects_unknown_completeness(completeness: str) -> None:
    source = FakeSource()
    recorder = PolymarketRecorder(source)
    recorder.capture_snapshot("1")
    invalid = replace(recorder.bundle(), completeness=completeness)

    with pytest.raises(CaptureValidationError, match="must be complete or partial"):
        PolymarketRecorder.from_bundle(source, invalid)


def test_resolution_identity_mismatch_rolls_back_label() -> None:
    class WrongResolutionSource(FakeSource):
        def fetch_gamma_resolution(self, market_id: str) -> PublicResponse:
            response = super().fetch_gamma_resolution(market_id)
            assert response is not None
            payload = response.payload()
            payload["resolution"]["market_id"] = "wrong-condition"
            return PublicResponse.create(
                stream=response.stream,
                endpoint=response.endpoint,
                requested_at=response.requested_at,
                received_at=response.received_at,
                source_record_id=response.source_record_id,
                payload=payload,
                request_params=response.request_params(),
                source_sequence=response.source_sequence,
            )

    recorder = PolymarketRecorder(WrongResolutionSource())
    recorder.capture_snapshot("1")
    with pytest.raises(CaptureValidationError, match="identity does not match"):
        recorder.capture_resolution("1")
    assert all(record.record_type != "resolution" for record in recorder.bundle().records)


def test_public_source_paginates_and_records_params_and_source_times() -> None:
    class Transport:
        def __init__(self) -> None:
            self.offsets: list[str] = []

        def get_json(self, endpoint: str, *, params=None):
            assert "data-api.polymarket.com/trades" in endpoint
            self.offsets.append(params["offset"])
            if params["offset"] == "0":
                return [
                    {
                        "conditionId": "condition-1",
                        "id": "trade-1",
                        "timestamp": 1767225600,
                    },
                    {
                        "conditionId": "condition-1",
                        "id": "trade-2",
                        "timestamp": 1767225601,
                    },
                ]
            return []

    times = iter(START + timedelta(seconds=value) for value in range(4))
    transport = Transport()
    source = ReadOnlyPolymarketSource(
        transport=transport,
        clock=lambda: next(times),
        trade_page_size=2,
    )
    pages = source.fetch_public_trades("condition-1")

    assert transport.offsets == ["0", "2"]
    assert pages[0].request_params() == {
        "limit": "2",
        "market": "condition-1",
        "offset": "0",
    }
    assert pages[0].source_at == datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert pages[1].payload() == {"trades": []}


def test_trade_pagination_bound_is_an_explicit_partial_gap() -> None:
    class Transport:
        def get_json(self, endpoint: str, *, params=None):
            return [{"conditionId": "condition-1", "id": "trade-1"}]

    times = iter((START, START + timedelta(seconds=1)))
    source = ReadOnlyPolymarketSource(
        transport=Transport(),
        clock=lambda: next(times),
        trade_page_size=1,
        max_trade_pages=1,
    )
    page = source.fetch_public_trades("condition-1")[0]
    assert page.partial_reason == "trade_pagination_limit"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "asks": [{"price": "0.6", "size": "1"}],
                "asset_id": "wrong-token",
                "bids": [{"price": "0.4", "size": "1"}],
                "market": "condition-1",
            },
            "asset_id",
        ),
        (
            {
                "asks": [{"price": "0.6", "size": "1"}],
                "asset_id": "yes-token",
                "bids": [{"price": "0.4", "size": "1"}],
                "market": "wrong-condition",
            },
            "condition",
        ),
    ],
)
def test_public_source_rejects_wrong_clob_identity(payload: dict[str, Any], message: str) -> None:
    class Transport:
        def get_json(self, endpoint: str, *, params=None):
            return payload

    times = iter((START, START + timedelta(seconds=1)))
    source = ReadOnlyPolymarketSource(transport=Transport(), clock=lambda: next(times))
    with pytest.raises(CaptureValidationError, match=message):
        source.fetch_clob_book("condition-1", "yes-token")


def test_public_source_rejects_wrong_trade_condition() -> None:
    class Transport:
        def get_json(self, endpoint: str, *, params=None):
            return [{"conditionId": "wrong-condition", "id": "trade-1"}]

    times = iter((START, START + timedelta(seconds=1)))
    source = ReadOnlyPolymarketSource(transport=Transport(), clock=lambda: next(times))
    with pytest.raises(CaptureValidationError, match="conditionId"):
        source.fetch_public_trades("condition-1")


def test_writer_rejects_undeclared_source_sequence_gap(tmp_path: Path) -> None:
    first = PublicResponse.create(
        stream="sequenced",
        endpoint="https://public.example/sequence",
        requested_at=START,
        received_at=START + timedelta(seconds=1),
        source_record_id="one",
        payload={"value": 1},
        source_sequence=1,
    )
    second = PublicResponse.create(
        stream="sequenced",
        endpoint="https://public.example/sequence",
        requested_at=START + timedelta(seconds=2),
        received_at=START + timedelta(seconds=3),
        source_record_id="three",
        payload={"value": 3},
        source_sequence=3,
    )
    bundle = CaptureBundle(
        venue="test",
        records=(
            CaptureRecord.create(
                record_type="event",
                capture_sequence=1,
                snapshot_id="snapshot-1",
                response=first,
                payload={"value": 1},
            ),
            CaptureRecord.create(
                record_type="event",
                capture_sequence=2,
                snapshot_id="snapshot-2",
                response=second,
                payload={"value": 3},
            ),
        ),
        completeness="complete",
        warnings=(),
    )
    with pytest.raises(CaptureValidationError, match="undeclared source sequence gap"):
        write_capture(bundle, tmp_path / "capture")
    assert not (tmp_path / "capture").exists()


def test_two_file_publication_is_atomic_in_both_conflict_directions(tmp_path: Path) -> None:
    recorder = PolymarketRecorder(FakeSource())
    recorder.capture_snapshot("1")
    recorder.capture_resolution("1")
    bundle = recorder.bundle()

    capture_records_conflict = tmp_path / "capture-records-conflict"
    capture_records_conflict.mkdir()
    (capture_records_conflict / "capture.jsonl").write_text("conflict\n")
    with pytest.raises(CaptureValidationError, match="refusing to overwrite"):
        write_capture(bundle, capture_records_conflict)
    assert not (capture_records_conflict / "manifest.json").exists()

    capture_manifest_conflict = tmp_path / "capture-manifest-conflict"
    capture_manifest_conflict.mkdir()
    (capture_manifest_conflict / "manifest.json").write_text("conflict\n")
    with pytest.raises(CaptureValidationError, match="refusing to overwrite"):
        write_capture(bundle, capture_manifest_conflict)
    assert not (capture_manifest_conflict / "capture.jsonl").exists()

    good_capture = write_capture(bundle, tmp_path / "good-capture")
    replay_manifest_conflict = tmp_path / "replay-manifest-conflict"
    replay_manifest_conflict.mkdir()
    (replay_manifest_conflict / "manifest.json").write_text("conflict\n")
    with pytest.raises(CaptureValidationError, match="refusing to overwrite"):
        replay_capture(good_capture, replay_manifest_conflict)
    assert not (replay_manifest_conflict / "records.jsonl").exists()

    replay_records_conflict = tmp_path / "replay-records-conflict"
    replay_records_conflict.mkdir()
    (replay_records_conflict / "records.jsonl").write_text("conflict\n")
    with pytest.raises(CaptureValidationError, match="refusing to overwrite"):
        replay_capture(good_capture, replay_records_conflict)
    assert not (replay_records_conflict / "manifest.json").exists()


def test_idempotent_existing_capture_is_validated_before_return(tmp_path: Path) -> None:
    recorder = PolymarketRecorder(FakeSource())
    recorder.capture_snapshot("1")
    valid = recorder.bundle()
    target = tmp_path / "existing-forged"
    manifest_path = write_capture(valid, target)

    lines = (target / "capture.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    first["capture_id"] = "capture-record-forged"
    lines[0] = json.dumps(
        first,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    forged_records = ("\n".join(lines) + "\n").encode()
    digest = hashlib.sha256(forged_records).hexdigest()
    manifest = json.loads(manifest_path.read_text())
    manifest["capture_id"] = f"capture-{digest}"
    manifest["records_sha256"] = digest
    (target / "capture.jsonl").write_bytes(forged_records)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    forged_bundle = replace(
        valid,
        records=(replace(valid.records[0], capture_id="capture-record-forged"), *valid.records[1:]),
    )
    with pytest.raises(CaptureValidationError, match="record id mismatch"):
        write_capture(forged_bundle, target)


def test_default_transport_rejects_credentials_and_non_allowlisted_hosts() -> None:
    class Session:
        headers = {"Authorization": "secret"}

        def get(self, *_args, **_kwargs):
            raise AssertionError("request must fail before network")

    transport = RequestsPublicJSONTransport(session=Session())
    with pytest.raises(CaptureValidationError, match="allowlisted HTTPS"):
        transport.get_json("http://clob.polymarket.com/book")
    with pytest.raises(CaptureValidationError, match="credential-bearing headers"):
        transport.get_json("https://clob.polymarket.com/book")


@pytest.mark.parametrize(
    ("unsafe", "message"),
    [
        ({"auth": ("user", "password")}, "session authentication"),
        ({"cookies": ["session-cookie"]}, "cookies"),
        ({"headers": {"Cookie": "session=secret"}}, "credential-bearing headers"),
        ({"headers": {"X-Access-Token": "secret"}}, "credential-bearing headers"),
        ({"headers": {"X-Auth-Token": "secret"}}, "credential-bearing headers"),
        ({"trust_env": True}, "ambient environment credentials"),
        ({"proxies": {"https": "http://user:pass@proxy.invalid"}}, "configured proxies"),
        ({"cert": ("client.pem", "key.pem")}, "client certificates"),
    ],
)
def test_transport_rejects_ambient_credentials_before_get(
    unsafe: dict[str, Any], message: str
) -> None:
    class Session:
        auth = None
        cert = None
        cookies: Any = []
        headers: dict[str, str] = {}
        proxies: dict[str, str] = {}
        trust_env = False

        def __init__(self) -> None:
            self.called = False
            for name, value in unsafe.items():
                setattr(self, name, value)

        def get(self, *_args, **_kwargs):
            self.called = True
            raise AssertionError("unsafe session must fail before GET")

    session = Session()
    transport = RequestsPublicJSONTransport(session=session)
    with pytest.raises(CaptureValidationError, match=message):
        transport.get_json("https://clob.polymarket.com/book")
    assert session.called is False


@pytest.mark.parametrize(
    ("endpoint", "params"),
    [
        ("https://clob.polymarket.com/book?api_key=secret", None),
        ("https://clob.polymarket.com/book?token=secret", None),
        ("https://clob.polymarket.com/book", {"access_token": "secret"}),
        ("https://clob.polymarket.com/book", {"auth_token": "secret"}),
        ("https://clob.polymarket.com/book", {"accessToken": "secret"}),
    ],
)
def test_transport_rejects_credential_query_keys_before_send(
    endpoint: str, params: dict[str, str] | None
) -> None:
    class Session(requests.Session):
        def __init__(self) -> None:
            super().__init__()
            self.trust_env = False
            self.called = False

        def send(self, *_args, **_kwargs):
            self.called = True
            raise AssertionError("credential query must fail before send")

    session = Session()
    transport = RequestsPublicJSONTransport(session=session)
    with pytest.raises(CaptureValidationError, match="non-public query parameters"):
        transport.get_json(endpoint, params=params)
    assert session.called is False


def test_transport_rejects_real_session_default_params_before_send() -> None:
    class Session(requests.Session):
        def __init__(self) -> None:
            super().__init__()
            self.trust_env = False
            self.params = {"api_key": "secret"}
            self.called = False

        def send(self, *_args, **_kwargs):
            self.called = True
            raise AssertionError("session params must fail before send")

    session = Session()
    transport = RequestsPublicJSONTransport(session=session)
    with pytest.raises(CaptureValidationError, match="session query parameters"):
        transport.get_json(
            "https://clob.polymarket.com/book",
            params={"token_id": "public-token-id"},
        )
    assert session.called is False
