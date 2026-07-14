"""Contract tests for canonical manifest and JSONL datasets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from autopredict.evaluation import DatasetValidationError, load_dataset_v1


FIXTURE = Path(__file__).parent / "fixtures/datasets/resolved-v1/manifest.json"


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "dataset"
    shutil.copytree(FIXTURE.parent, target)
    return target / "manifest.json"


def _rewrite_records(manifest_path: Path, records: list[dict[str, object]]) -> None:
    records_path = manifest_path.parent / "records.jsonl"
    payload = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records
    )
    records_path.write_text(payload, encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["record_count"] = len(records)
    manifest["records_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _records(manifest_path: Path) -> list[dict[str, object]]:
    records_path = manifest_path.parent / "records.jsonl"
    return [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]


def test_load_dataset_v1_separates_observations_from_resolutions() -> None:
    dataset = load_dataset_v1(FIXTURE)

    assert len(dataset.observations) == 2
    assert len(dataset.resolutions) == 2
    assert len(dataset.rows) == 2
    assert not hasattr(dataset.observations[0], "outcome")
    assert not hasattr(dataset.observations[0], "resolved_at")
    assert dataset.manifest.completeness == "complete"


def test_dataset_rejects_unknown_schema_version(tmp_path: Path) -> None:
    manifest_path = _copy_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "autopredict.dataset.v999"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="unsupported schema_version"):
        load_dataset_v1(manifest_path)


def test_dataset_rejects_tampered_record_bytes(tmp_path: Path) -> None:
    manifest_path = _copy_fixture(tmp_path)
    records_path = manifest_path.parent / "records.jsonl"
    records_path.write_text(records_path.read_text() + "\n", encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="records_sha256 mismatch"):
        load_dataset_v1(manifest_path)


def test_dataset_rejects_record_path_traversal(tmp_path: Path) -> None:
    manifest_path = _copy_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records_file"] = "../records.jsonl"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="manifest directory"):
        load_dataset_v1(manifest_path)


def test_dataset_rejects_duplicate_raw_json_keys(tmp_path: Path) -> None:
    manifest_path = _copy_fixture(tmp_path)
    records_path = manifest_path.parent / "records.jsonl"
    lines = records_path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace(
        '"record_id":',
        '"record_id":"duplicate","record_id":',
        1,
    )
    payload = "\n".join(lines) + "\n"
    records_path.write_text(payload, encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="duplicate JSON key: record_id"):
        load_dataset_v1(manifest_path)


def test_dataset_requires_canonical_lf_termination(tmp_path: Path) -> None:
    manifest_path = _copy_fixture(tmp_path)
    records_path = manifest_path.parent / "records.jsonl"
    payload = records_path.read_bytes().removesuffix(b"\n")
    records_path.write_bytes(payload)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records_sha256"] = hashlib.sha256(payload).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="single LF"):
        load_dataset_v1(manifest_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda record: record.__setitem__("fair_prob", 0.9), "unknown=\\['fair_prob'\\]"),
        (
            lambda record: record.__setitem__("observed_at", "2026-01-01T12:00:00"),
            "timezone-aware UTC",
        ),
        (
            lambda record: record["order_book"].__setitem__("bids", [[0.59, 0.0]]),
            "size must be positive",
        ),
        (lambda record: record["order_book"].__setitem__("bids", [[0.7, 1.0]]), "is crossed"),
    ],
)
def test_dataset_rejects_leakage_time_and_book_errors(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    manifest_path = _copy_fixture(tmp_path)
    records = _records(manifest_path)
    mutation(records[0])
    _rewrite_records(manifest_path, records)

    with pytest.raises(DatasetValidationError, match=message):
        load_dataset_v1(manifest_path)


def test_dataset_rejects_duplicate_record_ids(tmp_path: Path) -> None:
    manifest_path = _copy_fixture(tmp_path)
    records = _records(manifest_path)
    records[1]["record_id"] = records[0]["record_id"]
    _rewrite_records(manifest_path, records)

    with pytest.raises(DatasetValidationError, match="duplicate record_id"):
        load_dataset_v1(manifest_path)


def test_dataset_rejects_resolution_before_observation(tmp_path: Path) -> None:
    manifest_path = _copy_fixture(tmp_path)
    records = _records(manifest_path)
    records[2]["resolved_at"] = "2025-12-31T00:00:00Z"
    _rewrite_records(manifest_path, records)

    with pytest.raises(DatasetValidationError, match="resolution must follow observation"):
        load_dataset_v1(manifest_path)


def test_dataset_rejects_observations_outside_capture_bounds(tmp_path: Path) -> None:
    manifest_path = _copy_fixture(tmp_path)
    records = _records(manifest_path)
    records[0]["observed_at"] = "2026-01-03T00:00:00Z"
    _rewrite_records(manifest_path, records)

    with pytest.raises(DatasetValidationError, match="outside manifest capture bounds"):
        load_dataset_v1(manifest_path)


def test_dataset_rejects_market_mapped_to_multiple_event_ids(tmp_path: Path) -> None:
    manifest_path = _copy_fixture(tmp_path)
    records = _records(manifest_path)
    duplicate_observation = dict(records[0])
    duplicate_observation["record_id"] = "obs-election-fabricated-event"
    duplicate_observation["event_id"] = "event-election-fabricated"
    duplicate_resolution = dict(records[2])
    duplicate_resolution["record_id"] = "resolution-election-fabricated-event"
    duplicate_resolution["event_id"] = "event-election-fabricated"
    records.extend((duplicate_observation, duplicate_resolution))
    _rewrite_records(manifest_path, records)

    with pytest.raises(DatasetValidationError, match="maps to multiple event_ids"):
        load_dataset_v1(manifest_path)
