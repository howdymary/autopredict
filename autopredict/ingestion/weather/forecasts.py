"""Fixture-backed weather forecast ingestion."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch
from autopredict.ingestion.weather.fixtures import (
    FORECAST_SOURCE,
    sample_forecast_records,
)


class FixtureWeatherForecastIngestor:
    """Deterministic weather-forecast ingestor."""

    name = "weather.forecasts.fixture"

    def load_fixture(self) -> IngestionBatch:
        return load_fixture_forecast_batch()


def sample_forecast_rows() -> tuple[dict[str, Any], ...]:
    """Return fixture weather forecasts as row dictionaries."""

    rows: list[dict[str, Any]] = []
    for record in sample_forecast_records():
        rows.append(
            {
                "record_id": record.record_id,
                "observed_at": record.observed_at,
                "payload": dict(record.payload),
                "metadata": dict(record.metadata),
            }
        )
    return tuple(rows)


def normalize_forecasts(rows: Sequence[dict[str, Any]]) -> IngestionBatch:
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
        source_config=FORECAST_SOURCE,
        evidence=evidence,
        metadata={"domain": "weather"},
    )


def load_fixture_forecast_batch() -> IngestionBatch:
    """Return normalized forecast batch."""

    return normalize_forecasts(sample_forecast_rows())
