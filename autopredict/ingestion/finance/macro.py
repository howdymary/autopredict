"""Fixture-backed macro release ingestion."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch
from autopredict.ingestion.finance.fixtures import MACRO_SOURCE, sample_macro_records


class FixtureMacroIngestor:
    """Deterministic macro-release ingestor for finance fixtures."""

    name = "finance.macro.fixture"

    def load_fixture(self) -> IngestionBatch:
        return load_fixture_macro_batch()


def sample_macro_rows() -> tuple[dict[str, Any], ...]:
    """Return fixture macro releases as row dictionaries."""

    rows: list[dict[str, Any]] = []
    for record in sample_macro_records():
        rows.append(
            {
                "record_id": record.record_id,
                "observed_at": record.observed_at,
                "payload": dict(record.payload),
                "metadata": dict(record.metadata),
            }
        )
    return tuple(rows)


def normalize_macro_releases(rows: Sequence[dict[str, Any]]) -> IngestionBatch:
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
        source_config=MACRO_SOURCE,
        evidence=evidence,
        metadata={"domain": "finance"},
    )


def load_fixture_macro_batch() -> IngestionBatch:
    """Return normalized fixture macro batch."""

    return normalize_macro_releases(sample_macro_rows())
