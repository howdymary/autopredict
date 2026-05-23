"""Weather observation normalization."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import IngestionBatch, SourceConfig, TimeSeriesPoint


OBSERVATION_SOURCE = SourceConfig(name="weather.observations", version="v1")


def normalize_observations(
    rows: Sequence[dict[str, Any]],
    *,
    source_config: SourceConfig = OBSERVATION_SOURCE,
) -> IngestionBatch:
    """Normalize observation rows into the shared ingestion batch shape."""

    series = tuple(
        TimeSeriesPoint(
            series=str(row["series"]),
            observed_at=row["observed_at"],
            value=float(row["value"]),
            metadata=dict(row.get("metadata", {})),
        )
        for row in rows
    )
    return IngestionBatch(
        source_config=source_config,
        series=series,
        metadata={"domain": "weather"},
    )
