"""Tests for deterministic, provenance-rich evaluation reports."""

from __future__ import annotations

from pathlib import Path

import pytest

from autopredict.evaluation import evaluate_market_baseline, load_dataset_v1, report_json

FIXTURE = Path(__file__).parent / "fixtures/datasets/resolved-v1/manifest.json"


def test_market_baseline_report_is_deterministic_and_versioned() -> None:
    dataset = load_dataset_v1(FIXTURE)
    first = evaluate_market_baseline(dataset)
    second = evaluate_market_baseline(dataset)

    assert report_json(first) == report_json(second)
    assert first["report_version"] == "autopredict.evaluation.v2"
    assert first["dataset"]["dataset_sha256"] == dataset.dataset_sha256
    assert first["provider"]["name"] == "market-baseline"
    assert first["methodology"]["version"] == "binary-proper-scoring.v1"
    assert first["counts"] == {
        "requests": 2,
        "forecasts": 2,
        "abstentions": 0,
        "independent_events": 2,
        "markets": 2,
    }
    assert first["candidate"] == first["baseline"]
    assert first["skill"] == {"brier_skill": 0.0, "log_skill": 0.0}
    assert all("event_id" in row for row in first["rows"])


def test_partial_dataset_cannot_be_used_as_performance_evidence() -> None:
    dataset = load_dataset_v1(FIXTURE)
    partial_manifest = dataset.manifest.__class__(
        **{**dataset.manifest.__dict__, "completeness": "partial"}
    )
    partial_dataset = dataset.__class__(**{**dataset.__dict__, "manifest": partial_manifest})

    with pytest.raises(ValueError, match="complete dataset"):
        evaluate_market_baseline(partial_dataset)
