"""Immutable, canonical contracts for read-only public-data capture."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Iterable, cast

CAPTURE_SCHEMA_VERSION = "autopredict.capture.v1"


class CaptureValidationError(ValueError):
    """Raised when a capture cannot be trusted or replayed."""


def canonical_json(value: Any) -> str:
    """Serialize one value to deterministic, finite JSON."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise CaptureValidationError("capture timestamps must be timezone-aware UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CaptureValidationError(f"{field} must be a non-empty UTC timestamp")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CaptureValidationError(f"{field} must be ISO-8601") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise CaptureValidationError(f"{field} must be timezone-aware UTC")
    return timestamp.astimezone(timezone.utc)


def _immutable_payload(value: Any) -> str:
    """Store payloads as canonical text so frozen records are deeply immutable."""

    return canonical_json(value)


@dataclass(frozen=True)
class PublicResponse:
    """One credential-free public response with distinct request/receive times."""

    stream: str
    endpoint: str
    requested_at: datetime
    received_at: datetime
    source_record_id: str
    payload_json: str
    request_params_json: str
    source_at: datetime | None = None
    source_sequence: int | None = None
    reconnected: bool = False
    partial_reason: str | None = None

    @classmethod
    def create(
        cls,
        *,
        stream: str,
        endpoint: str,
        requested_at: datetime,
        received_at: datetime,
        source_record_id: str,
        payload: Any,
        request_params: dict[str, str] | None = None,
        source_at: datetime | None = None,
        source_sequence: int | None = None,
        reconnected: bool = False,
        partial_reason: str | None = None,
    ) -> "PublicResponse":
        if not stream or not endpoint or not source_record_id:
            raise CaptureValidationError("public response identifiers must be non-empty")
        if requested_at >= received_at:
            raise CaptureValidationError("public response requested_at must precede received_at")
        utc_text(requested_at)
        utc_text(received_at)
        if source_at is not None:
            utc_text(source_at)
        if not isinstance(request_params or {}, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in (request_params or {}).items()
        ):
            raise CaptureValidationError("request_params must be an object of strings")
        if partial_reason is not None and (
            not isinstance(partial_reason, str) or not partial_reason
        ):
            raise CaptureValidationError("partial_reason must be null or non-empty text")
        if source_sequence is not None and (
            isinstance(source_sequence, bool)
            or not isinstance(source_sequence, int)
            or source_sequence < 0
        ):
            raise CaptureValidationError("source_sequence must be non-negative")
        return cls(
            stream=stream,
            endpoint=endpoint,
            requested_at=requested_at,
            received_at=received_at,
            source_record_id=source_record_id,
            payload_json=_immutable_payload(payload),
            request_params_json=_immutable_payload(request_params or {}),
            source_at=source_at,
            source_sequence=source_sequence,
            reconnected=reconnected,
            partial_reason=partial_reason,
        )

    def payload(self) -> Any:
        return json.loads(self.payload_json)

    def request_params(self) -> dict[str, str]:
        return cast(dict[str, str], json.loads(self.request_params_json))


@dataclass(frozen=True)
class CaptureRecord:
    """One immutable line in the point-in-time capture log."""

    record_type: str
    capture_id: str
    capture_sequence: int
    snapshot_id: str | None
    stream: str
    source_sequence: int | None
    requested_at: datetime
    received_at: datetime
    endpoint: str
    request_params_json: str
    source_record_id: str
    source_at: datetime | None
    payload_json: str

    @classmethod
    def create(
        cls,
        *,
        record_type: str,
        capture_sequence: int,
        snapshot_id: str | None,
        response: PublicResponse,
        payload: Any,
    ) -> "CaptureRecord":
        if record_type not in _CAPTURE_RECORD_TYPES:
            raise CaptureValidationError(f"unknown capture record type: {record_type}")
        if (
            isinstance(capture_sequence, bool)
            or not isinstance(capture_sequence, int)
            or capture_sequence <= 0
        ):
            raise CaptureValidationError("capture_sequence must be a positive integer")
        if snapshot_id is not None and (not isinstance(snapshot_id, str) or not snapshot_id):
            raise CaptureValidationError("snapshot_id must be null or a non-empty string")
        core = {
            "capture_sequence": capture_sequence,
            "endpoint": response.endpoint,
            "payload": payload,
            "received_at": utc_text(response.received_at),
            "record_type": record_type,
            "request_params": response.request_params(),
            "requested_at": utc_text(response.requested_at),
            "snapshot_id": snapshot_id,
            "source_record_id": response.source_record_id,
            "source_at": utc_text(response.source_at) if response.source_at else None,
            "source_sequence": response.source_sequence,
            "stream": response.stream,
        }
        digest = canonical_sha256(canonical_json(core).encode("utf-8"))
        return cls(
            record_type=record_type,
            capture_id=f"capture-record-{digest}",
            capture_sequence=capture_sequence,
            snapshot_id=snapshot_id,
            stream=response.stream,
            source_sequence=response.source_sequence,
            requested_at=response.requested_at,
            received_at=response.received_at,
            endpoint=response.endpoint,
            request_params_json=response.request_params_json,
            source_record_id=response.source_record_id,
            source_at=response.source_at,
            payload_json=_immutable_payload(payload),
        )

    def payload(self) -> Any:
        return json.loads(self.payload_json)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "capture_sequence": self.capture_sequence,
            "capture_schema_version": CAPTURE_SCHEMA_VERSION,
            "endpoint": self.endpoint,
            "payload": self.payload(),
            "received_at": utc_text(self.received_at),
            "record_type": self.record_type,
            "request_params": json.loads(self.request_params_json),
            "requested_at": utc_text(self.requested_at),
            "snapshot_id": self.snapshot_id,
            "source_record_id": self.source_record_id,
            "source_at": utc_text(self.source_at) if self.source_at else None,
            "source_sequence": self.source_sequence,
            "stream": self.stream,
        }


@dataclass(frozen=True)
class CaptureBundle:
    """Validated capture records plus completeness evidence."""

    venue: str
    records: tuple[CaptureRecord, ...]
    completeness: str
    warnings: tuple[str, ...]

    @property
    def source_endpoints(self) -> tuple[str, ...]:
        return tuple(sorted({record.endpoint for record in self.records}))


@dataclass(frozen=True)
class CaptureManifest:
    capture_id: str
    venue: str
    records_file: str
    records_sha256: str
    record_count: int
    capture_started_at: datetime
    capture_ended_at: datetime
    source_endpoints: tuple[str, ...]
    source_started_at: datetime | None
    source_ended_at: datetime | None
    sequence_completeness: str
    completeness: str
    warnings: tuple[str, ...]


_CAPTURE_RECORD_TYPES = {
    "event",
    "market_metadata",
    "order_book",
    "trade",
    "trade_page",
    "resolution",
    "gap",
}
_RECORD_FIELDS = {
    "capture_id",
    "capture_sequence",
    "capture_schema_version",
    "endpoint",
    "payload",
    "received_at",
    "record_type",
    "request_params",
    "requested_at",
    "snapshot_id",
    "source_record_id",
    "source_at",
    "source_sequence",
    "stream",
}
_MANIFEST_FIELDS = {
    "schema_version",
    "capture_id",
    "venue",
    "records_file",
    "records_sha256",
    "record_count",
    "capture_started_at",
    "capture_ended_at",
    "source_endpoints",
    "source_started_at",
    "source_ended_at",
    "sequence_completeness",
    "completeness",
    "warnings",
}


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CaptureValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_object(payload: str, *, location: str) -> dict[str, Any]:
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, CaptureValidationError) as exc:
        raise CaptureValidationError(f"invalid JSON at {location}: {exc}") from exc
    if not isinstance(value, dict):
        raise CaptureValidationError(f"{location} must contain an object")
    return value


def write_capture(bundle: CaptureBundle, directory: str | Path) -> Path:
    """Write an immutable capture manifest and canonical JSONL record file."""

    if not bundle.records:
        raise CaptureValidationError("cannot write an empty capture")
    if bundle.completeness not in {"complete", "partial"}:
        raise CaptureValidationError("completeness must be complete or partial")
    if not bundle.venue:
        raise CaptureValidationError("capture venue must be non-empty")
    has_gap = any(record.record_type == "gap" for record in bundle.records)
    if has_gap and bundle.completeness != "partial":
        raise CaptureValidationError("captures containing gaps must be partial")
    if has_gap and not bundle.warnings:
        raise CaptureValidationError("captures containing gaps require warnings")
    ordered = sorted(bundle.records, key=lambda item: item.capture_sequence)
    if [record.capture_sequence for record in ordered] != list(range(1, len(ordered) + 1)):
        raise CaptureValidationError("capture_sequence must be contiguous from one")
    _validate_declared_sequence_gaps(ordered)
    records_bytes = ("".join(canonical_json(record.to_dict()) + "\n" for record in ordered)).encode(
        "utf-8"
    )
    records_sha256 = canonical_sha256(records_bytes)
    capture_id = f"capture-{records_sha256}"
    manifest = {
        "capture_ended_at": utc_text(max(record.received_at for record in ordered)),
        "capture_id": capture_id,
        "capture_started_at": utc_text(min(record.requested_at for record in ordered)),
        "completeness": bundle.completeness,
        "record_count": len(ordered),
        "records_file": "capture.jsonl",
        "records_sha256": records_sha256,
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "source_endpoints": list(bundle.source_endpoints),
        "source_ended_at": _source_boundary(ordered, maximum=True),
        "source_started_at": _source_boundary(ordered, maximum=False),
        "sequence_completeness": _sequence_completeness(ordered),
        "venue": bundle.venue,
        "warnings": list(bundle.warnings),
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    target = Path(directory)
    _publish_two_file_directory(
        target,
        {"capture.jsonl": records_bytes, "manifest.json": manifest_bytes},
        error_prefix="immutable capture",
        validator=lambda candidate: load_capture(candidate / "manifest.json"),
    )
    return target / "manifest.json"


def _publish_two_file_directory(
    target: Path,
    files: dict[str, bytes],
    *,
    error_prefix: str,
    validator: Callable[[Path], object] | None = None,
) -> None:
    """Publish a complete two-file artifact with one directory rename."""

    if target.exists():
        if not target.is_dir() or set(path.name for path in target.iterdir()) != set(files):
            raise CaptureValidationError(f"refusing to overwrite {error_prefix}: {target}")
        if validator is not None:
            validator(target)
        for name, payload in files.items():
            if (target / name).read_bytes() != payload:
                raise CaptureValidationError(
                    f"refusing to overwrite {error_prefix}: {target / name}"
                )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        for name, payload in files.items():
            (temporary / name).write_bytes(payload)
        if validator is not None:
            validator(temporary)
        temporary.replace(target)
    except FileExistsError as exc:
        raise CaptureValidationError(f"refusing to overwrite {error_prefix}: {target}") from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def load_capture(path: str | Path) -> tuple[CaptureManifest, tuple[CaptureRecord, ...]]:
    """Load and integrity-check a canonical capture log."""

    manifest_path = Path(path).resolve()
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest_text = manifest_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CaptureValidationError("capture manifest must be UTF-8") from exc
    manifest = _load_object(manifest_text, location=str(manifest_path))
    if set(manifest) != _MANIFEST_FIELDS:
        raise CaptureValidationError("capture manifest fields do not match v1")
    if manifest["schema_version"] != CAPTURE_SCHEMA_VERSION:
        raise CaptureValidationError("unsupported capture schema version")
    records_file = _required_text(manifest["records_file"], "records_file")
    records_path = (manifest_path.parent / records_file).resolve()
    if records_path.parent != manifest_path.parent:
        raise CaptureValidationError("capture records must remain beside the manifest")
    records_bytes = records_path.read_bytes()
    records_sha256 = _required_text(manifest["records_sha256"], "records_sha256")
    if canonical_sha256(records_bytes) != records_sha256:
        raise CaptureValidationError("capture records_sha256 mismatch")
    try:
        records_text = records_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CaptureValidationError("capture records must be UTF-8") from exc
    if not records_text.endswith("\n"):
        raise CaptureValidationError("capture records must end with LF")
    raw_lines = records_text[:-1].split("\n")
    if raw_lines == [""]:
        raise CaptureValidationError("capture records cannot be empty")
    records: list[CaptureRecord] = []
    for number, line in enumerate(raw_lines, start=1):
        if not line:
            raise CaptureValidationError(f"capture line {number} is blank")
        value = _load_object(line, location=f"capture line {number}")
        if set(value) != _RECORD_FIELDS:
            raise CaptureValidationError(f"capture line {number} fields do not match v1")
        if line != canonical_json(value):
            raise CaptureValidationError(f"capture line {number} is not canonical JSON")
        if value["capture_schema_version"] != CAPTURE_SCHEMA_VERSION:
            raise CaptureValidationError("capture record schema version mismatch")
        if value["record_type"] not in _CAPTURE_RECORD_TYPES:
            raise CaptureValidationError("unknown capture record type")
        requested_at = parse_utc(value["requested_at"], field="requested_at")
        received_at = parse_utc(value["received_at"], field="received_at")
        if requested_at >= received_at:
            raise CaptureValidationError("capture requested_at must precede received_at")
        capture_sequence = _positive_int(value["capture_sequence"], "capture_sequence")
        source_sequence = value["source_sequence"]
        if source_sequence is not None:
            source_sequence = _non_negative_int(source_sequence, "source_sequence")
        snapshot_id = value["snapshot_id"]
        if snapshot_id is not None:
            snapshot_id = _required_text(snapshot_id, "snapshot_id")
        request_params = value["request_params"]
        if not isinstance(request_params, dict) or any(
            not isinstance(key, str) or not isinstance(item, str)
            for key, item in request_params.items()
        ):
            raise CaptureValidationError("request_params must be an object of strings")
        source_at_value = value["source_at"]
        source_at = (
            parse_utc(source_at_value, field="source_at") if source_at_value is not None else None
        )
        response = PublicResponse.create(
            stream=_required_text(value["stream"], "stream"),
            endpoint=_required_text(value["endpoint"], "endpoint"),
            requested_at=requested_at,
            received_at=received_at,
            source_record_id=_required_text(value["source_record_id"], "source_record_id"),
            payload=value["payload"],
            request_params=request_params,
            source_at=source_at,
            source_sequence=source_sequence,
        )
        record = CaptureRecord.create(
            record_type=_required_text(value["record_type"], "record_type"),
            capture_sequence=capture_sequence,
            snapshot_id=snapshot_id,
            response=response,
            payload=value["payload"],
        )
        if record.capture_id != value["capture_id"]:
            raise CaptureValidationError("capture record id mismatch")
        records.append(record)
    record_count = _positive_int(manifest["record_count"], "record_count")
    if len(records) != record_count:
        raise CaptureValidationError("capture record_count mismatch")
    if [record.capture_sequence for record in records] != list(range(1, len(records) + 1)):
        raise CaptureValidationError("capture_sequence is not contiguous")
    _validate_declared_sequence_gaps(records)
    expected_capture_id = f"capture-{canonical_sha256(records_bytes)}"
    if manifest["capture_id"] != expected_capture_id:
        raise CaptureValidationError("capture_id does not match record bytes")
    source_endpoints_value = manifest["source_endpoints"]
    if not isinstance(source_endpoints_value, list) or not source_endpoints_value:
        raise CaptureValidationError("source_endpoints must be a non-empty array")
    source_endpoints = tuple(
        _required_text(item, "source_endpoints[]") for item in source_endpoints_value
    )
    warnings_value = manifest["warnings"]
    if not isinstance(warnings_value, list):
        raise CaptureValidationError("warnings must be an array")
    warnings = tuple(_required_text(item, "warnings[]") for item in warnings_value)
    loaded_manifest = CaptureManifest(
        capture_id=expected_capture_id,
        venue=_required_text(manifest["venue"], "venue"),
        records_file=records_file,
        records_sha256=records_sha256,
        record_count=record_count,
        capture_started_at=parse_utc(manifest["capture_started_at"], field="capture_started_at"),
        capture_ended_at=parse_utc(manifest["capture_ended_at"], field="capture_ended_at"),
        source_endpoints=source_endpoints,
        source_started_at=(
            parse_utc(manifest["source_started_at"], field="source_started_at")
            if manifest["source_started_at"] is not None
            else None
        ),
        source_ended_at=(
            parse_utc(manifest["source_ended_at"], field="source_ended_at")
            if manifest["source_ended_at"] is not None
            else None
        ),
        sequence_completeness=_required_text(
            manifest["sequence_completeness"], "sequence_completeness"
        ),
        completeness=_required_text(manifest["completeness"], "completeness"),
        warnings=warnings,
    )
    if loaded_manifest.completeness not in {"complete", "partial"}:
        raise CaptureValidationError("capture completeness must be complete or partial")
    if loaded_manifest.capture_started_at != min(record.requested_at for record in records):
        raise CaptureValidationError("capture_started_at does not match records")
    if loaded_manifest.capture_ended_at != max(record.received_at for record in records):
        raise CaptureValidationError("capture_ended_at does not match records")
    actual_endpoints = tuple(sorted({record.endpoint for record in records}))
    if loaded_manifest.source_endpoints != actual_endpoints:
        raise CaptureValidationError("source_endpoints do not match capture records")
    if loaded_manifest.source_started_at != _source_datetime_boundary(records, maximum=False):
        raise CaptureValidationError("source_started_at does not match capture records")
    if loaded_manifest.source_ended_at != _source_datetime_boundary(records, maximum=True):
        raise CaptureValidationError("source_ended_at does not match capture records")
    if loaded_manifest.sequence_completeness != _sequence_completeness(records):
        raise CaptureValidationError("sequence_completeness does not match capture records")
    has_gap = any(record.record_type == "gap" for record in records)
    if has_gap and loaded_manifest.completeness != "partial":
        raise CaptureValidationError("capture with gap records must be partial")
    if has_gap and not loaded_manifest.warnings:
        raise CaptureValidationError("capture with gap records must include warnings")
    return loaded_manifest, tuple(records)


def _response_key(record: CaptureRecord) -> tuple[str, str, str, str, str]:
    return (
        record.stream,
        record.endpoint,
        utc_text(record.requested_at),
        utc_text(record.received_at),
        record.source_record_id,
    )


def _validate_declared_sequence_gaps(records: Iterable[CaptureRecord]) -> None:
    """Reject silent source-sequence discontinuities in written or loaded logs."""

    previous: dict[str, int] = {}
    seen_responses: set[tuple[str, str, str, str, str]] = set()
    declared: set[tuple[str, int, int]] = set()
    materialized = list(records)
    for record in materialized:
        if record.record_type != "gap":
            continue
        payload = record.payload()
        if not isinstance(payload, dict) or payload.get("kind") != "sequence_gap":
            continue
        expected = payload.get("expected_sequence")
        observed = payload.get("observed_sequence")
        if isinstance(expected, int) and isinstance(observed, int):
            declared.add((record.stream, expected, observed))
    for record in materialized:
        key = _response_key(record)
        if key in seen_responses:
            continue
        seen_responses.add(key)
        sequence = record.source_sequence
        if sequence is None:
            continue
        prior = previous.get(record.stream)
        if prior is not None and sequence != prior + 1:
            expected = prior + 1
            if (record.stream, expected, sequence) not in declared:
                raise CaptureValidationError(
                    f"undeclared source sequence gap on {record.stream}: "
                    f"expected={expected}, observed={sequence}"
                )
        previous[record.stream] = sequence


def _sequence_completeness(records: Iterable[CaptureRecord]) -> str:
    sequences = {record.source_sequence is not None for record in records}
    if sequences == {False}:
        return "not_available_polling"
    if sequences == {True}:
        return "validated"
    return "mixed"


def _source_datetime_boundary(
    records: Iterable[CaptureRecord], *, maximum: bool
) -> datetime | None:
    timestamps = [record.source_at for record in records if record.source_at is not None]
    if not timestamps:
        return None
    return max(timestamps) if maximum else min(timestamps)


def _source_boundary(records: Iterable[CaptureRecord], *, maximum: bool) -> str | None:
    value = _source_datetime_boundary(records, maximum=maximum)
    return utc_text(value) if value is not None else None


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CaptureValidationError(f"{field} must be a non-empty string")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CaptureValidationError(f"{field} must be a positive integer")
    return cast(int, value)


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CaptureValidationError(f"{field} must be a non-negative integer")
    return cast(int, value)
