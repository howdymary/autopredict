"""Deterministic fixture data for weather evidence ingestion."""

from __future__ import annotations

from datetime import datetime, timedelta

from autopredict.ingestion.base import EvidenceRecord, SourceConfig, TimeSeriesPoint

FORECAST_SOURCE = SourceConfig(name="weather.forecasts", version="fixture.v1")
OBSERVATION_SOURCE = SourceConfig(name="weather.observations", version="fixture.v1")


def sample_forecast_records() -> tuple[EvidenceRecord, ...]:
    """Return deterministic weather forecast records."""

    base = datetime(2026, 8, 10, 6, 0, 0)
    return (
        EvidenceRecord(
            source=FORECAST_SOURCE.name,
            record_id="chi-temp-2026-08-11",
            observed_at=base,
            payload={"region": "chicago", "temperature_f": 92.0, "precip_probability": 0.10},
            metadata={"market_family": "temperature", "regime": "watch"},
        ),
        EvidenceRecord(
            source=FORECAST_SOURCE.name,
            record_id="gulf-storm-2026-08-11",
            observed_at=base + timedelta(hours=3),
            payload={"region": "gulf", "wind_speed_mph": 55.0, "landfall_probability": 0.35},
            metadata={"market_family": "storm", "regime": "warning"},
        ),
    )


def sample_observation_points() -> tuple[TimeSeriesPoint, ...]:
    """Return deterministic realized weather observations."""

    base = datetime(2026, 8, 11, 18, 0, 0)
    return (
        TimeSeriesPoint(
            series="chicago.temperature_f",
            observed_at=base,
            value=90.0,
            metadata={"market_family": "temperature"},
        ),
        TimeSeriesPoint(
            series="gulf.wind_speed_mph",
            observed_at=base,
            value=58.0,
            metadata={"market_family": "storm"},
        ),
    )
