"""Finance domain adapter for fixture-backed evidence."""

from __future__ import annotations

from autopredict.domains.base import DomainFeatureBundle
from autopredict.ingestion.finance.features import build_finance_features
from autopredict.ingestion.finance.macro import load_fixture_macro_batch
from autopredict.ingestion.finance.market_data import load_fixture_market_data_batch


class FinanceDomainAdapter:
    """Build a normalized finance bundle from fixture-backed evidence."""

    name = "finance"

    @classmethod
    def from_fixtures(cls) -> "FinanceDomainAdapter":
        """Return a fixture-backed finance adapter."""

        return cls()

    def build_bundle(self) -> DomainFeatureBundle:
        market_data_batch = load_fixture_market_data_batch()
        macro_batch = load_fixture_macro_batch()
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
