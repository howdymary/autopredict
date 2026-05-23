"""Politics news normalization."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch, SourceConfig


NEWS_SOURCE = SourceConfig(name="politics.news", version="v1")


def normalize_news(
    rows: Sequence[dict[str, Any]],
    *,
    source_config: SourceConfig = NEWS_SOURCE,
) -> IngestionBatch:
    """Normalize politics news rows into the shared ingestion batch shape."""

    evidence = tuple(
        EvidenceRecord(
            source=NEWS_SOURCE.name,
            record_id=str(row["record_id"]),
            observed_at=row["observed_at"],
            payload=dict(row["payload"]),
            metadata={
                "record_type": "news",
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
