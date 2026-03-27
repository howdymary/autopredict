"""Fixture-backed evidence ingestion primitives for domain-specialist agents."""

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch, Ingestor, SourceConfig, TimeSeriesPoint
from autopredict.ingestion.cache import FixtureCache
from autopredict.ingestion.registry import IngestionRegistry

__all__ = [
    "EvidenceRecord",
    "FixtureCache",
    "IngestionBatch",
    "IngestionRegistry",
    "Ingestor",
    "SourceConfig",
    "TimeSeriesPoint",
]
