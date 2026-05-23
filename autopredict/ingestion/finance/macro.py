"""Finance macro release normalization."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch, SourceConfig


MACRO_SOURCE = SourceConfig(name="finance.macro", version="v1")


def normalize_macro_releases(
    rows: Sequence[dict[str, Any]],
    *,
    source_config: SourceConfig = MACRO_SOURCE,
) -> IngestionBatch:
    """Normalize macro release rows into the shared ingestion batch shape."""

    evidence = tuple(
        EvidenceRecord(
            source=MACRO_SOURCE.name,
            record_id=str(row["record_id"]),
            observed_at=row["observed_at"],
            payload=dict(row["payload"]),
            metadata={
                "record_type": "macro_release",
                **dict(row.get("metadata", {})),
            },
        )
        for row in rows
    )
    return IngestionBatch(
        source_config=source_config,
        evidence=evidence,
        metadata={"domain": "finance"},
    )
