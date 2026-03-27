"""Fixture-backed politics news ingestion."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch
from autopredict.ingestion.politics.fixtures import NEWS_SOURCE, sample_news_records


class FixturePoliticalNewsIngestor:
    """Deterministic politics-news ingestor."""

    name = "politics.news.fixture"

    def load_fixture(self) -> IngestionBatch:
        return load_fixture_news_batch()


def sample_news_rows() -> tuple[dict[str, Any], ...]:
    """Return fixture politics news as row dictionaries."""

    rows: list[dict[str, Any]] = []
    for record in sample_news_records():
        rows.append(
            {
                "record_id": record.record_id,
                "observed_at": record.observed_at,
                "payload": dict(record.payload),
                "metadata": dict(record.metadata),
            }
        )
    return tuple(rows)


def normalize_news(rows: Sequence[dict[str, Any]]) -> IngestionBatch:
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
        source_config=NEWS_SOURCE,
        evidence=evidence,
        metadata={"domain": "politics"},
    )


def load_fixture_news_batch() -> IngestionBatch:
    """Return normalized politics news batch."""

    return normalize_news(sample_news_rows())
