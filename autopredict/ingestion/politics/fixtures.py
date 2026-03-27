"""Deterministic fixture data for politics evidence ingestion."""

from __future__ import annotations

from datetime import datetime, timedelta

from autopredict.ingestion.base import EvidenceRecord, SourceConfig

NEWS_SOURCE = SourceConfig(name="politics.news", version="fixture.v1")
POLL_SOURCE = SourceConfig(name="politics.polls", version="fixture.v1")
EVENT_SOURCE = SourceConfig(name="politics.events", version="fixture.v1")


def sample_news_records() -> tuple[EvidenceRecord, ...]:
    """Return deterministic politics news records."""

    base = datetime(2026, 10, 25, 9, 0, 0)
    return (
        EvidenceRecord(
            source=NEWS_SOURCE.name,
            record_id="news-001",
            observed_at=base,
            payload={"headline": "Candidate announces economic plan", "novelty": 0.8},
            metadata={"market_family": "elections", "regime": "campaign"},
        ),
        EvidenceRecord(
            source=NEWS_SOURCE.name,
            record_id="news-002",
            observed_at=base + timedelta(hours=4),
            payload={"headline": "Debate schedule finalized", "novelty": 0.6},
            metadata={"market_family": "elections", "regime": "debate_week"},
        ),
    )


def sample_poll_records() -> tuple[EvidenceRecord, ...]:
    """Return deterministic poll records."""

    base = datetime(2026, 10, 24, 7, 0, 0)
    return (
        EvidenceRecord(
            source=POLL_SOURCE.name,
            record_id="poll-001",
            observed_at=base,
            payload={"candidate_a": 48.0, "candidate_b": 45.0},
            metadata={"market_family": "elections", "regime": "campaign"},
        ),
        EvidenceRecord(
            source=POLL_SOURCE.name,
            record_id="poll-002",
            observed_at=base + timedelta(days=1),
            payload={"candidate_a": 49.0, "candidate_b": 44.0},
            metadata={"market_family": "approval", "regime": "campaign"},
        ),
    )


def sample_event_records() -> tuple[EvidenceRecord, ...]:
    """Return deterministic politics event records."""

    observed_at = datetime(2026, 10, 26, 18, 0, 0)
    return (
        EvidenceRecord(
            source=EVENT_SOURCE.name,
            record_id="event-001",
            observed_at=observed_at,
            payload={"event_type": "debate", "intensity": 0.9},
            metadata={"market_family": "elections", "regime": "debate_week"},
        ),
    )
