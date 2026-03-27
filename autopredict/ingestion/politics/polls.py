"""Fixture-backed politics poll ingestion."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch
from autopredict.ingestion.politics.fixtures import POLL_SOURCE, sample_poll_records


class FixturePoliticalPollIngestor:
    """Deterministic politics-poll ingestor."""

    name = "politics.polls.fixture"

    def load_fixture(self) -> IngestionBatch:
        return load_fixture_poll_batch()


def sample_poll_rows() -> tuple[dict[str, Any], ...]:
    """Return fixture politics polls as row dictionaries."""

    rows: list[dict[str, Any]] = []
    for record in sample_poll_records():
        rows.append(
            {
                "record_id": record.record_id,
                "observed_at": record.observed_at,
                "payload": dict(record.payload),
                "metadata": dict(record.metadata),
            }
        )
    return tuple(rows)


def normalize_polls(rows: Sequence[dict[str, Any]]) -> IngestionBatch:
    """Normalize poll rows into the shared ingestion batch shape."""

    evidence = tuple(
        EvidenceRecord(
            source=POLL_SOURCE.name,
            record_id=str(row["record_id"]),
            observed_at=row["observed_at"],
            payload=dict(row["payload"]),
            metadata={
                "record_type": "poll",
                **dict(row.get("metadata", {})),
            },
        )
        for row in rows
    )
    return IngestionBatch(
        source_config=POLL_SOURCE,
        evidence=evidence,
        metadata={"domain": "politics"},
    )


def load_fixture_poll_batch() -> IngestionBatch:
    """Return normalized politics poll batch."""

    return normalize_polls(sample_poll_rows())
