"""Fixture-backed politics event ingestion."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch
from autopredict.ingestion.politics.fixtures import EVENT_SOURCE, sample_event_records


class FixturePoliticalEventIngestor:
    """Deterministic politics-event ingestor."""

    name = "politics.events.fixture"

    def load_fixture(self) -> IngestionBatch:
        return load_fixture_event_batch()


def sample_event_rows() -> tuple[dict[str, Any], ...]:
    """Return fixture politics events as row dictionaries."""

    rows: list[dict[str, Any]] = []
    for record in sample_event_records():
        rows.append(
            {
                "record_id": record.record_id,
                "observed_at": record.observed_at,
                "payload": dict(record.payload),
                "metadata": dict(record.metadata),
            }
        )
    return tuple(rows)


def normalize_events(rows: Sequence[dict[str, Any]]) -> IngestionBatch:
    """Normalize event rows into the shared ingestion batch shape."""

    evidence = tuple(
        EvidenceRecord(
            source=EVENT_SOURCE.name,
            record_id=str(row["record_id"]),
            observed_at=row["observed_at"],
            payload=dict(row["payload"]),
            metadata={
                "record_type": "event",
                **dict(row.get("metadata", {})),
            },
        )
        for row in rows
    )
    return IngestionBatch(
        source_config=EVENT_SOURCE,
        evidence=evidence,
        metadata={"domain": "politics"},
    )


def load_fixture_event_batch() -> IngestionBatch:
    """Return normalized politics event batch."""

    return normalize_events(sample_event_rows())
