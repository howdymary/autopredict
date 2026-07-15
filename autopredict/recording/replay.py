"""Deterministic conversion from capture logs to canonical evaluation datasets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from autopredict.evaluation.contracts import DATASET_SCHEMA_VERSION, load_dataset_v1
from autopredict.recording.contracts import (
    CaptureRecord,
    CaptureValidationError,
    canonical_json,
    canonical_sha256,
    load_capture,
    parse_utc,
    _publish_two_file_directory,
    utc_text,
)


def replay_capture(capture_manifest: str | Path, output_directory: str | Path) -> Path:
    """Materialize a byte-stable Packet 3 dataset from a trusted capture log."""

    manifest, records = load_capture(capture_manifest)
    gaps = [record for record in records if record.record_type == "gap"]
    completeness = "partial" if gaps or manifest.completeness == "partial" else "complete"
    warnings = list(manifest.warnings)
    for gap in gaps:
        warning = _gap_warning(gap)
        if warning not in warnings:
            warnings.append(warning)

    snapshot_records: dict[str, dict[str, CaptureRecord]] = {}
    resolutions: dict[tuple[str, str], CaptureRecord] = {}
    for record in records:
        if record.record_type in {"event", "market_metadata", "order_book"}:
            if record.snapshot_id is None:
                raise CaptureValidationError(
                    f"{record.record_type} capture record requires snapshot_id"
                )
            group = snapshot_records.setdefault(record.snapshot_id, {})
            if record.record_type in group:
                raise CaptureValidationError(
                    f"duplicate {record.record_type} in snapshot {record.snapshot_id}"
                )
            group[record.record_type] = record
        elif record.record_type == "resolution":
            payload = _object(record.payload(), "resolution payload")
            key = (
                _text(payload.get("event_id"), "resolution.event_id"),
                _text(payload.get("market_id"), "resolution.market_id"),
            )
            if key in resolutions:
                raise CaptureValidationError(f"duplicate captured resolution for {key}")
            resolutions[key] = record

    observations: list[dict[str, Any]] = []
    referenced_resolutions: set[tuple[str, str]] = set()
    for snapshot_id in sorted(snapshot_records):
        group = snapshot_records[snapshot_id]
        required = {"event", "market_metadata", "order_book"}
        missing = sorted(required - set(group))
        if missing:
            raise CaptureValidationError(f"snapshot {snapshot_id} is incomplete: missing {missing}")
        event_record = group["event"]
        market_record = group["market_metadata"]
        book_record = group["order_book"]
        event = _object(event_record.payload(), "event payload")
        market = _object(market_record.payload(), "market metadata payload")
        book = _object(book_record.payload(), "order book payload")
        event_id = _text(event.get("event_id"), "event.event_id")
        market_id = _text(market.get("market_id"), "market.market_id")
        if market.get("event_id") != event_id:
            raise CaptureValidationError("market metadata event_id does not match event")
        if book.get("market_id") != market_id:
            raise CaptureValidationError("order book market_id does not match metadata")
        resolution_key = (event_id, market_id)
        if resolution_key not in resolutions:
            raise CaptureValidationError(
                f"snapshot {snapshot_id} has no separate captured resolution"
            )
        referenced_resolutions.add(resolution_key)
        observed_at = max(market_record.received_at, book_record.received_at)
        observation_core = {
            "category": _text(market.get("category", event.get("category")), "market.category"),
            "event_id": event_id,
            "expiry": _text(market.get("expiry"), "market.expiry"),
            "market_id": market_id,
            "market_probability": market.get("market_probability"),
            "observed_at": utc_text(observed_at),
            "order_book": {
                "asks": book.get("asks"),
                "bids": book.get("bids"),
            },
            "provenance": {
                "source": "polymarket-capture-v1",
                "source_record_id": (f"{market_record.capture_id}+{book_record.capture_id}"),
            },
            "question": _text(market.get("question"), "market.question"),
            "record_type": "market_observation",
        }
        observations.append(
            {
                **observation_core,
                "record_id": _stable_id("observation", observation_core),
            }
        )

    if not observations:
        raise CaptureValidationError("capture contains no replayable snapshots")
    unused_resolutions = sorted(set(resolutions) - referenced_resolutions)
    if unused_resolutions:
        raise CaptureValidationError(
            f"capture has resolutions without snapshots: {unused_resolutions}"
        )

    resolution_rows: list[dict[str, Any]] = []
    for event_id, market_id in sorted(referenced_resolutions):
        record = resolutions[(event_id, market_id)]
        payload = _object(record.payload(), "resolution payload")
        resolved_at = _text(payload.get("resolved_at"), "resolution.resolved_at")
        parsed_resolved_at = parse_utc(resolved_at, field="resolution.resolved_at")
        if parsed_resolved_at > record.received_at:
            raise CaptureValidationError(
                "captured resolution predates its declared resolved_at timestamp"
            )
        outcome = payload.get("outcome")
        if isinstance(outcome, bool) or outcome not in {0, 1}:
            raise CaptureValidationError("captured resolution outcome must be 0 or 1")
        resolution_core = {
            "event_id": event_id,
            "market_id": market_id,
            "outcome": outcome,
            "provenance": {
                "source": "polymarket-capture-v1",
                "source_record_id": record.capture_id,
            },
            "record_type": "resolution",
            "resolved_at": resolved_at,
        }
        resolution_rows.append(
            {
                **resolution_core,
                "record_id": _stable_id("resolution", resolution_core),
            }
        )

    ordered_observations = sorted(
        observations,
        key=lambda item: (
            item["observed_at"],
            item["event_id"],
            item["market_id"],
            item["record_id"],
        ),
    )
    dataset_records = ordered_observations + resolution_rows
    records_bytes = ("".join(canonical_json(record) + "\n" for record in dataset_records)).encode(
        "utf-8"
    )
    records_sha256 = canonical_sha256(records_bytes)
    dataset_manifest = {
        "capture_ended_at": utc_text(manifest.capture_ended_at),
        "capture_started_at": utc_text(manifest.capture_started_at),
        "completeness": completeness,
        "dataset_id": f"replay-{manifest.capture_id}",
        "record_count": len(dataset_records),
        "records_file": "records.jsonl",
        "records_sha256": records_sha256,
        "schema_version": DATASET_SCHEMA_VERSION,
        "source_endpoints": list(manifest.source_endpoints),
        "venue": manifest.venue,
        "warnings": warnings,
    }
    manifest_bytes = (
        json.dumps(dataset_manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")

    # Validate in isolation before publishing any output. No capture-specific
    # relaxation or partial output can silently enter evaluation.
    with tempfile.TemporaryDirectory(prefix="autopredict-replay-") as temporary:
        temporary_path = Path(temporary)
        (temporary_path / "records.jsonl").write_bytes(records_bytes)
        candidate_manifest = temporary_path / "manifest.json"
        candidate_manifest.write_bytes(manifest_bytes)
        load_dataset_v1(candidate_manifest)

    target = Path(output_directory)
    _publish_two_file_directory(
        target,
        {"manifest.json": manifest_bytes, "records.jsonl": records_bytes},
        error_prefix="replay output",
    )
    return target / "manifest.json"


def _stable_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def _gap_warning(record: CaptureRecord) -> str:
    payload = _object(record.payload(), "gap payload")
    return (
        f"{payload.get('kind')} on {payload.get('stream')}: "
        f"expected={payload.get('expected_sequence')}, "
        f"observed={payload.get('observed_sequence')}"
    )


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CaptureValidationError(f"{location} must be an object")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise CaptureValidationError(f"{location} must be a non-empty string")
    return value
