"""Tests for the forecast-owned ratchet path."""

from __future__ import annotations

from pathlib import Path

from autopredict.evaluation import load_resolved_snapshots
from autopredict.self_improvement import (
    improvement_config_with_population,
    run_forecast_owned_ratchet,
)


ROOT = Path(__file__).resolve().parent.parent


def test_load_resolved_snapshots_generates_questions_without_fair_prob_leakage() -> None:
    snapshots = load_resolved_snapshots(ROOT / "datasets/sample_markets.json")

    assert snapshots
    assert all(snapshot.market.question for snapshot in snapshots)
    assert all("fair_prob" not in snapshot.snapshot_features for snapshot in snapshots)
    assert all(snapshot.metadata["domain"] in {"finance", "politics", "generic"} for snapshot in snapshots)


def test_forecast_owned_ratchet_reports_agent_generated_forecasts() -> None:
    summary = run_forecast_owned_ratchet(
        ROOT / "datasets/sample_markets.json",
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
