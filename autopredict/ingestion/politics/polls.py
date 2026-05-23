"""Politics poll normalization."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch, SourceConfig


POLL_SOURCE = SourceConfig(name="politics.polls", version="v1")


def normalize_polls(
    rows: Sequence[dict[str, Any]],
    *,
    source_config: SourceConfig = POLL_SOURCE,
) -> IngestionBatch:
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
        source_config=source_config,
        evidence=evidence,
        metadata={"domain": "politics"},
    )
