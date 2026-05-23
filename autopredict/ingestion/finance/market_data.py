"""Finance market data normalization."""

from __future__ import annotations

from typing import Any, Sequence

from autopredict.ingestion.base import IngestionBatch, SourceConfig, TimeSeriesPoint


MARKET_DATA_SOURCE = SourceConfig(name="finance.market_data", version="v1")


def normalize_market_data(
    rows: Sequence[dict[str, Any]],
    *,
    source_config: SourceConfig = MARKET_DATA_SOURCE,
) -> IngestionBatch:
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
        source_config=source_config,
        series=series,
        metadata={"domain": "finance"},
    )
