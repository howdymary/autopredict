"""Tests for Phase 1 domain adapters and registries."""

from __future__ import annotations

from autopredict.domains import (
    DomainFeatureBundle,
    DomainRegistry,
    FinanceDomainAdapter,
    PoliticsDomainAdapter,
    WeatherDomainAdapter,
)


def test_domain_adapters_emit_required_labels_and_features() -> None:
    """Adapters should emit normalized bundles with required metadata labels."""

    for adapter_cls, domain in (
        (FinanceDomainAdapter, "finance"),
        (WeatherDomainAdapter, "weather"),
        (PoliticsDomainAdapter, "politics"),
    ):
        adapter = adapter_cls.from_fixtures()
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
    finance = FinanceDomainAdapter.from_fixtures()
    weather = WeatherDomainAdapter.from_fixtures()

    registry.register(finance.name, finance)
    registry.register(weather.name, weather)

    assert registry.get("finance") is finance
    assert registry.get("weather") is weather
    assert registry.names() == ("finance", "weather")
