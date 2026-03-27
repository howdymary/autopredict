"""Fixture-backed weather ingestion helpers."""

from autopredict.ingestion.weather.features import build_weather_features
from autopredict.ingestion.weather.forecasts import (
    FixtureWeatherForecastIngestor,
    load_fixture_forecast_batch,
    normalize_forecasts,
    sample_forecast_rows,
)
from autopredict.ingestion.weather.observations import (
    FixtureWeatherObservationIngestor,
    load_fixture_observation_batch,
    normalize_observations,
    sample_observation_rows,
)

__all__ = [
    "FixtureWeatherForecastIngestor",
    "FixtureWeatherObservationIngestor",
    "build_weather_features",
    "load_fixture_forecast_batch",
    "load_fixture_observation_batch",
    "normalize_forecasts",
    "normalize_observations",
    "sample_forecast_rows",
    "sample_observation_rows",
]
