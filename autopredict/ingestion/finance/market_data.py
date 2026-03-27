"""Fixture-backed finance market data ingestion."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import IngestionBatch, Ingestor, TimeSeriesPoint
from autopredict.ingestion.finance.fixtures import (
    MARKET_DATA_SOURCE,
    sample_market_data_points,
)


class FixtureFinanceMarketDataIngestor:
    """Deterministic market-data ingestor for finance fixtures."""

    name = "finance.market_data.fixture"

    def load_fixture(self) -> IngestionBatch:
        return load_fixture_market_data_batch()


def sample_market_data_rows() -> tuple[dict[str, Any], ...]:
    """Return fixture market data as row dictionaries."""

    rows: list[dict[str, Any]] = []
    for point in sample_market_data_points():
        rows.append(
            {
                "series": point.series,
                "observed_at": point.observed_at,
                "value": point.value,
                "metadata": dict(point.metadata),
            }
        )
    return tuple(rows)


def normalize_market_data(rows: Sequence[dict[str, Any]]) -> IngestionBatch:
    """Normalize market-data rows into the shared ingestion batch shape."""

    series = tuple(
        TimeSeriesPoint(
            series=str(row["series"]),
            observed_at=row["observed_at"],
            value=float(row["value"]),
            metadata=dict(row.get("metadata", {})),
        )
        for row in rows
    )
    return IngestionBatch(
        source_config=MARKET_DATA_SOURCE,
        series=series,
        metadata={"domain": "finance"},
    )


def load_fixture_market_data_batch() -> IngestionBatch:
    """Return normalized fixture market data batch."""

    return normalize_market_data(sample_market_data_rows())


FixtureFinanceMarketDataIngestorType = Ingestor
