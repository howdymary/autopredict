"""Tests for weather ingestion fixtures and normalization."""

from __future__ import annotations

import pytest

from autopredict.ingestion.weather import (
    build_weather_features,
    normalize_forecasts,
    normalize_observations,
    sample_forecast_rows,
    sample_observation_rows,
)


def test_weather_ingestion_normalizes_fixture_rows() -> None:
    """Fixture rows should normalize into shared weather batches."""

    forecast_batch = normalize_forecasts(sample_forecast_rows())
    observation_batch = normalize_observations(sample_observation_rows())

    assert forecast_batch.source.domain == "weather"
    assert len(forecast_batch.records) == 2
    assert forecast_batch.records[-1].payload["wind_speed_mph"] == pytest.approx(55.0)

    assert observation_batch.source.name == "weather.observations"
    assert len(observation_batch.records) == 0
    assert len(observation_batch.series) == 2
    assert observation_batch.series[0].series_name == "chicago.temperature_f"


def test_weather_feature_builder_emits_stable_values() -> None:
    """Feature extraction should be deterministic for fixture-backed weather data."""

    features = build_weather_features(
        normalize_forecasts(sample_forecast_rows()),
        normalize_observations(sample_observation_rows()),
    )

    assert features["num_forecasts"] == 2
    assert features["num_observations"] == 2
    assert features["max_precip_probability"] == pytest.approx(0.1)
    assert features["max_temperature_f"] == pytest.approx(92.0)
    assert features["max_landfall_probability"] == pytest.approx(0.35)
    assert features["max_observed_temperature_f"] == pytest.approx(90.0)
    assert features["max_observed_wind_mph"] == pytest.approx(58.0)
