"""Tests for finance ingestion fixtures and normalization."""

from __future__ import annotations

import pytest

from autopredict.ingestion.finance import (
    build_finance_features,
    normalize_macro_releases,
    normalize_market_data,
    sample_macro_rows,
    sample_market_data_rows,
)


def test_finance_ingestion_normalizes_fixture_rows() -> None:
    """Fixture rows should normalize into shared ingestion batches."""

    market_batch = normalize_market_data(sample_market_data_rows())
    macro_batch = normalize_macro_releases(sample_macro_rows())

    assert market_batch.source.domain == "finance"
    assert market_batch.count == 4
    assert len(market_batch.records) == 0
    assert len(market_batch.series) == 4
    assert market_batch.series[-1].series_name == "btc_usd"

    assert macro_batch.source.name == "finance.macro"
    assert len(macro_batch.records) == 2
    assert macro_batch.records[0].record_type == "macro_release"
    assert macro_batch.records[0].payload["expected"] == pytest.approx(0.2)


def test_finance_feature_builder_emits_stable_values() -> None:
    """Feature extraction should be deterministic for fixture-backed data."""

    features = build_finance_features(
        normalize_market_data(sample_market_data_rows()),
        normalize_macro_releases(sample_macro_rows()),
    )

    assert features["num_series_points"] == 4
    assert features["num_macro_events"] == 2
    assert features["market_families"] == ("crypto", "rates")
    assert features["latest_crypto_price"] == pytest.approx(84500.0)
    assert features["latest_rates_value"] == pytest.approx(4.28)
    assert features["mean_percent_release_surprise"] == pytest.approx(0.2)
    assert features["mean_rate_cut_surprise_bps"] == pytest.approx(-25.0)
