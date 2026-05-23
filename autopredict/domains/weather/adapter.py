"""Weather domain adapter for caller-provided evidence."""

from __future__ import annotations

from autopredict.domains.base import DomainFeatureBundle
from autopredict.ingestion.base import IngestionBatch
from autopredict.ingestion.weather.features import build_weather_features


class WeatherDomainAdapter:
    """Build a normalized weather bundle from explicit evidence batches."""

    name = "weather"

    def __init__(
        self,
        *,
        forecast_batch: IngestionBatch,
        observation_batch: IngestionBatch,
    ) -> None:
        self.forecast_batch = forecast_batch
        self.observation_batch = observation_batch

    @classmethod
    def from_batches(
        cls,
        *,
        forecast_batch: IngestionBatch,
        observation_batch: IngestionBatch,
    ) -> "WeatherDomainAdapter":
        """Return an adapter over observed weather batches."""

        return cls(
            forecast_batch=forecast_batch,
            observation_batch=observation_batch,
        )

    def build_bundle(self) -> DomainFeatureBundle:
        forecast_batch = self.forecast_batch
        observation_batch = self.observation_batch
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
