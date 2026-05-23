"""Politics ingestion helpers."""

from autopredict.ingestion.politics.events import EVENT_SOURCE, normalize_events
from autopredict.ingestion.politics.features import build_politics_features
from autopredict.ingestion.politics.news import NEWS_SOURCE, normalize_news
from autopredict.ingestion.politics.polls import POLL_SOURCE, normalize_polls

__all__ = [
    "EVENT_SOURCE",
    "NEWS_SOURCE",
    "POLL_SOURCE",
    "build_politics_features",
    "normalize_events",
    "normalize_news",
    "normalize_polls",
]
