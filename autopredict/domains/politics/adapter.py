"""Politics domain adapter for caller-provided evidence."""

from __future__ import annotations

from autopredict.domains.base import DomainFeatureBundle
from autopredict.ingestion.base import IngestionBatch
from autopredict.ingestion.politics.features import build_politics_features


class PoliticsDomainAdapter:
    """Build a normalized politics bundle from explicit evidence batches."""

    name = "politics"

    def __init__(
        self,
        *,
        news_batch: IngestionBatch,
        poll_batch: IngestionBatch,
        event_batch: IngestionBatch,
    ) -> None:
        self.news_batch = news_batch
        self.poll_batch = poll_batch
        self.event_batch = event_batch

    @classmethod
    def from_batches(
        cls,
        *,
        news_batch: IngestionBatch,
        poll_batch: IngestionBatch,
        event_batch: IngestionBatch,
    ) -> "PoliticsDomainAdapter":
        """Return an adapter over observed politics batches."""

        return cls(
            news_batch=news_batch,
            poll_batch=poll_batch,
            event_batch=event_batch,
        )

    def build_bundle(self) -> DomainFeatureBundle:
        news_batch = self.news_batch
        poll_batch = self.poll_batch
        event_batch = self.event_batch
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
