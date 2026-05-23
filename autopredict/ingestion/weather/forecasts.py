"""Weather forecast normalization."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch, SourceConfig


FORECAST_SOURCE = SourceConfig(name="weather.forecasts", version="v1")


def normalize_forecasts(
    rows: Sequence[dict[str, Any]],
    *,
    source_config: SourceConfig = FORECAST_SOURCE,
) -> IngestionBatch:
    """Normalize weather forecast rows into the shared ingestion batch shape."""

    evidence = tuple(
        EvidenceRecord(
            source=FORECAST_SOURCE.name,
            record_id=str(row["record_id"]),
            observed_at=row["observed_at"],
            payload=dict(row["payload"]),
            metadata={
                "record_type": "forecast",
                **dict(row.get("metadata", {})),
            },
        )
        for row in rows
    )
    return IngestionBatch(
        source_config=source_config,
        evidence=evidence,
        metadata={"domain": "weather"},
    )
