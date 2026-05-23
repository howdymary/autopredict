"""Evidence ingestion primitives for domain-specialist agents."""

from autopredict.ingestion.base import EvidenceRecord, IngestionBatch, Ingestor, SourceConfig, TimeSeriesPoint
from autopredict.ingestion.cache import EvidenceCache
from autopredict.ingestion.registry import IngestionRegistry

__all__ = [
    "EvidenceRecord",
    "EvidenceCache",
    "IngestionBatch",
    "IngestionRegistry",
    "Ingestor",
    "SourceConfig",
    "TimeSeriesPoint",
]
