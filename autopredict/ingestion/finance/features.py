"""Feature builders for fixture-backed finance evidence."""

from __future__ import annotations

import statistics
from typing import Any

from autopredict.ingestion.base import IngestionBatch


def build_finance_features(
    market_data_batch: IngestionBatch,
    macro_batch: IngestionBatch,
) -> dict[str, Any]:
    """Build a small deterministic finance feature payload."""

    market_families = [str(point.metadata.get("market_family", "unknown")) for point in market_data_batch.series]
    crypto_values = [
        point.value
        for point in market_data_batch.series
        if point.metadata.get("market_family") == "crypto"
    ]
    rate_values = [
        point.value
        for point in market_data_batch.series
        if point.metadata.get("market_family") == "rates"
    ]
    percent_surprises = []
    rate_cut_surprises_bps = []
    for record in macro_batch.evidence:
        payload = record.payload
        if "expected" in payload and "actual" in payload:
            percent_surprises.append(float(payload["actual"]) - float(payload["expected"]))
        elif "expected_cut_bps" in payload and "actual_cut_bps" in payload:
            rate_cut_surprises_bps.append(
                float(payload["actual_cut_bps"]) - float(payload["expected_cut_bps"])
            )

    return {
        "num_series_points": len(market_data_batch.series),
        "num_macro_events": len(macro_batch.evidence),
        "market_families": tuple(sorted(set(market_families))),
        "latest_crypto_price": crypto_values[-1] if crypto_values else 0.0,
        "latest_rates_value": rate_values[-1] if rate_values else 0.0,
        "mean_percent_release_surprise": (
            statistics.fmean(percent_surprises) if percent_surprises else 0.0
        ),
        "mean_rate_cut_surprise_bps": (
            statistics.fmean(rate_cut_surprises_bps) if rate_cut_surprises_bps else 0.0
        ),
    }
