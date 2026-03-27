"""Shared ingestion contracts for domain-specialist evidence pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class SourceConfig:
    """Stable identity and version information for one evidence source."""

    name: str
    version: str = "v1"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name cannot be empty")
        if not self.version:
            raise ValueError("version cannot be empty")

    @property
    def domain(self) -> str:
        """Return the top-level domain name for this source."""

        return self.name.split(".", 1)[0]


@dataclass(frozen=True)
class EvidenceRecord:
    """Canonical event-like evidence record."""

    source: str
    record_id: str
    observed_at: datetime
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("source cannot be empty")
        if not self.record_id:
            raise ValueError("record_id cannot be empty")

    @property
    def record_type(self) -> str:
        """Return a stable record type when one is available."""

        if "record_type" in self.metadata:
            return str(self.metadata["record_type"])
        if "record_type" in self.payload:
            return str(self.payload["record_type"])
        source_tail = self.source.rsplit(".", 1)[-1]
        return source_tail.rstrip("s")


@dataclass(frozen=True)
class TimeSeriesPoint:
    """Canonical time-series observation."""

    series: str
    observed_at: datetime
    value: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.series:
            raise ValueError("series cannot be empty")

    @property
    def series_name(self) -> str:
        """Return the logical series name."""

        return self.series


@dataclass(frozen=True)
class IngestionBatch:
    """One normalized fixture-backed batch from an ingestor."""

    source_config: SourceConfig
    evidence: tuple[EvidenceRecord, ...] = ()
    series: tuple[TimeSeriesPoint, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence and not self.series:
            raise ValueError("batch must contain evidence or series")

    @property
    def source(self) -> SourceConfig:
        """Return the batch source config."""

        return self.source_config

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        """Return event-like evidence records."""

        return self.evidence

    @property
    def count(self) -> int:
        """Return the total number of normalized items in the batch."""

        return len(self.evidence) + len(self.series)

    @property
    def record_ids(self) -> tuple[str, ...]:
        """Return stable IDs for all records in the batch."""

        evidence_ids = [record.record_id for record in self.evidence]
        series_ids = [
            f"{point.series}:{point.observed_at.isoformat()}"
            for point in self.series
        ]
        return tuple(evidence_ids + series_ids)


class Ingestor(Protocol):
    """Protocol for deterministic fixture-backed ingestors."""

    name: str

    def load_fixture(self) -> IngestionBatch:
        """Return a normalized local batch."""
