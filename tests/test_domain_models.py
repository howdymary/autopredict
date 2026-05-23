"""Tests for production-safe default domain models."""

from __future__ import annotations

from autopredict.domains import (
    FinanceDomainAdapter,
    PoliticsDomainAdapter,
    WeatherDomainAdapter,
    build_default_finance_model,
    build_default_politics_model,
    build_default_weather_model,
    finance_dataset,
    politics_dataset,
    weather_dataset,
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


def _finance_bundle():
    return FinanceDomainAdapter.from_batches(
        market_data_batch=normalize_market_data(finance_market_data_rows()),
        macro_batch=normalize_macro_releases(finance_macro_rows()),
    ).build_bundle()


def _weather_bundle():
    return WeatherDomainAdapter.from_batches(
        forecast_batch=normalize_forecasts(weather_forecast_rows()),
        observation_batch=normalize_observations(weather_observation_rows()),
    ).build_bundle()


def _politics_bundle():
    return PoliticsDomainAdapter.from_batches(
        news_batch=normalize_news(politics_news_rows()),
        poll_batch=normalize_polls(politics_poll_rows()),
        event_batch=normalize_events(politics_event_rows()),
    ).build_bundle()


def test_default_domain_models_use_market_implied_no_edge_forecasts() -> None:
    """Bundled defaults should not fabricate domain alpha from package data."""

    cases = (
        (_finance_bundle(), build_default_finance_model()),
        (_weather_bundle(), build_default_weather_model()),
        (_politics_bundle(), build_default_politics_model()),
    )

    for bundle, model in cases:
        first = model.predict(
            "Will this market resolve YES?",
            {**bundle.features, "market_prob": 0.40},
            bundle.metadata,
        )
        second = model.predict(
            "Will a completely different wording resolve YES?",
            {**bundle.features, "market_prob": 0.40},
            bundle.metadata,
        )

        assert first.probability == 0.40
        assert second.probability == 0.40
        assert first.metadata["forecast_source"] == "market_implied_no_edge"
        assert first.metadata["verified_training_data"] is False
        assert first.metadata["dataset_name"] is None


def test_default_domain_datasets_are_empty_until_verified_data_is_configured() -> None:
    """Package defaults should expose metadata but no bundled supervised examples."""

    for dataset in (finance_dataset(), weather_dataset(), politics_dataset()):
        assert dataset.version == "none"
        assert dataset.split_counts() == {}
        assert dataset.coverage_score == 0.0


def test_default_model_report_card_declares_missing_verified_training_data() -> None:
    """The neutral fallback should make its no-edge status explicit."""

    model = build_default_finance_model()
    summary = model.training_summary
    report_card = summary["report_card"]

    assert summary["forecast_source"] == "market_implied_no_edge"
    assert summary["verified_training_data"] is False
    assert report_card["dataset_name"] is None
    assert report_card["coverage_score"] == 0.0
