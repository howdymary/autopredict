"""Deterministic fixture data for finance evidence ingestion."""

from __future__ import annotations

from datetime import datetime, timedelta

from autopredict.ingestion.base import EvidenceRecord, SourceConfig, TimeSeriesPoint

MARKET_DATA_SOURCE = SourceConfig(name="finance.market_data", version="fixture.v1")
MACRO_SOURCE = SourceConfig(name="finance.macro", version="fixture.v1")


def sample_market_data_points() -> tuple[TimeSeriesPoint, ...]:
    """Return deterministic market data series points."""

    base = datetime(2026, 3, 20, 12, 0, 0)
    return (
        TimeSeriesPoint(
            series="ust2y",
            observed_at=base,
            value=4.20,
            metadata={"asset_class": "rates", "market_family": "rates"},
        ),
        TimeSeriesPoint(
            series="ust2y",
            observed_at=base + timedelta(days=1),
            value=4.28,
            metadata={"asset_class": "rates", "market_family": "rates"},
        ),
        TimeSeriesPoint(
            series="btc_usd",
            observed_at=base,
            value=82_000.0,
            metadata={"asset_class": "crypto", "market_family": "crypto"},
        ),
        TimeSeriesPoint(
            series="btc_usd",
            observed_at=base + timedelta(days=1),
            value=84_500.0,
            metadata={"asset_class": "crypto", "market_family": "crypto"},
        ),
    )


def sample_macro_records() -> tuple[EvidenceRecord, ...]:
    """Return deterministic macro release records."""

    observed_at = datetime(2026, 3, 21, 8, 30, 0)
    return (
        EvidenceRecord(
            source=MACRO_SOURCE.name,
            record_id="cpi-2026-03",
            observed_at=observed_at,
            payload={"expected": 0.2, "actual": 0.4, "unit": "pct_mom"},
            metadata={
                "release": "cpi",
                "market_family": "macro",
                "regime": "pre_release",
            },
        ),
        EvidenceRecord(
            source=MACRO_SOURCE.name,
            record_id="fomc-2026-03",
            observed_at=observed_at + timedelta(hours=6),
            payload={"expected_cut_bps": 25, "actual_cut_bps": 0},
            metadata={
                "release": "fomc",
                "market_family": "rates",
                "regime": "post_release",
            },
        ),
    )
