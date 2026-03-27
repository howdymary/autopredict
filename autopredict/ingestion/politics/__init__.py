"""Fixture-backed politics ingestion helpers."""

from autopredict.ingestion.politics.events import (
    FixturePoliticalEventIngestor,
    load_fixture_event_batch,
    normalize_events,
    sample_event_rows,
)
from autopredict.ingestion.politics.features import build_politics_features
from autopredict.ingestion.politics.news import (
    FixturePoliticalNewsIngestor,
    load_fixture_news_batch,
    normalize_news,
    sample_news_rows,
)
from autopredict.ingestion.politics.polls import (
    FixturePoliticalPollIngestor,
    load_fixture_poll_batch,
    normalize_polls,
    sample_poll_rows,
)

__all__ = [
    "FixturePoliticalEventIngestor",
    "FixturePoliticalNewsIngestor",
    "FixturePoliticalPollIngestor",
    "build_politics_features",
    "load_fixture_event_batch",
    "load_fixture_news_batch",
    "load_fixture_poll_batch",
    "normalize_events",
    "normalize_news",
    "normalize_polls",
    "sample_event_rows",
    "sample_news_rows",
    "sample_poll_rows",
]
