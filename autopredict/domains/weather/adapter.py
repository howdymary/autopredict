"""Weather domain adapter for fixture-backed evidence."""

from __future__ import annotations

from autopredict.domains.base import DomainFeatureBundle
from autopredict.ingestion.weather.features import build_weather_features
from autopredict.ingestion.weather.forecasts import load_fixture_forecast_batch
from autopredict.ingestion.weather.observations import load_fixture_observation_batch


class WeatherDomainAdapter:
    """Build a normalized weather bundle from fixture-backed evidence."""

    name = "weather"

    @classmethod
    def from_fixtures(cls) -> "WeatherDomainAdapter":
        """Return a fixture-backed weather adapter."""

        return cls()

    def build_bundle(self) -> DomainFeatureBundle:
        forecast_batch = load_fixture_forecast_batch()
        observation_batch = load_fixture_observation_batch()
        features = build_weather_features(forecast_batch, observation_batch)
        dominant_record = forecast_batch.evidence[-1]
        return DomainFeatureBundle(
            domain="weather",
            features=features,
            metadata={
                "domain": "weather",
                "market_family": str(dominant_record.metadata.get("market_family", "storm")),
                "regime": str(dominant_record.metadata.get("regime", "watch")),
                "feature_version": "weather.phase1",
            },
            evidence_ids=forecast_batch.record_ids + observation_batch.record_ids,
        )
