"""Feature builders for fixture-backed politics evidence."""

from __future__ import annotations

import statistics
from typing import Any

from autopredict.ingestion.base import IngestionBatch


def build_politics_features(
    news_batch: IngestionBatch,
    poll_batch: IngestionBatch,
    event_batch: IngestionBatch,
) -> dict[str, Any]:
    """Build a small deterministic politics feature payload."""

    latest_poll = poll_batch.evidence[-1].payload
    poll_margin = float(latest_poll["candidate_a"]) - float(latest_poll["candidate_b"])
    novelty_scores = [float(record.payload.get("novelty", 0.0)) for record in news_batch.evidence]
    event_intensity = max(
        float(record.payload.get("intensity", 0.0))
        for record in event_batch.evidence
    )
    return {
        "num_articles": len(news_batch.evidence),
        "num_polls": len(poll_batch.evidence),
        "num_events": len(event_batch.evidence),
        "poll_margin": poll_margin,
        "mean_article_novelty": statistics.fmean(novelty_scores) if novelty_scores else 0.0,
        "max_event_intensity": event_intensity,
    }
