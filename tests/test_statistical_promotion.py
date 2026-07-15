"""Adversarial tests for statistically defensible frontier promotion."""

from __future__ import annotations

import math
import json
import hashlib
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from autopredict.self_improvement.promotion import (
    PairedForecastRow,
    PromotionPolicy,
    assess_paired_forecasts,
    parse_paired_rows,
)
from autopredict.self_improvement.archive import build_run_archive
from autopredict.self_improvement.frontier import FrontierStore, promote_archive


def _row(
    index: int,
    *,
    event_id: str | None = None,
    candidate: float = 0.90,
    market: float = 0.55,
    outcome: int = 1,
) -> PairedForecastRow:
    return PairedForecastRow(
        event_id=event_id or f"event-{index}",
        market_id=f"market-{index}",
        fold_index=index // 4,
        snapshot_id=None,
        provider_version=f"provider-{index // 4}",
        artifact_id=f"artifact-{index // 4}",
        candidate_probability=candidate,
        market_probability=market,
        outcome=outcome,
    )


def _promotion_evaluation(
    rows: list[dict[str, object]],
    *,
    final_genome: dict[str, object],
    hypothesis_count: int = 4,
) -> dict[str, object]:
    final_artifact = (
        "genome-sha256:"
        + hashlib.sha256(
            json.dumps(final_genome, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
    )
    last_fold = max(int(row["fold_index"]) for row in rows)
    for row in rows:
        if row["fold_index"] == last_fold:
            row["artifact_id"] = final_artifact
    folds = sorted({int(row["fold_index"]) for row in rows})
    evaluated = []
    attempted = []
    for position, fold_index in enumerate(folds):
        fold_row = next(row for row in rows if row["fold_index"] == fold_index)
        artifact_id = str(fold_row["artifact_id"])
        evaluated.append(
            {
                "fold_index": fold_index,
                "provider_version": fold_row["provider_version"],
                "artifact_id": artifact_id,
            }
        )
        artifact_ids = [artifact_id]
        if position == 0:
            artifact_ids.extend(f"attempted-{index}" for index in range(hypothesis_count))
        attempted.append(
            {
                "fold_index": fold_index,
                "baseline_artifact_id": artifact_id,
                "artifact_ids": artifact_ids,
            }
        )
    return {
        "rows": rows,
        "expected_row_identities": [
            {
                "fold_index": row["fold_index"],
                "event_id": row["event_id"],
                "market_id": row["market_id"],
                **({"snapshot_id": row["snapshot_id"]} if "snapshot_id" in row else {}),
            }
            for row in rows
        ],
        "attempted_artifacts": attempted,
        "evaluated_trajectory": evaluated,
        "hypothesis_count": hypothesis_count,
    }


def test_promotion_aggregates_all_rows_and_accepts_strong_paired_evidence() -> None:
    rows = tuple(_row(index) for index in range(12))

    decision = assess_paired_forecasts(
        rows,
        expected_row_identities=[row.identity for row in rows],
        hypothesis_count=4,
        policy=PromotionPolicy(min_independent_events=10),
    )

    assert decision.accepted is True
    assert decision.row_count == 12
    assert decision.independent_event_count == 12
    assert decision.corrected_alpha == 0.0125
    assert decision.candidate_brier_score == pytest.approx(0.01)
    assert decision.market_brier_score == pytest.approx(0.2025)
    assert decision.corrected_lower_bound is not None
    assert decision.corrected_lower_bound > 0.0


def test_duplicate_snapshots_do_not_inflate_independent_event_count() -> None:
    rows = tuple(_row(index, event_id="same-event") for index in range(50))

    decision = assess_paired_forecasts(
        rows,
        expected_row_identities=[row.identity for row in rows],
        hypothesis_count=1,
        policy=PromotionPolicy(min_independent_events=10),
    )

    assert decision.accepted is False
    assert decision.row_count == 50
    assert decision.independent_event_count == 1
    assert "insufficient_independent_events:1<10" in decision.rejection_reasons


def test_empty_incomplete_and_mismatched_evidence_fails_closed() -> None:
    empty = assess_paired_forecasts(
        (),
        expected_row_identities=[(0, "expected", "market", None)],
        hypothesis_count=1,
        policy=PromotionPolicy(min_independent_events=2),
    )
    mismatch = assess_paired_forecasts(
        (_row(1, event_id="unexpected"), _row(2, event_id="other")),
        expected_row_identities=[
            (0, "expected", "missing-market", None),
            (0, "other", "market-2", None),
        ],
        hypothesis_count=1,
        policy=PromotionPolicy(min_independent_events=2),
    )

    assert empty.accepted is False
    assert "empty_out_of_fold_evidence" in empty.rejection_reasons
    assert any(reason.startswith("missing_expected_rows:") for reason in empty.rejection_reasons)
    assert mismatch.accepted is False
    assert any(reason.startswith("missing_expected_rows:") for reason in mismatch.rejection_reasons)
    assert any(reason.startswith("unexpected_rows:") for reason in mismatch.rejection_reasons)


def test_nonfinite_rows_are_rejected_with_precise_reason() -> None:
    raw = [
        {
            "event_id": "event-1",
            "market_id": "market-1",
            "fold_index": 0,
            "provider_version": "provider",
            "artifact_id": "artifact",
            "candidate_probability": math.nan,
            "market_probability": 0.5,
            "outcome": 1,
        }
    ]

    rows, reasons = parse_paired_rows(raw)

    assert rows == ()
    assert reasons == ("invalid_promotion_row:0:candidate_probability must be finite",)


def test_conflicting_outcomes_within_event_cluster_fail_closed() -> None:
    rows = (
        replace(_row(1, event_id="event-shared", outcome=1), snapshot_id="snapshot-1"),
        replace(
            _row(2, event_id="event-shared", outcome=0),
            market_id="market-1",
            snapshot_id="snapshot-2",
        ),
        _row(3, event_id="event-other", outcome=1),
    )

    decision = assess_paired_forecasts(
        rows,
        expected_row_identities=[row.identity for row in rows],
        hypothesis_count=1,
        policy=PromotionPolicy(min_independent_events=2),
    )

    assert decision.accepted is False
    assert "conflicting_outcomes:event-shared|market-1" in decision.rejection_reasons


def test_multiple_testing_correction_is_explicit_and_stricter() -> None:
    rows = tuple(
        _row(index, candidate=0.57 + (0.01 if index % 2 else -0.01), market=0.55)
        for index in range(40)
    )
    policy = PromotionPolicy(min_independent_events=30)

    one_hypothesis = assess_paired_forecasts(
        rows,
        expected_row_identities=[row.identity for row in rows],
        hypothesis_count=1,
        policy=policy,
    )
    many_hypotheses = assess_paired_forecasts(
        rows,
        expected_row_identities=[row.identity for row in rows],
        hypothesis_count=20,
        policy=policy,
    )

    assert one_hypothesis.corrected_alpha == 0.05
    assert many_hypotheses.corrected_alpha == 0.0025
    assert many_hypotheses.corrected_lower_bound <= one_hypothesis.corrected_lower_bound


def test_student_t_bound_rejects_requested_finite_sample_adversary() -> None:
    rows = tuple(
        (
            _row(index, candidate=1.0, market=0.5)
            if index < 28
            else _row(index, candidate=0.0, market=1.0)
        )
        for index in range(30)
    )

    decision = assess_paired_forecasts(
        rows,
        expected_row_identities=[row.identity for row in rows],
        hypothesis_count=20,
        policy=PromotionPolicy(),
    )

    assert decision.mean_brier_improvement == pytest.approx(1.0 / 6.0)
    assert decision.corrected_lower_bound is not None
    assert decision.corrected_lower_bound < 0.0
    assert decision.accepted is False
    assert "corrected_lower_bound_not_positive" in decision.rejection_reasons


def test_archive_records_versions_evidence_and_repeated_attempts(tmp_path: Path) -> None:
    rows = [_row(index).to_dict() for index in range(36)]
    final_genome = {"name": "candidate", "strategy_kind": "market_recalibrated"}
    archive = build_run_archive(
        {
            "final_genome": final_genome,
            "promotion_evaluation": _promotion_evaluation(rows, final_genome=final_genome),
        },
        dataset_hash="dataset-hash",
        dataset_version="autopredict.dataset.v1",
        config={"split_mode": "chronological"},
        run_id="attempt-001",
        promotion_policy=PromotionPolicy(min_independent_events=2),
        repo_root=tmp_path,
        dependency_names=(),
    )

    attempt = archive["promotion_attempt"]
    assert attempt["attempt_id"].startswith("attempt-sha256:")
    assert archive["provenance"]["run_id"] == "attempt-001"
    assert attempt["dataset_version"] == "autopredict.dataset.v1"
    assert attempt["method_version"] == "paired-event-clustered-brier-student-t-v2"
    assert attempt["provider_version"].startswith("trajectory-sha256:")
    assert attempt["corrected_threshold"]["corrected_alpha"] == 0.0125
    assert attempt["accepted"] is True
    assert attempt["rejection_reasons"] == []

    frontier_path = tmp_path / "frontier.json"
    first = promote_archive(frontier_path, archive)
    repeated = promote_archive(frontier_path, archive)

    assert first.accepted is True
    assert first.entry["metadata"]["attempt_id"] == attempt["attempt_id"]
    assert first.entry["run_id"] == "attempt-001"
    assert first.entry["metrics"]["independent_event_count"] == 36
    assert first.entry["genome"]["kind"] == "walk_forward_trajectory"
    assert len(first.entry["genome"]["artifacts"]) == 9
    assert first.entry["genome"] != archive["run"]["final_genome"]
    assert "reusing the same dataset" in first.entry["metadata"]["repeated_run_caveat"]
    assert repeated.accepted is False
    assert repeated.entry["frontier_rejection_reasons"] == ["duplicate_attempt_id"]
    assert repeated.previous["metadata"]["attempt_id"] == attempt["attempt_id"]


def test_legacy_archive_fails_with_explicit_migration_message(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="legacy archive cannot be promoted"):
        promote_archive(
            tmp_path / "frontier.json",
            {"schema_version": 1},
        )


def test_tampered_archive_evidence_cannot_force_promotion(tmp_path: Path) -> None:
    rows = [_row(index).to_dict() for index in range(12)]
    final_genome = {"name": "candidate", "strategy_kind": "market_recalibrated"}
    archive = build_run_archive(
        {
            "final_genome": final_genome,
            "promotion_evaluation": _promotion_evaluation(
                rows, final_genome=final_genome, hypothesis_count=1
            ),
        },
        dataset_hash="dataset-hash",
        config={"split_mode": "chronological"},
        promotion_policy=PromotionPolicy(min_independent_events=10),
        repo_root=tmp_path,
        dependency_names=(),
    )
    tampered = deepcopy(archive)
    tampered["promotion_attempt"]["evidence_summary"]["mean_brier_improvement"] = math.inf

    with pytest.raises(ValueError, match="does not match.*raw out-of-fold evidence"):
        promote_archive(tmp_path / "frontier.json", tampered)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("fold_index", True, "fold_index must be a non-negative integer"),
        ("fold_index", 1.5, "fold_index must be a non-negative integer"),
        ("outcome", True, "outcome must be 0 or 1"),
        ("outcome", 1.0, "outcome must be 0 or 1"),
        ("candidate_probability", "0.9", "candidate_probability must be a number"),
        ("event_id", 7, "event_id must be a non-empty string"),
    ),
)
def test_untrusted_rows_reject_bool_coercion_and_fractional_integers(
    field: str, value: object, message: str
) -> None:
    raw = _row(0).to_dict()
    raw[field] = value

    rows, reasons = parse_paired_rows([raw])

    assert rows == ()
    assert reasons == (f"invalid_promotion_row:0:{message}",)


def test_exact_row_identity_multiset_rejects_duplicates_and_swapped_mappings() -> None:
    original = (_row(0), _row(1))
    duplicate = assess_paired_forecasts(
        (original[0], original[0], original[1]),
        expected_row_identities=[row.identity for row in original],
        hypothesis_count=1,
        policy=PromotionPolicy(min_independent_events=2),
    )
    swapped = assess_paired_forecasts(
        original,
        expected_row_identities=[
            (original[0].fold_index, original[0].event_id, original[1].market_id, None),
            (original[1].fold_index, original[1].event_id, original[0].market_id, None),
        ],
        hypothesis_count=1,
        policy=PromotionPolicy(min_independent_events=2),
    )

    assert any(
        reason.startswith("duplicate_observed_row_identities:")
        for reason in duplicate.rejection_reasons
    )
    assert any(reason.startswith("unexpected_rows:") for reason in duplicate.rejection_reasons)
    assert any(reason.startswith("missing_expected_rows:") for reason in swapped.rejection_reasons)
    assert any(reason.startswith("unexpected_rows:") for reason in swapped.rejection_reasons)


def test_multi_market_event_may_have_distinct_market_outcomes() -> None:
    rows = (
        replace(_row(0, event_id="shared", outcome=1), market_id="yes-market"),
        replace(_row(1, event_id="shared", outcome=0), market_id="other-market"),
        _row(2, event_id="independent", outcome=1),
    )

    decision = assess_paired_forecasts(
        rows,
        expected_row_identities=[row.identity for row in rows],
        hypothesis_count=1,
        policy=PromotionPolicy(min_independent_events=2),
    )

    assert not any(
        reason.startswith("conflicting_outcomes:") for reason in decision.rejection_reasons
    )
    assert decision.independent_event_count == 2


def test_frontier_enforces_trusted_policy_floor_despite_lenient_archive(tmp_path: Path) -> None:
    rows = [_row(index).to_dict() for index in range(12)]
    final_genome = {"name": "candidate", "strategy_kind": "recalibrated"}
    archive = build_run_archive(
        {
            "final_genome": final_genome,
            "promotion_evaluation": _promotion_evaluation(
                rows, final_genome=final_genome, hypothesis_count=1
            ),
        },
        dataset_hash="dataset-hash",
        config={"split_mode": "chronological"},
        promotion_policy=PromotionPolicy(
            min_independent_events=2,
            familywise_alpha=0.40,
        ),
        repo_root=tmp_path,
        dependency_names=(),
    )

    result = promote_archive(tmp_path / "frontier.json", archive)

    assert result.accepted is False
    metadata = result.entry["metadata"]
    assert "insufficient_independent_events:12<30" in metadata["rejection_reasons"]
    assert metadata["corrected_threshold"]["familywise_alpha"] == 0.05
    assert metadata["corrected_threshold"]["corrected_alpha"] == 0.05


def test_attempt_and_provider_tampering_fail_independently(tmp_path: Path) -> None:
    rows = [_row(index).to_dict() for index in range(36)]
    final_genome = {"name": "candidate", "strategy_kind": "recalibrated"}
    archive = build_run_archive(
        {
            "final_genome": final_genome,
            "promotion_evaluation": _promotion_evaluation(rows, final_genome=final_genome),
        },
        dataset_hash="dataset-hash",
        config={"split_mode": "chronological"},
        repo_root=tmp_path,
        dependency_names=(),
    )
    provider_tampered = deepcopy(archive)
    provider_tampered["promotion_attempt"]["provider_version"] = "provider-v2"
    attempt_tampered = deepcopy(archive)
    attempt_tampered["promotion_attempt"]["attempt_id"] = "attempt-sha256:fake"

    with pytest.raises(ValueError, match="does not match.*raw out-of-fold evidence"):
        promote_archive(tmp_path / "provider.json", provider_tampered)
    with pytest.raises(ValueError, match="does not match.*raw out-of-fold evidence"):
        promote_archive(tmp_path / "attempt.json", attempt_tampered)


def test_duplicate_attempt_is_global_and_checked_before_score_comparison(tmp_path: Path) -> None:
    rows = [_row(index).to_dict() for index in range(36)]
    final_genome = {"name": "candidate", "strategy_kind": "recalibrated"}
    archive = build_run_archive(
        {
            "final_genome": final_genome,
            "promotion_evaluation": _promotion_evaluation(rows, final_genome=final_genome),
        },
        dataset_hash="dataset-hash",
        config={"split_mode": "chronological"},
        repo_root=tmp_path,
        dependency_names=(),
    )
    attempt_id = archive["promotion_attempt"]["attempt_id"]
    frontier_path = tmp_path / "frontier.json"
    frontier_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "entries": {
                    "other|key|trajectory": {
                        "score": -999.0,
                        "metric_name": "mean_brier_improvement",
                        "higher_is_better": True,
                        "metadata": {"attempt_id": attempt_id},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = promote_archive(frontier_path, archive)

    assert result.accepted is False
    assert result.entry["frontier_rejection_reasons"] == ["duplicate_attempt_id"]


def test_frontier_schema_one_is_explicitly_rejected(tmp_path: Path) -> None:
    path = tmp_path / "frontier.json"
    path.write_text('{"schema_version": 1, "entries": {}}', encoding="utf-8")

    with pytest.raises(ValueError, match="legacy frontier schema"):
        FrontierStore(path).load()


def test_hypothesis_count_understatement_is_rejected_from_attempt_manifest(
    tmp_path: Path,
) -> None:
    rows = [_row(index).to_dict() for index in range(36)]
    final_genome = {"name": "candidate", "strategy_kind": "recalibrated"}
    evaluation = _promotion_evaluation(
        rows,
        final_genome=final_genome,
        hypothesis_count=20,
    )
    evaluation["hypothesis_count"] = 1

    archive = build_run_archive(
        {"final_genome": final_genome, "promotion_evaluation": evaluation},
        dataset_hash="dataset-hash",
        config={"split_mode": "chronological"},
        repo_root=tmp_path,
        dependency_names=(),
    )

    assert archive["promotion_attempt"]["corrected_threshold"]["derived_hypothesis_count"] == 20
    assert (
        "hypothesis_count_does_not_match_attempted_artifacts:1!=20"
        in archive["promotion_attempt"]["rejection_reasons"]
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("row_artifact", "row_artifact_mismatch:0"),
        ("row_provider", "row_provider_mismatch:0"),
        ("final_genome", "final_genome_does_not_match_last_evaluated_artifact"),
    ),
)
def test_evaluated_provenance_mismatches_fail_closed(
    tmp_path: Path, mutation: str, reason: str
) -> None:
    rows = [_row(index).to_dict() for index in range(36)]
    final_genome = {"name": "candidate", "strategy_kind": "recalibrated"}
    evaluation = _promotion_evaluation(rows, final_genome=final_genome)
    if mutation == "row_artifact":
        rows[0]["artifact_id"] = "conflicting-artifact"
    elif mutation == "row_provider":
        rows[0]["provider_version"] = "conflicting-provider"
    else:
        final_genome = {"name": "different", "strategy_kind": "recalibrated"}

    archive = build_run_archive(
        {"final_genome": final_genome, "promotion_evaluation": evaluation},
        dataset_hash="dataset-hash",
        config={"split_mode": "chronological"},
        repo_root=tmp_path,
        dependency_names=(),
    )

    assert reason in archive["promotion_attempt"]["rejection_reasons"]


def test_explicit_top_level_provider_override_must_match_trajectory(tmp_path: Path) -> None:
    rows = [_row(index).to_dict() for index in range(36)]
    final_genome = {"name": "candidate", "strategy_kind": "recalibrated"}

    with pytest.raises(ValueError, match="canonical evaluated trajectory"):
        build_run_archive(
            {
                "final_genome": final_genome,
                "promotion_evaluation": _promotion_evaluation(rows, final_genome=final_genome),
            },
            dataset_hash="dataset-hash",
            config={"split_mode": "chronological"},
            provider_version="operator-supplied-version",
            repo_root=tmp_path,
            dependency_names=(),
        )


def test_zero_row_fake_final_fold_cannot_supply_promoted_genome(tmp_path: Path) -> None:
    rows = [_row(index).to_dict() for index in range(36)]
    evidence_genome = {"name": "evidence-winner", "strategy_kind": "recalibrated"}
    fake_final_genome = {"name": "unevaluated-final", "strategy_kind": "recalibrated"}
    evaluation = _promotion_evaluation(rows, final_genome=evidence_genome)
    fake_artifact = (
        "genome-sha256:"
        + hashlib.sha256(
            json.dumps(fake_final_genome, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
    )
    evaluation["attempted_artifacts"].append(
        {
            "fold_index": 99,
            "baseline_artifact_id": fake_artifact,
            "artifact_ids": [fake_artifact],
        }
    )
    evaluation["evaluated_trajectory"].append(
        {
            "fold_index": 99,
            "provider_version": "fake-provider",
            "artifact_id": fake_artifact,
        }
    )

    archive = build_run_archive(
        {"final_genome": fake_final_genome, "promotion_evaluation": evaluation},
        dataset_hash="dataset-hash",
        config={"split_mode": "chronological"},
        repo_root=tmp_path,
        dependency_names=(),
    )
    reasons = archive["promotion_attempt"]["rejection_reasons"]

    assert archive["promotion_attempt"]["accepted"] is False
    assert "promotion_fold_sets_mismatch" in reasons
    assert "evaluated_fold_has_no_evidence_rows:99" in reasons
    assert "final_genome_does_not_match_last_evaluated_artifact" in reasons
    assert promote_archive(tmp_path / "frontier.json", archive).accepted is False
