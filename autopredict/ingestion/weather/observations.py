"""Fixture-backed weather observation ingestion."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import IngestionBatch, TimeSeriesPoint
from autopredict.ingestion.weather.fixtures import (
    OBSERVATION_SOURCE,
    sample_observation_points,
)


class FixtureWeatherObservationIngestor:
    """Deterministic weather-observation ingestor."""

    name = "weather.observations.fixture"

    def load_fixture(self) -> IngestionBatch:
        return load_fixture_observation_batch()


def sample_observation_rows() -> tuple[dict[str, Any], ...]:
    """Return fixture weather observations as row dictionaries."""

    rows: list[dict[str, Any]] = []
    for point in sample_observation_points():
        rows.append(
            {
                "series": point.series,
                "observed_at": point.observed_at,
                "value": point.value,
                "metadata": dict(point.metadata),
            }
        )
    return tuple(rows)


def normalize_observations(rows: Sequence[dict[str, Any]]) -> IngestionBatch:
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
        source_config=OBSERVATION_SOURCE,
        series=series,
        metadata={"domain": "weather"},
    )


def load_fixture_observation_batch() -> IngestionBatch:
    """Return normalized observation batch."""

    return normalize_observations(sample_observation_rows())
