"""Tests for politics ingestion fixtures and normalization."""

from __future__ import annotations

import pytest

from autopredict.ingestion.politics import (
    build_politics_features,
    normalize_events,
    normalize_news,
    normalize_polls,
    sample_event_rows,
    sample_news_rows,
    sample_poll_rows,
)


def test_politics_ingestion_normalizes_fixture_rows() -> None:
    """Fixture rows should normalize into shared politics batches."""

    news_batch = normalize_news(sample_news_rows())
    poll_batch = normalize_polls(sample_poll_rows())
    event_batch = normalize_events(sample_event_rows())

    assert news_batch.source.domain == "politics"
    assert len(news_batch.records) == 2
    assert news_batch.records[-1].payload["novelty"] == pytest.approx(0.6)

    assert len(poll_batch.records) == 2
    assert poll_batch.records[0].record_type == "poll"
    assert poll_batch.records[0].payload["candidate_a"] == pytest.approx(48.0)

    assert len(event_batch.records) == 1
    assert event_batch.records[0].payload["event_type"] == "debate"


def test_politics_feature_builder_emits_stable_values() -> None:
    """Feature extraction should be deterministic for fixture-backed politics data."""

    features = build_politics_features(
        normalize_news(sample_news_rows()),
        normalize_polls(sample_poll_rows()),
        normalize_events(sample_event_rows()),
    )

    assert features["num_articles"] == 2
    assert features["num_polls"] == 2
    assert features["num_events"] == 1
    assert features["poll_margin"] == pytest.approx(5.0)
    assert features["mean_article_novelty"] == pytest.approx(0.7)
    assert features["max_event_intensity"] == pytest.approx(0.9)
