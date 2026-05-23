"""Tests for Phase 1 domain adapters and registries."""

from __future__ import annotations

from autopredict.domains import (
    DomainFeatureBundle,
    DomainRegistry,
    FinanceDomainAdapter,
    PoliticsDomainAdapter,
    WeatherDomainAdapter,
)
from autopredict.ingestion.finance import normalize_macro_releases, normalize_market_data
from autopredict.ingestion.politics import normalize_events, normalize_news, normalize_polls
from autopredict.ingestion.weather import normalize_forecasts, normalize_observations
from tests.domain_rows import (
    finance_macro_rows,
    finance_market_data_rows,
    politics_event_rows,
    politics_news_rows,
    politics_poll_rows,
    weather_forecast_rows,
    weather_observation_rows,
)


def _finance_adapter() -> FinanceDomainAdapter:
    return FinanceDomainAdapter.from_batches(
        market_data_batch=normalize_market_data(finance_market_data_rows()),
        macro_batch=normalize_macro_releases(finance_macro_rows()),
    )


def _weather_adapter() -> WeatherDomainAdapter:
    return WeatherDomainAdapter.from_batches(
        forecast_batch=normalize_forecasts(weather_forecast_rows()),
        observation_batch=normalize_observations(weather_observation_rows()),
    )


def _politics_adapter() -> PoliticsDomainAdapter:
    return PoliticsDomainAdapter.from_batches(
        news_batch=normalize_news(politics_news_rows()),
        poll_batch=normalize_polls(politics_poll_rows()),
        event_batch=normalize_events(politics_event_rows()),
    )


def test_domain_adapters_emit_required_labels_and_features() -> None:
    """Adapters should emit normalized bundles with required metadata labels."""

    for adapter, domain in (
        (_finance_adapter(), "finance"),
        (_weather_adapter(), "weather"),
        (_politics_adapter(), "politics"),
    ):
        bundle = adapter.build_bundle()

        assert isinstance(bundle, DomainFeatureBundle)
        assert bundle.domain == domain
        assert bundle.metadata["domain"] == domain
        assert bundle.metadata["market_family"]
        assert bundle.metadata["regime"]
        assert bundle.metadata["feature_version"].endswith("phase1")
        features, metadata = bundle.as_snapshot_inputs()
        assert features
        assert metadata["market_family"] == bundle.metadata["market_family"]


def test_domain_registry_registers_and_returns_adapters() -> None:
    """Domain registries should behave deterministically."""

    registry = DomainRegistry()
    finance = _finance_adapter()
    weather = _weather_adapter()

    registry.register(finance.name, finance)
    registry.register(weather.name, weather)

    assert registry.get("finance") is finance
    assert registry.get("weather") is weather
    assert registry.names() == ("finance", "weather")
