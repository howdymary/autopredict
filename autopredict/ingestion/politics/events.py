"""Politics event normalization."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch, SourceConfig


EVENT_SOURCE = SourceConfig(name="politics.events", version="v1")


def normalize_events(
    rows: Sequence[dict[str, Any]],
    *,
    source_config: SourceConfig = EVENT_SOURCE,
) -> IngestionBatch:
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
        source_config=source_config,
        evidence=evidence,
        metadata={"domain": "politics"},
    )
