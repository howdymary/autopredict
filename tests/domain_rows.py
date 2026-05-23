"""Local test rows for domain ingestion and adapter tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def finance_market_data_rows() -> tuple[dict[str, Any], ...]:
    base = datetime(2026, 3, 20, 12, 0, 0)
    return (
        {
            "series": "ust2y",
            "observed_at": base,
            "value": 4.20,
            "metadata": {"asset_class": "rates", "market_family": "rates"},
        },
        {
            "series": "ust2y",
            "observed_at": base + timedelta(days=1),
            "value": 4.28,
            "metadata": {"asset_class": "rates", "market_family": "rates"},
        },
        {
            "series": "btc_usd",
            "observed_at": base,
            "value": 82_000.0,
            "metadata": {"asset_class": "crypto", "market_family": "crypto"},
        },
        {
            "series": "btc_usd",
            "observed_at": base + timedelta(days=1),
            "value": 84_500.0,
            "metadata": {"asset_class": "crypto", "market_family": "crypto"},
        },
    )


def finance_macro_rows() -> tuple[dict[str, Any], ...]:
    observed_at = datetime(2026, 3, 21, 8, 30, 0)
    return (
        {
            "record_id": "cpi-2026-03",
            "observed_at": observed_at,
            "payload": {"expected": 0.2, "actual": 0.4, "unit": "pct_mom"},
            "metadata": {
                "release": "cpi",
                "market_family": "macro",
                "regime": "pre_release",
            },
        },
        {
            "record_id": "fomc-2026-03",
            "observed_at": observed_at + timedelta(hours=6),
            "payload": {"expected_cut_bps": 25, "actual_cut_bps": 0},
            "metadata": {
                "release": "fomc",
                "market_family": "rates",
                "regime": "post_release",
            },
        },
    )


def weather_forecast_rows() -> tuple[dict[str, Any], ...]:
    base = datetime(2026, 8, 10, 6, 0, 0)
    return (
        {
            "record_id": "chi-temp-2026-08-11",
            "observed_at": base,
            "payload": {
                "region": "chicago",
                "temperature_f": 92.0,
                "precip_probability": 0.10,
            },
            "metadata": {"market_family": "temperature", "regime": "watch"},
        },
        {
            "record_id": "gulf-storm-2026-08-11",
            "observed_at": base + timedelta(hours=3),
            "payload": {
                "region": "gulf",
                "wind_speed_mph": 55.0,
                "landfall_probability": 0.35,
            },
            "metadata": {"market_family": "storm", "regime": "warning"},
        },
    )


def weather_observation_rows() -> tuple[dict[str, Any], ...]:
    base = datetime(2026, 8, 11, 18, 0, 0)
    return (
        {
            "series": "chicago.temperature_f",
            "observed_at": base,
            "value": 90.0,
            "metadata": {"market_family": "temperature"},
        },
        {
            "series": "gulf.wind_speed_mph",
            "observed_at": base,
            "value": 58.0,
            "metadata": {"market_family": "storm"},
        },
    )


def politics_news_rows() -> tuple[dict[str, Any], ...]:
    base = datetime(2026, 10, 25, 9, 0, 0)
    return (
        {
            "record_id": "news-001",
            "observed_at": base,
            "payload": {"headline": "Candidate announces economic plan", "novelty": 0.8},
            "metadata": {"market_family": "elections", "regime": "campaign"},
        },
        {
            "record_id": "news-002",
            "observed_at": base + timedelta(hours=4),
            "payload": {"headline": "Debate schedule finalized", "novelty": 0.6},
            "metadata": {"market_family": "elections", "regime": "debate_week"},
        },
    )


def politics_poll_rows() -> tuple[dict[str, Any], ...]:
    base = datetime(2026, 10, 24, 7, 0, 0)
    return (
        {
            "record_id": "poll-001",
            "observed_at": base,
            "payload": {"candidate_a": 48.0, "candidate_b": 45.0},
            "metadata": {"market_family": "elections", "regime": "campaign"},
        },
        {
            "record_id": "poll-002",
            "observed_at": base + timedelta(days=1),
            "payload": {"candidate_a": 49.0, "candidate_b": 44.0},
            "metadata": {"market_family": "approval", "regime": "campaign"},
        },
    )


def politics_event_rows() -> tuple[dict[str, Any], ...]:
    return (
        {
            "record_id": "event-001",
            "observed_at": datetime(2026, 10, 26, 18, 0, 0),
            "payload": {"event_type": "debate", "intensity": 0.9},
            "metadata": {"market_family": "elections", "regime": "debate_week"},
        },
    )
