"""Politics domain adapter for fixture-backed evidence."""

from __future__ import annotations

from autopredict.domains.base import DomainFeatureBundle
from autopredict.ingestion.politics.events import load_fixture_event_batch
from autopredict.ingestion.politics.features import build_politics_features
from autopredict.ingestion.politics.news import load_fixture_news_batch
from autopredict.ingestion.politics.polls import load_fixture_poll_batch


class PoliticsDomainAdapter:
    """Build a normalized politics bundle from fixture-backed evidence."""

    name = "politics"

    @classmethod
    def from_fixtures(cls) -> "PoliticsDomainAdapter":
        """Return a fixture-backed politics adapter."""

        return cls()

    def build_bundle(self) -> DomainFeatureBundle:
        news_batch = load_fixture_news_batch()
        poll_batch = load_fixture_poll_batch()
        event_batch = load_fixture_event_batch()
        features = build_politics_features(news_batch, poll_batch, event_batch)
        anchor_record = event_batch.evidence[0]
        return DomainFeatureBundle(
            domain="politics",
            features=features,
            metadata={
                "domain": "politics",
                "market_family": str(anchor_record.metadata.get("market_family", "elections")),
                "regime": str(anchor_record.metadata.get("regime", "campaign")),
                "feature_version": "politics.phase1",
            },
            evidence_ids=news_batch.record_ids + poll_batch.record_ids + event_batch.record_ids,
        )
