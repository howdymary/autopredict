"""Tests for meta-harness run archives and frontier promotion."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from autopredict.evaluation import (
    BacktestResult,
    BinaryForecast,
    CalibrationBucket,
    CalibrationSummary,
    ScoringReport,
)
from autopredict.self_improvement.archive import (
    build_run_archive,
    dataset_sha256,
    load_run_archive,
    write_run_archive,
)
from autopredict.self_improvement.frontier import (
    FrontierStore,
    frontier_key,
    promote_archive,
)
from autopredict.self_improvement.loop import (
    ImprovementCycleReport,
    WalkForwardConfig,
    WalkForwardFoldReport,
    WalkForwardReport,
    WalkForwardSplit,
)
from autopredict.self_improvement.mutation import StrategyGenome
from autopredict.self_improvement.ratchet import ForecastRatchetSummary
from autopredict.self_improvement.selection import CandidateEvaluation, SelectionOutcome


def _result(
    *,
    log_score: float,
    brier_score: float,
    total_pnl: float,
    report_card: dict[str, Any] | None = None,
) -> BacktestResult:
    calibration = CalibrationSummary(
        buckets=(
            CalibrationBucket(
                lower=0.0,
                upper=1.0,
                count=1,
                avg_probability=0.64,
                realized_rate=1.0,
            ),
        ),
        mean_absolute_gap=0.36,
        max_absolute_gap=0.36,
        base_rate=1.0,
    )
    scoring = ScoringReport(
        count=1,
        brier_score=brier_score,
        log_score=log_score,
        log_loss=-log_score,
        spherical_score=0.82,
        calibration=calibration,
    )
    metadata = {"domain": "finance"}
    if report_card is not None:
        metadata["report_card"] = report_card
    return BacktestResult(
        decisions=(),
        forecasts=(
            BinaryForecast(
                market_id="market-1",
                probability=0.64,
                outcome=1,
                metadata=metadata,
            ),
        ),
        trades=(),
        scoring=scoring,
        metrics={
            "num_filled_trades": 1,
            "total_pnl": total_pnl,
            "avg_slippage_bps": 2.0,
            "brier_score": brier_score,
            "log_score": log_score,
        },
    )


def _walk_forward_report() -> WalkForwardReport:
    baseline = StrategyGenome(name="baseline", strategy_kind="legacy_mispriced")
    candidate = StrategyGenome(
        name="baseline_conservative",
        strategy_kind="legacy_mispriced",
        kelly_fraction=0.20,
        metadata={"parent": "baseline"},
    )
    baseline_eval = CandidateEvaluation(
        genome=baseline,
        result=_result(
            log_score=-0.62,
            brier_score=0.20,
            total_pnl=1.0,
            report_card={
                "dataset_name": "sample",
                "coverage_score": 0.41,
                "held_out_calibration_stability": 0.08,
            },
        ),
    )
    candidate_eval = CandidateEvaluation(
        genome=candidate,
        result=_result(
            log_score=-0.42,
            brier_score=0.14,
            total_pnl=4.0,
            report_card={
                "dataset_name": "sample",
                "coverage_score": 0.77,
                "held_out_calibration_stability": 0.04,
            },
        ),
    )
    rejected = StrategyGenome(name="baseline_aggressive", strategy_kind="legacy_mispriced")
    rejected_eval = CandidateEvaluation(
        genome=rejected,
        result=_result(log_score=-0.30, brier_score=0.25, total_pnl=6.0),
    )
    train_selection = SelectionOutcome(
        baseline=baseline_eval,
        winner=candidate_eval,
        accepted=(baseline_eval, candidate_eval),
        rejected=(rejected_eval,),
        rejection_reasons={"baseline_aggressive": ("brier_regression",)},
    )
    train_report = ImprovementCycleReport(
        population=(baseline_eval, candidate_eval, rejected_eval),
        selection=train_selection,
    )
    validation_selection = SelectionOutcome(
        baseline=baseline_eval,
        winner=candidate_eval,
        accepted=(baseline_eval, candidate_eval),
        rejected=(),
        rejection_reasons={},
    )
    fold = WalkForwardFoldReport(
        fold_index=0,
        baseline_genome=baseline,
        train_market_ids=("train-1", "train-2"),
        validation_market_ids=("heldout-1",),
        train_report=train_report,
        validation_baseline=baseline_eval,
        validation_candidate=candidate_eval,
        validation_selection=validation_selection,
        promoted=True,
        train_split_labels=("calm",),
        validation_split_labels=("volatile",),
    )
    return WalkForwardReport(
        initial_genome=baseline,
        final_genome=candidate,
        folds=(fold,),
    )


def test_write_run_archive_persists_real_walk_forward_artifacts(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text('{"markets": ["market-1"]}\n', encoding="utf-8")

    archive_path = write_run_archive(
        _walk_forward_report(),
        tmp_path / "archives",
        dataset_path=dataset_path,
        config=WalkForwardConfig(split_mode=WalkForwardSplit.REGIME),
        warnings=("small_holdout",),
        run_id="run-001",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        repo_root=tmp_path,
        dependency_names=("autopredict",),
    )
    payload = load_run_archive(archive_path)

    assert payload["schema_version"] == 2
    assert payload["provenance"]["run_id"] == "run-001"
    assert payload["provenance"]["attempt_id"].startswith("attempt-sha256:")
    assert "autopredict" in payload["provenance"]["dependency_versions"]
    assert "git_sha" not in payload["provenance"]
    assert payload["dataset"] == {
        "path": str(dataset_path),
        "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "version": "legacy-resolved-snapshots-v0",
    }
    assert payload["config"]["split_mode"] == "regime"
    assert payload["warnings"] == ["small_holdout"]

    run = payload["run"]
    assert run["kind"] == "walk_forward"
    assert run["initial_genome"]["name"] == "baseline"
    assert run["final_genome"]["name"] == "baseline_conservative"
    assert run["promotions"] == 1

    fold = run["folds"][0]
    assert fold["train_market_ids"] == ["train-1", "train-2"]
    assert fold["validation_market_ids"] == ["heldout-1"]
    assert fold["train_split_labels"] == ["calm"]
    assert fold["validation_split_labels"] == ["volatile"]
    assert fold["metrics"]["validation"]["winner"]["total_pnl"] == 4.0
    assert fold["rejection_reasons"]["train"] == {"baseline_aggressive": ["brier_regression"]}
    report_cards = fold["report_cards"]
    assert any(card["report_card"]["coverage_score"] == 0.77 for card in report_cards)
    assert (
        fold["validation"]["candidate"]["result"]["forecasts"][0]["metadata"]["report_card"][
            "dataset_name"
        ]
        == "sample"
    )


def test_build_run_archive_uses_only_provided_dataset_identity(tmp_path: Path) -> None:
    payload = build_run_archive(
        _walk_forward_report(),
        dataset_hash="provided-hash",
        repo_root=tmp_path,
        dependency_names=(),
    )

    assert payload["dataset"] == {
        "sha256": "provided-hash",
        "version": "legacy-resolved-snapshots-v0",
    }
    assert "warnings" not in payload
    assert payload["provenance"]["attempt_id"].startswith("attempt-")
    assert payload["provenance"]["created_at"]


def test_build_run_archive_records_dirty_git_state(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "audit@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Audit"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True
    )
    tracked.write_text("dirty\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("new\n", encoding="utf-8")

    payload = build_run_archive(
        _walk_forward_report(),
        repo_root=tmp_path,
        dependency_names=(),
    )

    assert payload["provenance"]["git"]["dirty"] is True
    assert payload["provenance"]["git"]["tracked_diff_sha256"]
    assert payload["provenance"]["git"]["untracked_files"] == ["untracked.txt"]


def test_archive_rejects_non_finite_metrics(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        build_run_archive(
            {"metrics": {"log_score": math.nan}},
            repo_root=tmp_path,
            dependency_names=(),
        )


def test_archive_and_frontier_accept_lightweight_ratchet_summary(tmp_path: Path) -> None:
    dataset = tmp_path / "resolved.json"
    dataset.write_text("[]", encoding="utf-8")
    summary = ForecastRatchetSummary(
        dataset_path=str(dataset),
        initial_genome={"name": "baseline", "strategy_kind": "routed_question_model"},
        final_genome={"name": "winner", "strategy_kind": "routed_question_model"},
        promotions=1,
        folds=(
            {
                "fold_index": 0,
                "winner_metrics": {
                    "log_score": -0.31,
                    "brier_score": 0.18,
                    "total_pnl": 1.25,
                },
            },
        ),
    )

    archive_path = write_run_archive(
        summary,
        tmp_path / "archives",
        dataset_path=dataset,
        config=WalkForwardConfig(split_mode=WalkForwardSplit.CHRONOLOGICAL),
        genome=summary.final_genome,
        repo_root=tmp_path,
        dependency_names=(),
    )
    archive = load_run_archive(archive_path)
    promotion = promote_archive(
        tmp_path / "frontier.json",
        archive,
        score=-0.31,
        metric_name="log_score",
        archive_path=archive_path,
    )

    assert archive["run"]["final_genome"]["name"] == "winner"
    assert promotion.accepted is False
    assert "empty_out_of_fold_evidence" in promotion.entry["metadata"]["rejection_reasons"]


def test_dataset_sha256_hashes_file_bytes(tmp_path: Path) -> None:
    dataset = tmp_path / "sample.json"
    dataset.write_bytes(b"abc")

    assert dataset_sha256(dataset) == hashlib.sha256(b"abc").hexdigest()


def test_frontier_store_promotes_only_improved_entries(tmp_path: Path) -> None:
    path = tmp_path / "frontier.json"
    store = FrontierStore(path)
    genome = StrategyGenome(name="winner", strategy_kind="legacy_mispriced")

    first = store._promote_verified(
        dataset_hash="hash-1",
        split_mode=WalkForwardSplit.CHRONOLOGICAL,
        strategy_kind="legacy_mispriced",
        score=-0.50,
        metric_name="log_score",
        archive_path=tmp_path / "archive-1.json",
        genome=genome,
        metrics={"log_score": -0.50},
        run_id="run-1",
        promoted_at="2026-01-02T00:00:00Z",
    )
    rejected = store._promote_verified(
        dataset_hash="hash-1",
        split_mode=WalkForwardSplit.CHRONOLOGICAL,
        strategy_kind="legacy_mispriced",
        score=-0.70,
        metric_name="log_score",
        archive_path=tmp_path / "archive-2.json",
    )
    improved = store._promote_verified(
        dataset_hash="hash-1",
        split_mode=WalkForwardSplit.CHRONOLOGICAL,
        strategy_kind="legacy_mispriced",
        score=-0.30,
        metric_name="log_score",
        archive_path=tmp_path / "archive-3.json",
    )

    key = frontier_key("hash-1", "chronological", "legacy_mispriced")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert first.accepted is True
    assert rejected.accepted is False
    assert rejected.previous["score"] == -0.50
    assert improved.accepted is True
    assert payload["entries"][key]["score"] == -0.30
    assert store.get(
        dataset_hash="hash-1",
        split_mode="chronological",
        strategy_kind="legacy_mispriced",
    )["archive_path"] == str(tmp_path / "archive-3.json")
    assert not list(tmp_path.glob(".frontier.json.*.tmp"))


def test_direct_scalar_frontier_promotion_is_disabled(tmp_path: Path) -> None:
    store = FrontierStore(tmp_path / "frontier.json")

    with pytest.raises(ValueError, match="direct scalar frontier promotion is disabled"):
        store.promote(score=999.0)

    assert not store.path.exists()


def test_frontier_store_can_minimize_metrics(tmp_path: Path) -> None:
    store = FrontierStore(tmp_path / "frontier.json")

    accepted = store._promote_verified(
        dataset_hash="hash-1",
        split_mode="regime",
        strategy_kind="legacy_mispriced",
        score=0.20,
        metric_name="brier_score",
        higher_is_better=False,
    )
    improved = store._promote_verified(
        dataset_hash="hash-1",
        split_mode="regime",
        strategy_kind="legacy_mispriced",
        score=0.12,
        metric_name="brier_score",
        higher_is_better=False,
    )
    rejected = store._promote_verified(
        dataset_hash="hash-1",
        split_mode="regime",
        strategy_kind="legacy_mispriced",
        score=0.18,
        metric_name="brier_score",
        higher_is_better=False,
    )

    assert accepted.accepted is True
    assert improved.accepted is True
    assert rejected.accepted is False
    assert rejected.previous["score"] == 0.12


def test_promote_archive_uses_dataset_split_and_final_genome(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.json"
    dataset.write_text("[]", encoding="utf-8")
    archive = build_run_archive(
        _walk_forward_report(),
        dataset_path=dataset,
        config=WalkForwardConfig(split_mode=WalkForwardSplit.REGIME),
        run_id="run-archive",
        repo_root=tmp_path,
        dependency_names=(),
    )

    promotion = promote_archive(
        tmp_path / "frontier.json",
        archive,
        score=-0.42,
        metric_name="log_score",
        archive_path=tmp_path / "archive.json",
    )

    assert promotion.accepted is False
    assert promotion.entry["dataset_hash"] == archive["dataset"]["sha256"]
    assert promotion.entry["split_mode"] == "regime"
    assert promotion.entry["strategy_kind"] == "legacy_mispriced"
    assert (
        "insufficient_independent_events:0<30" in promotion.entry["metadata"]["rejection_reasons"]
    )


def test_legacy_score_argument_cannot_override_rejected_evidence(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.json"
    dataset.write_text("[]", encoding="utf-8")
    archive = build_run_archive(
        _walk_forward_report(),
        dataset_path=dataset,
        config=WalkForwardConfig(split_mode=WalkForwardSplit.REGIME),
        repo_root=tmp_path,
        dependency_names=(),
    )

    promotion = promote_archive(
        tmp_path / "frontier.json",
        archive,
        score=999.0,
        metric_name="log_score",
    )

    assert promotion.accepted is False
    assert not (tmp_path / "frontier.json").exists()


def test_frontier_store_rejects_score_mismatched_with_metrics(tmp_path: Path) -> None:
    store = FrontierStore(tmp_path / "frontier.json")

    with pytest.raises(ValueError, match="does not match metrics"):
        store._promote_verified(
            dataset_hash="hash-1",
            split_mode="chronological",
            strategy_kind="legacy_mispriced",
            score=999.0,
            metric_name="log_score",
            metrics={"log_score": -0.5},
        )


def test_frontier_rejects_incomparable_metric_direction(tmp_path: Path) -> None:
    store = FrontierStore(tmp_path / "frontier.json")
    store._promote_verified(
        dataset_hash="hash-1",
        split_mode="chronological",
        strategy_kind="legacy_mispriced",
        score=-0.5,
        metric_name="log_score",
    )

    with pytest.raises(ValueError, match="different metric_name"):
        store._promote_verified(
            dataset_hash="hash-1",
            split_mode="chronological",
            strategy_kind="legacy_mispriced",
            score=0.2,
            metric_name="brier_score",
            higher_is_better=False,
        )
