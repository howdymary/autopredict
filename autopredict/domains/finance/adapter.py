"""Finance domain adapter for caller-provided evidence."""

from __future__ import annotations

from autopredict.domains.base import DomainFeatureBundle
from autopredict.ingestion.base import IngestionBatch
from autopredict.ingestion.finance.features import build_finance_features


class FinanceDomainAdapter:
    """Build a normalized finance bundle from explicit evidence batches."""

    name = "finance"

    def __init__(
        self,
        *,
        market_data_batch: IngestionBatch,
        macro_batch: IngestionBatch,
    ) -> None:
        self.market_data_batch = market_data_batch
        self.macro_batch = macro_batch

    @classmethod
    def from_batches(
        cls,
        *,
        market_data_batch: IngestionBatch,
        macro_batch: IngestionBatch,
    ) -> "FinanceDomainAdapter":
        """Return an adapter over observed finance batches."""

        return cls(
            market_data_batch=market_data_batch,
            macro_batch=macro_batch,
        )

    def build_bundle(self) -> DomainFeatureBundle:
        market_data_batch = self.market_data_batch
        macro_batch = self.macro_batch
        features = build_finance_features(market_data_batch, macro_batch)
        macro_family = macro_batch.evidence[0].metadata.get("market_family", "macro")
        macro_regime = macro_batch.evidence[0].metadata.get("regime", "pre_release")
        return DomainFeatureBundle(
            domain="finance",
            features=features,
            metadata={
                "domain": "finance",
                "market_family": str(macro_family),
                "regime": str(macro_regime),
                "feature_version": "finance.phase1",
            },
            evidence_ids=market_data_batch.record_ids + macro_batch.record_ids,
        )
