"""Versioned point-in-time dataset contracts for canonical evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

DATASET_SCHEMA_VERSION = "autopredict.dataset.v1"


class DatasetValidationError(ValueError):
    """Raised when a dataset fails a fail-closed contract check."""


@dataclass(frozen=True)
class PriceLevelV1:
    """One price/size level in a point-in-time order book."""

    price: float
    size: float


@dataclass(frozen=True)
class OrderBookV1:
    """Ordered, non-crossed binary-market book."""

    bids: tuple[PriceLevelV1, ...]
    asks: tuple[PriceLevelV1, ...]


@dataclass(frozen=True)
class MarketObservationV1:
    """Forecast-safe observation that structurally excludes realized labels."""

    record_id: str
    event_id: str
    market_id: str
    question: str
    category: str
    observed_at: datetime
    expiry: datetime
    market_probability: float
    order_book: OrderBookV1
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class ResolutionV1:
    """Realized label stored separately from every forecast-safe observation."""

    record_id: str
    event_id: str
    market_id: str
    resolved_at: datetime
    outcome: int
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class ResolvedEvaluationRowV1:
    """Observation joined to its label only inside the evaluation boundary."""

    observation: MarketObservationV1
    resolution: ResolutionV1


@dataclass(frozen=True)
class DatasetManifestV1:
    """Immutable dataset inventory and byte-integrity metadata."""

    dataset_id: str
    venue: str
    records_file: str
    records_sha256: str
    record_count: int
    capture_started_at: datetime
    capture_ended_at: datetime
    source_endpoints: tuple[str, ...]
    completeness: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedDatasetV1:
    """Fully validated canonical dataset."""

    manifest: DatasetManifestV1
    observations: tuple[MarketObservationV1, ...]
    resolutions: tuple[ResolutionV1, ...]
    rows: tuple[ResolvedEvaluationRowV1, ...]
    manifest_sha256: str
    records_sha256: str
    dataset_sha256: str


_MANIFEST_FIELDS = {
    "schema_version",
    "dataset_id",
    "venue",
    "records_file",
    "records_sha256",
    "record_count",
    "capture_started_at",
    "capture_ended_at",
    "source_endpoints",
    "completeness",
    "warnings",
}
_OBSERVATION_FIELDS = {
    "record_type",
    "record_id",
    "event_id",
    "market_id",
    "question",
    "category",
    "observed_at",
    "expiry",
    "market_probability",
    "order_book",
    "provenance",
}
_RESOLUTION_FIELDS = {
    "record_type",
    "record_id",
    "event_id",
    "market_id",
    "resolved_at",
    "outcome",
    "provenance",
}


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DatasetValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(payload: str, *, location: str) -> dict[str, Any]:
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, DatasetValidationError) as exc:
        raise DatasetValidationError(f"invalid JSON at {location}: {exc}") from exc
    if not isinstance(value, dict):
        raise DatasetValidationError(f"{location} must contain a JSON object")
    return value


def _require_exact_fields(value: Mapping[str, Any], fields: set[str], *, location: str) -> None:
    actual = set(value)
    missing = sorted(fields - actual)
    unknown = sorted(actual - fields)
    if missing or unknown:
        raise DatasetValidationError(
            f"{location} fields mismatch: missing={missing}, unknown={unknown}"
        )


def _require_string(value: Any, *, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{location} must be a non-empty string")
    return value


def _parse_utc(value: Any, *, location: str) -> datetime:
    text = _require_string(value, location=location)
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatasetValidationError(f"{location} is not a valid ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise DatasetValidationError(f"{location} must be timezone-aware UTC")
    return timestamp.astimezone(timezone.utc)


def _finite_float(value: Any, *, location: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DatasetValidationError(f"{location} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise DatasetValidationError(f"{location} must be finite and in [{minimum}, {maximum}]")
    return result


def _parse_provenance(value: Any, *, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise DatasetValidationError(f"{location} must be an object")
    source = _require_string(value.get("source"), location=f"{location}.source")
    source_record_id = _require_string(
        value.get("source_record_id"),
        location=f"{location}.source_record_id",
    )
    if set(value) != {"source", "source_record_id"}:
        raise DatasetValidationError(f"{location} permits only source and source_record_id")
    return {"source": source, "source_record_id": source_record_id}


def _parse_levels(value: Any, *, location: str, descending: bool) -> tuple[PriceLevelV1, ...]:
    if not isinstance(value, list) or not value:
        raise DatasetValidationError(f"{location} must be a non-empty array")
    levels: list[PriceLevelV1] = []
    for index, item in enumerate(value):
        if not isinstance(item, list) or len(item) != 2:
            raise DatasetValidationError(f"{location}[{index}] must be [price, size]")
        price = _finite_float(
            item[0],
            location=f"{location}[{index}].price",
            minimum=0.0,
            maximum=1.0,
        )
        size = _finite_float(
            item[1],
            location=f"{location}[{index}].size",
            minimum=0.0,
            maximum=float("inf"),
        )
        if size <= 0.0:
            raise DatasetValidationError(f"{location}[{index}].size must be positive")
        levels.append(PriceLevelV1(price=price, size=size))
    prices = [level.price for level in levels]
    expected = sorted(prices, reverse=descending)
    if prices != expected:
        direction = "descending" if descending else "ascending"
        raise DatasetValidationError(f"{location} prices must be {direction}")
    return tuple(levels)


def _parse_order_book(value: Any, *, location: str) -> OrderBookV1:
    if not isinstance(value, dict) or set(value) != {"bids", "asks"}:
        raise DatasetValidationError(f"{location} must contain only bids and asks")
    bids = _parse_levels(value["bids"], location=f"{location}.bids", descending=True)
    asks = _parse_levels(value["asks"], location=f"{location}.asks", descending=False)
    if bids[0].price > asks[0].price:
        raise DatasetValidationError(f"{location} is crossed")
    return OrderBookV1(bids=bids, asks=asks)


def _parse_observation(value: Mapping[str, Any], *, location: str) -> MarketObservationV1:
    _require_exact_fields(value, _OBSERVATION_FIELDS, location=location)
    if value["record_type"] != "market_observation":
        raise DatasetValidationError(f"{location}.record_type must be market_observation")
    observed_at = _parse_utc(value["observed_at"], location=f"{location}.observed_at")
    expiry = _parse_utc(value["expiry"], location=f"{location}.expiry")
    if observed_at >= expiry:
        raise DatasetValidationError(f"{location}.observed_at must precede expiry")
    return MarketObservationV1(
        record_id=_require_string(value["record_id"], location=f"{location}.record_id"),
        event_id=_require_string(value["event_id"], location=f"{location}.event_id"),
        market_id=_require_string(value["market_id"], location=f"{location}.market_id"),
        question=_require_string(value["question"], location=f"{location}.question"),
        category=_require_string(value["category"], location=f"{location}.category"),
        observed_at=observed_at,
        expiry=expiry,
        market_probability=_finite_float(
            value["market_probability"],
            location=f"{location}.market_probability",
            minimum=0.0,
            maximum=1.0,
        ),
        order_book=_parse_order_book(value["order_book"], location=f"{location}.order_book"),
        provenance=_parse_provenance(value["provenance"], location=f"{location}.provenance"),
    )


def _parse_resolution(value: Mapping[str, Any], *, location: str) -> ResolutionV1:
    _require_exact_fields(value, _RESOLUTION_FIELDS, location=location)
    if value["record_type"] != "resolution":
        raise DatasetValidationError(f"{location}.record_type must be resolution")
    outcome = value["outcome"]
    if isinstance(outcome, bool) or outcome not in (0, 1):
        raise DatasetValidationError(f"{location}.outcome must be 0 or 1")
    return ResolutionV1(
        record_id=_require_string(value["record_id"], location=f"{location}.record_id"),
        event_id=_require_string(value["event_id"], location=f"{location}.event_id"),
        market_id=_require_string(value["market_id"], location=f"{location}.market_id"),
        resolved_at=_parse_utc(value["resolved_at"], location=f"{location}.resolved_at"),
        outcome=int(outcome),
        provenance=_parse_provenance(value["provenance"], location=f"{location}.provenance"),
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _decode_utf8(payload: bytes, *, location: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetValidationError(f"{location} must be valid UTF-8") from exc


def load_dataset_v1(path: str | Path) -> ResolvedDatasetV1:
    """Load and fully validate a v1 manifest plus canonical JSONL records."""

    manifest_path = Path(path).resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest_value = _load_json(
        _decode_utf8(manifest_bytes, location=str(manifest_path)),
        location=str(manifest_path),
    )
    _require_exact_fields(manifest_value, _MANIFEST_FIELDS, location="manifest")
    if manifest_value["schema_version"] != DATASET_SCHEMA_VERSION:
        raise DatasetValidationError(
            f"unsupported schema_version: {manifest_value['schema_version']!r}"
        )

    records_file = _require_string(manifest_value["records_file"], location="records_file")
    records_path = (manifest_path.parent / records_file).resolve()
    if manifest_path.parent != records_path.parent:
        raise DatasetValidationError("records_file must stay within the manifest directory")
    records_bytes = records_path.read_bytes()
    records_sha256 = _sha256(records_bytes)
    expected_sha256 = _require_string(
        manifest_value["records_sha256"],
        location="records_sha256",
    )
    if records_sha256 != expected_sha256:
        raise DatasetValidationError(
            f"records_sha256 mismatch: expected {expected_sha256}, got {records_sha256}"
        )

    record_count = manifest_value["record_count"]
    if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count <= 0:
        raise DatasetValidationError("record_count must be a positive integer")
    source_endpoints_value = manifest_value["source_endpoints"]
    if not isinstance(source_endpoints_value, list) or not source_endpoints_value:
        raise DatasetValidationError("source_endpoints must be a non-empty array")
    source_endpoints = tuple(
        _require_string(item, location="source_endpoints[]") for item in source_endpoints_value
    )
    warnings_value = manifest_value["warnings"]
    if not isinstance(warnings_value, list):
        raise DatasetValidationError("warnings must be an array")
    warnings = tuple(_require_string(item, location="warnings[]") for item in warnings_value)
    completeness = _require_string(manifest_value["completeness"], location="completeness")
    if completeness not in {"complete", "partial"}:
        raise DatasetValidationError("completeness must be complete or partial")
    capture_started_at = _parse_utc(
        manifest_value["capture_started_at"],
        location="capture_started_at",
    )
    capture_ended_at = _parse_utc(
        manifest_value["capture_ended_at"],
        location="capture_ended_at",
    )
    if capture_started_at > capture_ended_at:
        raise DatasetValidationError("capture_started_at must not follow capture_ended_at")

    records_text = _decode_utf8(records_bytes, location=str(records_path))
    if not records_text.endswith("\n"):
        raise DatasetValidationError("records file must end with a single LF after every record")

    observations: list[MarketObservationV1] = []
    resolutions: list[ResolutionV1] = []
    seen_record_ids: set[str] = set()
    lines = records_text[:-1].split("\n")
    if len(lines) != record_count:
        raise DatasetValidationError(
            f"record_count mismatch: expected {record_count}, got {len(lines)}"
        )
    for index, line in enumerate(lines, start=1):
        if not line:
            raise DatasetValidationError(f"records line {index} is blank")
        value = _load_json(line, location=f"records line {index}")
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if line != canonical:
            raise DatasetValidationError(f"records line {index} is not canonical JSON")
        record_type = value.get("record_type")
        if record_type == "market_observation":
            parsed_observation = _parse_observation(value, location=f"records line {index}")
            observations.append(parsed_observation)
            record_id = parsed_observation.record_id
        elif record_type == "resolution":
            parsed_resolution = _parse_resolution(value, location=f"records line {index}")
            resolutions.append(parsed_resolution)
            record_id = parsed_resolution.record_id
        else:
            raise DatasetValidationError(
                f"records line {index} has unknown record_type {record_type!r}"
            )
        if record_id in seen_record_ids:
            raise DatasetValidationError(f"duplicate record_id: {record_id}")
        seen_record_ids.add(record_id)

    if not observations:
        raise DatasetValidationError("dataset contains no market observations")
    event_id_by_market: dict[str, str] = {}
    for observation in observations:
        if not capture_started_at <= observation.observed_at <= capture_ended_at:
            raise DatasetValidationError(
                f"observation {observation.record_id!r} falls outside manifest capture bounds"
            )
        existing_event_id = event_id_by_market.setdefault(
            observation.market_id,
            observation.event_id,
        )
        if existing_event_id != observation.event_id:
            raise DatasetValidationError(
                f"market_id={observation.market_id!r} maps to multiple event_ids: "
                f"{existing_event_id!r} and {observation.event_id!r}"
            )

    resolution_by_key: dict[tuple[str, str], ResolutionV1] = {}
    for resolved_record in resolutions:
        key = (resolved_record.event_id, resolved_record.market_id)
        if key in resolution_by_key:
            raise DatasetValidationError(
                f"multiple resolutions for event_id={key[0]!r}, market_id={key[1]!r}"
            )
        resolution_by_key[key] = resolved_record

    rows: list[ResolvedEvaluationRowV1] = []
    used_resolution_keys: set[tuple[str, str]] = set()
    for observation in observations:
        key = (observation.event_id, observation.market_id)
        matched_resolution = resolution_by_key.get(key)
        if matched_resolution is None:
            raise DatasetValidationError(
                f"missing resolution for event_id={key[0]!r}, market_id={key[1]!r}"
            )
        if matched_resolution.resolved_at <= observation.observed_at:
            raise DatasetValidationError(
                f"resolution must follow observation {observation.record_id!r}"
            )
        rows.append(
            ResolvedEvaluationRowV1(
                observation=observation,
                resolution=matched_resolution,
            )
        )
        used_resolution_keys.add(key)
    unused = sorted(set(resolution_by_key) - used_resolution_keys)
    if unused:
        raise DatasetValidationError(f"resolutions without observations: {unused}")

    manifest = DatasetManifestV1(
        dataset_id=_require_string(manifest_value["dataset_id"], location="dataset_id"),
        venue=_require_string(manifest_value["venue"], location="venue"),
        records_file=records_file,
        records_sha256=records_sha256,
        record_count=record_count,
        capture_started_at=capture_started_at,
        capture_ended_at=capture_ended_at,
        source_endpoints=source_endpoints,
        completeness=completeness,
        warnings=warnings,
    )
    ordered_rows = tuple(
        sorted(
            rows,
            key=lambda item: (
                item.observation.observed_at,
                item.observation.event_id,
                item.observation.market_id,
                item.observation.record_id,
            ),
        )
    )
    manifest_sha256 = _sha256(manifest_bytes)
    dataset_sha256 = _sha256(manifest_bytes + b"\0" + records_bytes)
    return ResolvedDatasetV1(
        manifest=manifest,
        observations=tuple(observations),
        resolutions=tuple(resolutions),
        rows=ordered_rows,
        manifest_sha256=manifest_sha256,
        records_sha256=records_sha256,
        dataset_sha256=dataset_sha256,
    )
