"""Tests for the forecast-owned ratchet path."""

from __future__ import annotations

from pathlib import Path
import json

from autopredict.evaluation import load_resolved_snapshots
from autopredict.self_improvement import (
    improvement_config_with_population,
    run_forecast_owned_ratchet,
)


def _write_resolved_dataset(path: Path) -> None:
    records = [
        {
            "market_id": "fed-cuts-before-september",
            "question": "Will the Fed cut rates before September?",
            "observed_at": "2026-01-01T00:00:00Z",
            "category": "macro",
            "market_prob": 0.48,
            "fair_prob": 0.52,
            "outcome": 1,
            "time_to_expiry_hours": 720.0,
            "order_book": {"bids": [[0.47, 200.0]], "asks": [[0.49, 220.0]]},
            "metadata": {"liquidity_tier": "medium", "spread_tier": "normal"},
        },
        {
            "market_id": "btc-above-120k-by-year-end",
            "question": "Will BTC be above 120k by year end?",
            "observed_at": "2026-01-02T00:00:00Z",
            "category": "crypto",
            "market_prob": 0.42,
            "fair_prob": 0.46,
            "outcome": 0,
            "time_to_expiry_hours": 1440.0,
            "order_book": {"bids": [[0.41, 220.0]], "asks": [[0.43, 230.0]]},
            "metadata": {"liquidity_tier": "medium", "spread_tier": "normal"},
        },
        {
            "market_id": "us-election-2028-democrat-win",
            "question": "Will a Democrat win the 2028 US presidential election?",
            "observed_at": "2026-01-03T00:00:00Z",
            "category": "politics",
            "market_prob": 0.55,
            "fair_prob": 0.57,
            "outcome": 1,
            "time_to_expiry_hours": 2400.0,
            "order_book": {"bids": [[0.54, 210.0]], "asks": [[0.56, 200.0]]},
            "metadata": {"liquidity_tier": "medium", "spread_tier": "normal"},
        },
        {
            "market_id": "weather-event-resolves",
            "question": "Will named weather event resolve YES?",
            "observed_at": "2026-01-04T00:00:00Z",
            "category": "weather",
            "market_prob": 0.36,
            "fair_prob": 0.38,
            "outcome": 0,
            "time_to_expiry_hours": 120.0,
            "order_book": {"bids": [[0.35, 190.0]], "asks": [[0.37, 190.0]]},
            "metadata": {"liquidity_tier": "small", "spread_tier": "normal"},
        },
    ]
    path.write_text(json.dumps(records), encoding="utf-8")


def test_load_resolved_snapshots_preserves_questions_without_fair_prob_leakage(tmp_path: Path) -> None:
    dataset_path = tmp_path / "resolved_markets.json"
    _write_resolved_dataset(dataset_path)
    snapshots = load_resolved_snapshots(dataset_path)

    assert snapshots
    assert all(snapshot.market.question for snapshot in snapshots)
    assert all("fair_prob" not in snapshot.snapshot_features for snapshot in snapshots)
    assert all(snapshot.metadata["domain"] in {"finance", "politics", "weather", "generic"} for snapshot in snapshots)


def test_load_resolved_snapshots_uses_market_id_when_question_is_missing(tmp_path: Path) -> None:
    dataset_path = tmp_path / "resolved_markets.json"
    records = [
        {
            "market_id": "fixture-market-without-question",
            "observed_at": "2026-01-01T00:00:00Z",
            "category": "macro",
            "market_prob": 0.48,
            "outcome": 1,
            "time_to_expiry_hours": 720.0,
            "order_book": {"bids": [[0.47, 200.0]], "asks": [[0.49, 220.0]]},
        }
    ]
    dataset_path.write_text(json.dumps(records), encoding="utf-8")

    snapshot = load_resolved_snapshots(dataset_path)[0]

    assert snapshot.market.question == "fixture-market-without-question"
    assert snapshot.metadata["question_source"] == "market_id"


def test_load_resolved_snapshots_requires_real_observed_timestamp(tmp_path: Path) -> None:
    dataset_path = tmp_path / "resolved_markets.json"
    records = [
        {
            "market_id": "missing-observed-time",
            "category": "macro",
            "market_prob": 0.48,
            "outcome": 1,
            "time_to_expiry_hours": 720.0,
            "order_book": {"bids": [[0.47, 200.0]], "asks": [[0.49, 220.0]]},
        }
    ]
    dataset_path.write_text(json.dumps(records), encoding="utf-8")

    try:
        load_resolved_snapshots(dataset_path)
    except ValueError as exc:
        assert "observed_at" in str(exc)
    else:
        raise AssertionError("missing observed_at should fail closed")


def test_forecast_owned_ratchet_reports_agent_generated_forecasts(tmp_path: Path) -> None:
    dataset_path = tmp_path / "resolved_markets.json"
    _write_resolved_dataset(dataset_path)
    summary = run_forecast_owned_ratchet(
        dataset_path,
        config=improvement_config_with_population(
            population_size=3,
            train_size=3,
            validation_size=1,
        ),
    )

    payload = summary.to_dict()
    assert payload["agent_owns_forecast_generation"] is True
    assert payload["initial_genome"]["strategy_kind"] == "routed_question_model"
    assert payload["final_genome"]["strategy_kind"] == "routed_question_model"
    assert payload["folds"]
    assert "winner_metrics" in payload["folds"][0]
