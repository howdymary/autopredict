"""Feature builders for fixture-backed weather evidence."""

from __future__ import annotations

from typing import Any

from autopredict.ingestion.base import IngestionBatch


def build_weather_features(
    forecast_batch: IngestionBatch,
    observation_batch: IngestionBatch,
) -> dict[str, Any]:
    """Build a small deterministic weather feature payload."""

    max_precip_probability = max(
        float(record.payload.get("precip_probability", 0.0))
        for record in forecast_batch.evidence
    )
    max_temperature = max(
        float(record.payload.get("temperature_f", float("-inf")))
        for record in forecast_batch.evidence
    )
    max_landfall_probability = max(
        float(record.payload.get("landfall_probability", 0.0))
        for record in forecast_batch.evidence
    )
    observed_temperatures = [
        point.value
        for point in observation_batch.series
        if "temperature" in point.series
    ]
    observed_winds = [
        point.value
        for point in observation_batch.series
        if "wind" in point.series
    ]
    return {
        "num_forecasts": len(forecast_batch.evidence),
        "num_observations": len(observation_batch.series),
        "max_precip_probability": max_precip_probability,
        "max_temperature_f": max_temperature,
        "max_landfall_probability": max_landfall_probability,
        "max_observed_temperature_f": max(observed_temperatures) if observed_temperatures else 0.0,
        "max_observed_wind_mph": max(observed_winds) if observed_winds else 0.0,
    }
