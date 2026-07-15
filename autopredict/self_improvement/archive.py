"""Archive utilities for meta-harness self-improvement runs.

The helpers in this module serialize artifacts that already exist in memory.
They intentionally avoid deriving synthetic performance summaries; callers can
pass run metadata such as dataset identity, config, and warnings when those
values are known to the harness.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import subprocess
import tempfile
from datetime import date, datetime, timezone
from enum import Enum
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from autopredict.self_improvement.promotion import (
    PROMOTION_METHOD_VERSION,
    PromotionPolicy,
    assess_paired_forecasts,
    parse_expected_row_identities,
    parse_paired_rows,
)

DEFAULT_DEPENDENCY_NAMES = ("autopredict", "PyYAML", "requests")
ARCHIVE_SCHEMA_VERSION = 2


def dataset_sha256(dataset_path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest for a dataset file."""

    path = Path(dataset_path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_dependency_versions(
    dependency_names: Iterable[str] = DEFAULT_DEPENDENCY_NAMES,
) -> dict[str, str]:
    """Return installed versions for dependencies that can be discovered."""

    versions: dict[str, str] = {}
    for name in dependency_names:
        try:
            versions[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            if name == "autopredict":
                try:
                    from autopredict import __version__
                except ImportError:
                    continue
                versions[name] = __version__
    return versions


def discover_git_sha(repo_root: str | Path | None = None) -> str | None:
    """Return the current git SHA for *repo_root* when git can resolve one."""

    cwd = Path(repo_root) if repo_root is not None else Path.cwd()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    sha = completed.stdout.strip()
    return sha or None


def discover_git_state(repo_root: str | Path | None = None) -> dict[str, Any] | None:
    """Return reproducibility metadata for the current git checkout."""

    cwd = Path(repo_root) if repo_root is not None else Path.cwd()
    git_sha = discover_git_sha(cwd)
    if git_sha is None:
        return None

    status = _run_git_text(cwd, "status", "--porcelain=v1", "--untracked-files=normal")
    tracked_diff = _run_git_bytes(cwd, "diff", "--binary", "HEAD", "--")
    untracked_files = _run_git_bytes(cwd, "ls-files", "--others", "--exclude-standard", "-z")
    untracked_paths = sorted(
        path for path in untracked_files.decode("utf-8", errors="replace").split("\0") if path
    )

    state: dict[str, Any] = {
        "sha": git_sha,
        "dirty": bool(status.strip()),
        "status_porcelain": [line for line in status.splitlines() if line],
    }
    if tracked_diff:
        state["tracked_diff_sha256"] = hashlib.sha256(tracked_diff).hexdigest()
    if untracked_paths:
        state["untracked_files"] = untracked_paths
        state["untracked_manifest_sha256"] = _hash_untracked_manifest(cwd, untracked_paths)
    return state


def build_run_archive(
    run: Any,
    *,
    dataset_path: str | Path | None = None,
    dataset_hash: str | None = None,
    config: Any | None = None,
    genome: Any | None = None,
    warnings: Sequence[Any] | None = None,
    run_id: str | None = None,
    created_at: datetime | str | None = None,
    repo_root: str | Path | None = None,
    dependency_names: Iterable[str] = DEFAULT_DEPENDENCY_NAMES,
    promotion_policy: Any | None = None,
    dataset_version: str = "legacy-resolved-snapshots-v0",
    provider_version: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-ready archive payload from an in-memory run object."""

    timestamp = _coerce_timestamp(created_at)
    serialized_run = serialize_run(run)
    dataset = _dataset_payload(dataset_path=dataset_path, dataset_hash=dataset_hash)
    if dataset:
        dataset["version"] = dataset_version
    serialized_config = _json_ready(config) if config is not None else None
    serialized_genome = _json_ready(genome) if genome is not None else None
    derived_provider_version = _derive_provider_version(serialized_run)
    if provider_version is not None and provider_version != derived_provider_version:
        raise ValueError("provider_version does not match the canonical evaluated trajectory")
    resolved_provider_version = derived_provider_version
    provenance: dict[str, Any] = {"created_at": timestamp}
    if run_id:
        provenance["run_id"] = run_id

    git_state = discover_git_state(repo_root)
    if git_state is not None:
        provenance["git_sha"] = git_state["sha"]
        provenance["git"] = git_state

    dependency_versions = collect_dependency_versions(dependency_names)
    if dependency_versions:
        provenance["dependency_versions"] = dependency_versions

    archive: dict[str, Any] = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "provenance": provenance,
        "run": serialized_run,
        "provider": {"version": resolved_provider_version},
    }

    if dataset:
        archive["dataset"] = dataset

    if serialized_config is not None:
        archive["config"] = serialized_config
    if serialized_genome is not None:
        archive["genome"] = serialized_genome

    warning_values = _collect_warnings(run, warnings)
    if warning_values is not None:
        archive["warnings"] = warning_values

    archive["promotion_attempt"] = _build_promotion_attempt(
        serialized_run,
        dataset=dataset,
        policy=promotion_policy,
        provider_version=resolved_provider_version,
        config=serialized_config,
        genome=serialized_genome,
    )
    provenance["attempt_id"] = archive["promotion_attempt"]["attempt_id"]

    return archive


def write_run_archive(
    run: Any,
    archive_dir: str | Path,
    *,
    filename: str | None = None,
    dataset_path: str | Path | None = None,
    dataset_hash: str | None = None,
    config: Any | None = None,
    genome: Any | None = None,
    warnings: Sequence[Any] | None = None,
    run_id: str | None = None,
    created_at: datetime | str | None = None,
    repo_root: str | Path | None = None,
    dependency_names: Iterable[str] = DEFAULT_DEPENDENCY_NAMES,
    promotion_policy: Any | None = None,
    dataset_version: str = "legacy-resolved-snapshots-v0",
    provider_version: str | None = None,
) -> Path:
    """Write a run archive JSON file and return its path."""

    timestamp = _coerce_timestamp(created_at)
    payload = build_run_archive(
        run,
        dataset_path=dataset_path,
        dataset_hash=dataset_hash,
        config=config,
        genome=genome,
        warnings=warnings,
        run_id=run_id,
        created_at=timestamp,
        repo_root=repo_root,
        dependency_names=dependency_names,
        promotion_policy=promotion_policy,
        dataset_version=dataset_version,
        provider_version=provider_version,
    )

    directory = Path(archive_dir)
    archive_name = filename or (
        f"{_safe_filename(run_id or 'meta-run')}-{_safe_timestamp(timestamp)}.json"
    )
    path = directory / archive_name
    _atomic_write_json(path, payload)
    return path


def load_run_archive(path: str | Path) -> dict[str, Any]:
    """Load a previously written run archive."""

    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("run archive must contain a JSON object")
    return payload


def rebuild_promotion_attempt(archive: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute archived evidence from its raw run rows for tamper detection."""

    run = archive.get("run")
    dataset = archive.get("dataset")
    attempt = archive.get("promotion_attempt")
    if not isinstance(dataset, Mapping):
        raise ValueError("archive must include dataset metadata")
    if not isinstance(attempt, Mapping):
        raise ValueError("archive must include promotion_attempt evidence")
    provider = archive.get("provider")
    if not isinstance(provider, Mapping) or not isinstance(provider.get("version"), str):
        raise ValueError("archive must include provider.version")
    if provider["version"] != _derive_provider_version(run):
        raise ValueError("archive provider.version does not match evaluated trajectory")
    return _build_promotion_attempt(
        run,
        dataset=dataset,
        policy=attempt.get("policy"),
        provider_version=provider["version"],
        config=archive.get("config"),
        genome=archive.get("genome"),
    )


def rebuild_trusted_promotion_attempt(archive: Mapping[str, Any]) -> dict[str, Any]:
    """Reassess evidence with non-negotiable frontier policy floors."""

    attempt = archive.get("promotion_attempt")
    dataset = archive.get("dataset")
    provider = archive.get("provider")
    if not isinstance(attempt, Mapping) or not isinstance(dataset, Mapping):
        raise ValueError("archive is missing promotion evidence or dataset metadata")
    if not isinstance(provider, Mapping) or not isinstance(provider.get("version"), str):
        raise ValueError("archive must include provider.version")
    if provider["version"] != _derive_provider_version(archive.get("run")):
        raise ValueError("archive provider.version does not match evaluated trajectory")
    supplied_policy = _coerce_promotion_policy(attempt.get("policy"))
    trusted_policy = PromotionPolicy(
        min_independent_events=max(30, supplied_policy.min_independent_events),
        familywise_alpha=min(0.05, supplied_policy.familywise_alpha),
        min_brier_improvement=max(0.0, supplied_policy.min_brier_improvement),
        correction_method="bonferroni",
    )
    return _build_promotion_attempt(
        archive.get("run"),
        dataset=dataset,
        policy=trusted_policy,
        provider_version=provider["version"],
        config=archive.get("config"),
        genome=archive.get("genome"),
    )


def serialize_run(run: Any) -> Any:
    """Serialize a known run object, falling back to a JSON-ready form."""

    if _looks_like_walk_forward_report(run):
        return _serialize_walk_forward_report(run)
    if _looks_like_cycle_report(run):
        return _serialize_cycle_report(run)
    if _looks_like_selection_outcome(run):
        return _serialize_selection_outcome(run)
    if _looks_like_candidate_evaluation(run):
        return _serialize_candidate_evaluation(run)
    if _looks_like_backtest_result(run):
        return _serialize_backtest_result(run)
    return _json_ready(run)


def extract_report_cards(result: Any) -> list[dict[str, Any]]:
    """Return report cards embedded in forecast and trade metadata."""

    cards: list[dict[str, Any]] = []
    for source_name in ("forecasts", "trades"):
        for index, item in enumerate(getattr(result, source_name, ()) or ()):
            metadata = getattr(item, "metadata", None)
            if not isinstance(metadata, Mapping):
                continue
            report_card = metadata.get("report_card")
            if not isinstance(report_card, Mapping) or not report_card:
                continue

            record: dict[str, Any] = {
                "source": source_name[:-1],
                "index": index,
                "report_card": _json_ready(report_card),
            }
            market_id = getattr(item, "market_id", None)
            if market_id is not None:
                record["market_id"] = str(market_id)
            cards.append(record)
    return cards


def _serialize_walk_forward_report(report: Any) -> dict[str, Any]:
    folds = [_serialize_walk_forward_fold(fold) for fold in report.folds]
    return {
        "kind": "walk_forward",
        "initial_genome": _json_ready(report.initial_genome),
        "final_genome": _json_ready(report.final_genome),
        "promotions": report.promotions,
        "folds": folds,
        "metrics": {f"fold_{fold['fold_index']}": fold["metrics"] for fold in folds},
        "report_cards": [report_card for fold in folds for report_card in fold["report_cards"]],
        "rejection_reasons": {
            f"fold_{fold['fold_index']}": fold["rejection_reasons"] for fold in folds
        },
    }


def _serialize_walk_forward_fold(fold: Any) -> dict[str, Any]:
    validation_candidate = getattr(fold, "validation_candidate", None)
    train_report = _serialize_cycle_report(fold.train_report)
    validation_baseline = _serialize_candidate_evaluation(fold.validation_baseline)
    validation_candidate_payload = (
        _serialize_candidate_evaluation(validation_candidate)
        if validation_candidate is not None
        else None
    )
    validation_selection = _serialize_selection_outcome(fold.validation_selection)
    validation_report_cards = list(validation_baseline["report_cards"])
    if validation_candidate_payload is not None:
        validation_report_cards.extend(validation_candidate_payload["report_cards"])

    return {
        "fold_index": fold.fold_index,
        "promoted": fold.promoted,
        "train_market_ids": list(fold.train_market_ids),
        "validation_market_ids": list(fold.validation_market_ids),
        "validation_event_ids": list(
            getattr(fold, "validation_event_ids", ()) or fold.validation_market_ids
        ),
        "validation_snapshot_ids": list(
            getattr(fold, "validation_snapshot_ids", ())
            or (None for _ in fold.validation_market_ids)
        ),
        "train_split_labels": list(getattr(fold, "train_split_labels", ()) or ()),
        "validation_split_labels": list(getattr(fold, "validation_split_labels", ()) or ()),
        "baseline_genome": _json_ready(fold.baseline_genome),
        "candidate_genome": _json_ready(fold.candidate_genome),
        "winner_genome": _json_ready(fold.winner.genome),
        "train": train_report,
        "validation": {
            "baseline": validation_baseline,
            "candidate": validation_candidate_payload,
            "selection": validation_selection,
        },
        "metrics": {
            "train": train_report["metrics"],
            "validation": {
                "baseline": validation_baseline["metrics"],
                "candidate": (
                    validation_candidate_payload["metrics"]
                    if validation_candidate_payload is not None
                    else None
                ),
                "winner": _json_ready(fold.winner.result.metrics),
            },
        },
        "report_cards": train_report["report_cards"] + validation_report_cards,
        "rejection_reasons": {
            "train": train_report["rejection_reasons"],
            "validation": validation_selection["rejection_reasons"],
        },
    }


def _serialize_cycle_report(report: Any) -> dict[str, Any]:
    selection = _serialize_selection_outcome(report.selection)
    population = []
    metrics: dict[str, Any] = {}
    report_cards: list[dict[str, Any]] = []

    rejection_reasons = getattr(report.selection, "rejection_reasons", {}) or {}
    for candidate in report.population:
        genome_name = getattr(candidate.genome, "name", "")
        candidate_payload = _serialize_candidate_evaluation(
            candidate,
            rejection_reasons=rejection_reasons.get(genome_name),
        )
        population.append(candidate_payload)
        metrics[genome_name] = candidate_payload["metrics"]
        report_cards.extend(candidate_payload["report_cards"])

    return {
        "kind": "improvement_cycle",
        "population": population,
        "selection": selection,
        "winner": _serialize_candidate_evaluation(report.winner),
        "metrics": metrics,
        "report_cards": report_cards,
        "rejection_reasons": selection["rejection_reasons"],
    }


def _serialize_selection_outcome(outcome: Any) -> dict[str, Any]:
    return {
        "baseline": _json_ready(outcome.baseline.genome),
        "winner": _json_ready(outcome.winner.genome),
        "accepted": [_json_ready(candidate.genome) for candidate in outcome.accepted],
        "rejected": [_json_ready(candidate.genome) for candidate in outcome.rejected],
        "rejection_reasons": {
            str(name): list(reasons)
            for name, reasons in (getattr(outcome, "rejection_reasons", {}) or {}).items()
        },
    }


def _serialize_candidate_evaluation(
    candidate: Any,
    *,
    rejection_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    result = candidate.result
    payload = {
        "genome": _json_ready(candidate.genome),
        "result": _serialize_backtest_result(result),
        "metrics": _json_ready(result.metrics),
        "scoring": _json_ready(result.scoring),
        "report_cards": extract_report_cards(result),
    }
    if rejection_reasons is not None:
        payload["rejection_reasons"] = list(rejection_reasons)
    return payload


def _serialize_backtest_result(result: Any) -> dict[str, Any]:
    payload = {
        "kind": "backtest_result",
        "metrics": _json_ready(result.metrics),
        "scoring": _json_ready(result.scoring),
        "num_decisions": len(getattr(result, "decisions", ()) or ()),
        "num_forecasts": len(getattr(result, "forecasts", ()) or ()),
        "num_trades": len(getattr(result, "trades", ()) or ()),
        "forecasts": [_json_ready(forecast) for forecast in getattr(result, "forecasts", ())],
        "trades": [_json_ready(trade) for trade in getattr(result, "trades", ())],
    }
    payload["report_cards"] = extract_report_cards(result)
    return payload


def _build_promotion_attempt(
    run: Any,
    *,
    dataset: Mapping[str, Any],
    policy: Any | None,
    provider_version: str,
    config: Any,
    genome: Any,
) -> dict[str, Any]:
    active_policy = _coerce_promotion_policy(policy)
    promotion_input = _extract_promotion_input(run)
    raw_rows = promotion_input.get("rows", [])
    rows, parse_reasons = parse_paired_rows(raw_rows)
    expected_identities, identity_reasons = parse_expected_row_identities(
        promotion_input.get("expected_row_identities")
    )
    parse_reasons = (*parse_reasons, *identity_reasons)
    attempted_artifacts, attempted_reasons = _parse_attempted_artifacts(
        promotion_input.get("attempted_artifacts")
    )
    evaluated_trajectory, trajectory_reasons = _parse_evaluated_trajectory(
        promotion_input.get("evaluated_trajectory")
    )
    parse_reasons = (*parse_reasons, *attempted_reasons, *trajectory_reasons)
    raw_hypothesis_count = promotion_input.get("hypothesis_count", 0)
    derived_hypothesis_count = sum(len(entry["artifact_ids"]) - 1 for entry in attempted_artifacts)
    if type(raw_hypothesis_count) is not int or raw_hypothesis_count <= 0:
        hypothesis_count = 1
        parse_reasons = (*parse_reasons, "hypothesis_count_must_be_positive_integer")
    elif raw_hypothesis_count != derived_hypothesis_count:
        hypothesis_count = max(derived_hypothesis_count, 1)
        parse_reasons = (
            *parse_reasons,
            "hypothesis_count_does_not_match_attempted_artifacts:"
            f"{raw_hypothesis_count}!={derived_hypothesis_count}",
        )
    else:
        hypothesis_count = raw_hypothesis_count
    parse_reasons = (
        *parse_reasons,
        *_validate_evaluated_provenance(
            rows,
            expected_identities=expected_identities,
            attempted_artifacts=attempted_artifacts,
            evaluated_trajectory=evaluated_trajectory,
            final_genome=_final_genome(run, genome),
        ),
    )

    decision = assess_paired_forecasts(
        rows,
        expected_row_identities=expected_identities,
        hypothesis_count=hypothesis_count,
        policy=active_policy,
        input_rejection_reasons=parse_reasons,
    )
    evidence_content = {
        "rows": raw_rows,
        "expected_row_identities": promotion_input.get("expected_row_identities"),
        "hypothesis_count": raw_hypothesis_count,
        "attempted_artifacts": promotion_input.get("attempted_artifacts"),
        "evaluated_trajectory": promotion_input.get("evaluated_trajectory"),
    }
    evidence_sha256 = _canonical_sha256(evidence_content)
    content_sha256 = _canonical_sha256(
        {
            "run": run,
            "dataset": dataset,
            "config": config,
            "genome": genome,
            "provider_version": provider_version,
            "method_version": PROMOTION_METHOD_VERSION,
            "policy": active_policy.to_dict(),
            "evidence_sha256": evidence_sha256,
        }
    )
    trajectory = {
        "kind": "walk_forward_trajectory",
        "artifacts": list(evaluated_trajectory),
    }
    return {
        "attempt_id": "attempt-sha256:" + content_sha256,
        "content_sha256": content_sha256,
        "evidence_sha256": evidence_sha256,
        "dataset_version": str(dataset.get("version", "unknown")),
        "dataset_sha256": dataset.get("sha256"),
        "method_version": PROMOTION_METHOD_VERSION,
        "provider_version": provider_version,
        "policy": active_policy.to_dict(),
        "corrected_threshold": {
            "familywise_alpha": active_policy.familywise_alpha,
            "hypothesis_count": hypothesis_count,
            "derived_hypothesis_count": derived_hypothesis_count,
            "corrected_alpha": decision.corrected_alpha,
            "minimum_brier_improvement": active_policy.min_brier_improvement,
        },
        "evidence_summary": decision.to_dict(),
        "trajectory": trajectory,
        "uncertainty_unit": "event_id",
        "outcome_consistency_unit": "event_id+market_id",
        "repeated_run_caveat": (
            "Bonferroni correction covers hypotheses declared by this attempt; "
            "reusing the same dataset across separate attempts remains exploratory."
        ),
        "rejection_reasons": list(decision.rejection_reasons),
        "accepted": decision.accepted,
    }


def _coerce_promotion_policy(value: Any | None) -> PromotionPolicy:
    if value is None:
        return PromotionPolicy()
    if isinstance(value, PromotionPolicy):
        return value
    if isinstance(value, Mapping):
        min_events = value.get("min_independent_events", 30)
        alpha = value.get("familywise_alpha", 0.05)
        min_improvement = value.get("min_brier_improvement", 0.0)
        correction = value.get("correction_method", "bonferroni")
        if type(min_events) is not int:
            raise ValueError("min_independent_events must be an integer")
        if isinstance(alpha, bool) or not isinstance(alpha, (int, float)):
            raise ValueError("familywise_alpha must be a number")
        if isinstance(min_improvement, bool) or not isinstance(min_improvement, (int, float)):
            raise ValueError("min_brier_improvement must be a number")
        if not isinstance(correction, str):
            raise ValueError("correction_method must be a string")
        return PromotionPolicy(
            min_independent_events=min_events,
            familywise_alpha=float(alpha),
            min_brier_improvement=float(min_improvement),
            correction_method=correction,
        )
    raise TypeError("promotion_policy must be PromotionPolicy or a mapping")


def _parse_attempted_artifacts(
    value: Any,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    if not isinstance(value, list):
        return (), ("attempted_artifacts_must_be_a_list",)
    entries: list[dict[str, Any]] = []
    reasons: list[str] = []
    seen_folds: set[int] = set()
    required = {"fold_index", "baseline_artifact_id", "artifact_ids"}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != required:
            reasons.append(f"invalid_attempted_artifacts:{index}:invalid_fields")
            continue
        fold_index = item["fold_index"]
        baseline = item["baseline_artifact_id"]
        artifact_ids = item["artifact_ids"]
        if type(fold_index) is not int or fold_index < 0:
            reasons.append(f"invalid_attempted_artifacts:{index}:invalid_fold_index")
            continue
        if fold_index in seen_folds:
            reasons.append(f"invalid_attempted_artifacts:{index}:duplicate_fold_index")
            continue
        if not isinstance(baseline, str) or not baseline.strip():
            reasons.append(f"invalid_attempted_artifacts:{index}:invalid_baseline")
            continue
        if (
            not isinstance(artifact_ids, list)
            or not artifact_ids
            or not all(
                isinstance(artifact_id, str) and artifact_id.strip() for artifact_id in artifact_ids
            )
        ):
            reasons.append(f"invalid_attempted_artifacts:{index}:invalid_artifact_ids")
            continue
        if len(set(artifact_ids)) != len(artifact_ids):
            reasons.append(f"invalid_attempted_artifacts:{index}:duplicate_artifact_ids")
            continue
        if artifact_ids[0] != baseline:
            reasons.append(f"invalid_attempted_artifacts:{index}:baseline_must_be_first")
            continue
        seen_folds.add(fold_index)
        entries.append(
            {
                "fold_index": fold_index,
                "baseline_artifact_id": baseline,
                "artifact_ids": tuple(artifact_ids),
            }
        )
    return tuple(entries), tuple(reasons)


def _parse_evaluated_trajectory(
    value: Any,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    if not isinstance(value, list):
        return (), ("evaluated_trajectory_must_be_a_list",)
    entries: list[dict[str, Any]] = []
    reasons: list[str] = []
    seen_folds: set[int] = set()
    required = {"fold_index", "provider_version", "artifact_id"}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != required:
            reasons.append(f"invalid_evaluated_trajectory:{index}:invalid_fields")
            continue
        fold_index = item["fold_index"]
        provider_version = item["provider_version"]
        artifact_id = item["artifact_id"]
        if type(fold_index) is not int or fold_index < 0:
            reasons.append(f"invalid_evaluated_trajectory:{index}:invalid_fold_index")
            continue
        if fold_index in seen_folds:
            reasons.append(f"invalid_evaluated_trajectory:{index}:duplicate_fold_index")
            continue
        if not isinstance(provider_version, str) or not provider_version.strip():
            reasons.append(f"invalid_evaluated_trajectory:{index}:invalid_provider_version")
            continue
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            reasons.append(f"invalid_evaluated_trajectory:{index}:invalid_artifact_id")
            continue
        seen_folds.add(fold_index)
        entries.append(
            {
                "fold_index": fold_index,
                "provider_version": provider_version,
                "artifact_id": artifact_id,
            }
        )
    return tuple(entries), tuple(reasons)


def _validate_evaluated_provenance(
    rows: Sequence[Any],
    *,
    expected_identities: Sequence[tuple[int, str, str, str | None]],
    attempted_artifacts: Sequence[Mapping[str, Any]],
    evaluated_trajectory: Sequence[Mapping[str, Any]],
    final_genome: Any,
) -> tuple[str, ...]:
    reasons: list[str] = []
    attempted_by_fold = {entry["fold_index"]: entry for entry in attempted_artifacts}
    evaluated_by_fold = {entry["fold_index"]: entry for entry in evaluated_trajectory}
    attempted_folds = set(attempted_by_fold)
    evaluated_folds = set(evaluated_by_fold)
    observed_folds = {row.fold_index for row in rows}
    expected_folds = {identity[0] for identity in expected_identities}
    if not (attempted_folds == evaluated_folds == observed_folds == expected_folds):
        reasons.append("promotion_fold_sets_mismatch")
    for fold_index in sorted(evaluated_folds - observed_folds):
        reasons.append(f"evaluated_fold_has_no_evidence_rows:{fold_index}")
    for fold_index, evaluated in evaluated_by_fold.items():
        attempted = attempted_by_fold.get(fold_index)
        if attempted is not None and evaluated["artifact_id"] not in attempted["artifact_ids"]:
            reasons.append(f"evaluated_artifact_not_attempted:{fold_index}")
    for row in rows:
        row_evaluation = evaluated_by_fold.get(row.fold_index)
        if row_evaluation is None:
            reasons.append(f"row_fold_missing_from_evaluated_trajectory:{row.fold_index}")
            continue
        if row.artifact_id != row_evaluation["artifact_id"]:
            reasons.append(f"row_artifact_mismatch:{row.fold_index}")
        if row.provider_version != row_evaluation["provider_version"]:
            reasons.append(f"row_provider_mismatch:{row.fold_index}")
    if observed_folds and final_genome is not None:
        last_evidence_fold = max(observed_folds)
        last = evaluated_by_fold.get(last_evidence_fold)
        if last is None or last["artifact_id"] != _artifact_id(final_genome):
            reasons.append("final_genome_does_not_match_last_evaluated_artifact")
    return tuple(dict.fromkeys(reasons))


def _final_genome(run: Any, genome: Any) -> Any:
    if isinstance(run, Mapping) and run.get("final_genome") is not None:
        return run["final_genome"]
    return genome


def _extract_promotion_input(run: Any) -> dict[str, Any]:
    if not isinstance(run, Mapping):
        return {}
    explicit = run.get("promotion_evaluation")
    if isinstance(explicit, Mapping):
        return dict(explicit)
    if run.get("kind") != "walk_forward":
        return {}

    rows: list[dict[str, Any]] = []
    expected_row_identities: list[dict[str, Any]] = []
    attempted_artifacts: list[dict[str, Any]] = []
    evaluated_trajectory: list[dict[str, Any]] = []
    hypothesis_count = 0
    folds = run.get("folds")
    if not isinstance(folds, list):
        return {}
    for fold in folds:
        if not isinstance(fold, Mapping):
            continue
        fold_index = fold.get("fold_index", 0)
        if type(fold_index) is not int or fold_index < 0:
            continue
        train = fold.get("train")
        if isinstance(train, Mapping) and isinstance(train.get("population"), list):
            artifact_ids = [
                _artifact_id(candidate.get("genome"))
                for candidate in train["population"]
                if isinstance(candidate, Mapping) and candidate.get("genome") is not None
            ]
            if artifact_ids:
                attempted_artifacts.append(
                    {
                        "fold_index": fold_index,
                        "baseline_artifact_id": artifact_ids[0],
                        "artifact_ids": artifact_ids,
                    }
                )
                hypothesis_count += len(artifact_ids) - 1
        selected = _selected_validation_payload(fold)
        fold_rows = _paired_rows_from_candidate(selected, fold_index)
        rows.extend(fold_rows)
        if isinstance(selected, Mapping) and selected.get("genome") is not None:
            selected_artifact = _artifact_id(selected["genome"])
            evaluated_trajectory.append(
                {
                    "fold_index": fold_index,
                    "provider_version": selected_artifact,
                    "artifact_id": selected_artifact,
                }
            )
        validation_markets = fold.get("validation_market_ids")
        validation_events = fold.get("validation_event_ids", validation_markets)
        validation_snapshots = fold.get("validation_snapshot_ids")
        if isinstance(validation_markets, list) and isinstance(validation_events, list):
            if validation_snapshots is None:
                validation_snapshots = [None] * len(validation_markets)
            if isinstance(validation_snapshots, list) and len(validation_markets) == len(
                validation_events
            ) == len(validation_snapshots):
                for event_id, market_id, snapshot_id in zip(
                    validation_events, validation_markets, validation_snapshots
                ):
                    identity = {
                        "fold_index": fold_index,
                        "event_id": event_id,
                        "market_id": market_id,
                    }
                    if snapshot_id is not None:
                        identity["snapshot_id"] = snapshot_id
                    expected_row_identities.append(identity)
    return {
        "rows": rows,
        "expected_row_identities": expected_row_identities,
        "attempted_artifacts": attempted_artifacts,
        "evaluated_trajectory": evaluated_trajectory,
        "hypothesis_count": hypothesis_count,
    }


def _selected_validation_payload(fold: Mapping[str, Any]) -> Mapping[str, Any] | None:
    validation = fold.get("validation")
    if not isinstance(validation, Mapping):
        return None
    candidate = validation.get("candidate")
    winner_genome = fold.get("winner_genome")
    if isinstance(candidate, Mapping) and candidate.get("genome") == winner_genome:
        return candidate
    baseline = validation.get("baseline")
    return baseline if isinstance(baseline, Mapping) else None


def _paired_rows_from_candidate(
    candidate: Mapping[str, Any] | None,
    fold_index: int,
) -> list[dict[str, Any]]:
    if not isinstance(candidate, Mapping):
        return []
    result = candidate.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("forecasts"), list):
        return []
    rows: list[dict[str, Any]] = []
    for forecast in result["forecasts"]:
        if not isinstance(forecast, Mapping):
            rows.append({"invalid_forecast": True})
            continue
        metadata = forecast.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        market_id = str(forecast.get("market_id", ""))
        genome = candidate.get("genome")
        artifact_id = _artifact_id(genome)
        provider_version = metadata.get("provider_version", artifact_id)
        snapshot_id = metadata.get("snapshot_id")
        rows.append(
            {
                "event_id": str(metadata.get("event_id", market_id)),
                "market_id": market_id,
                "fold_index": fold_index,
                **({"snapshot_id": snapshot_id} if snapshot_id is not None else {}),
                "provider_version": provider_version,
                "artifact_id": metadata.get("artifact_id", artifact_id),
                "candidate_probability": forecast.get("probability"),
                "market_probability": metadata.get("market_prob"),
                "outcome": forecast.get("outcome"),
            }
        )
    return rows


def _derive_provider_version(run: Any) -> str:
    promotion_input = _extract_promotion_input(run)
    return "trajectory-sha256:" + _canonical_sha256(promotion_input.get("evaluated_trajectory"))


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        _json_ready(value), allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _artifact_id(genome: Any) -> str:
    return "genome-sha256:" + _canonical_sha256(genome)


def _dataset_payload(
    *,
    dataset_path: str | Path | None,
    dataset_hash: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if dataset_path is not None:
        path = Path(dataset_path)
        payload["path"] = str(path)
        if dataset_hash is None and path.exists() and path.is_file():
            dataset_hash = dataset_sha256(path)
    if dataset_hash is not None:
        payload["sha256"] = dataset_hash
    return payload


def _collect_warnings(run: Any, warnings: Sequence[Any] | None) -> list[Any] | None:
    if warnings is not None:
        return [_json_ready(warning) for warning in warnings]

    for attr_name in ("warnings", "warning_messages"):
        values = getattr(run, attr_name, None)
        if values is not None:
            return [_json_ready(warning) for warning in values]
    return None


def _coerce_timestamp(value: datetime | str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
        timestamp = value
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _safe_timestamp(value: str) -> str:
    return value.replace(":", "").replace(".", "").replace("+", "").replace("/", "-")


def _safe_filename(value: str) -> str:
    safe = []
    for character in value:
        if character.isalnum() or character in {"-", "_", "."}:
            safe.append(character)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or "meta-run"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, allow_nan=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("archives cannot contain non-finite numeric values")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return [_json_ready(item) for item in sorted(value, key=repr)]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_ready(value.to_dict())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_ready(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    try:
        json.dumps(value, allow_nan=False)
    except TypeError:
        return repr(value)
    return value


def _run_git_text(cwd: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return completed.stdout


def _run_git_bytes(cwd: Path, *args: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return b""
    return completed.stdout


def _hash_untracked_manifest(repo_root: Path, paths: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for relative_path in paths:
        path = repo_root / relative_path
        digest.update(relative_path.encode("utf-8", errors="replace"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(dataset_sha256(path).encode("ascii"))
        else:
            digest.update(b"<non-file>")
        digest.update(b"\n")
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _looks_like_walk_forward_report(value: Any) -> bool:
    if not all(hasattr(value, attr) for attr in ("initial_genome", "final_genome", "folds")):
        return False
    return all(hasattr(fold, "train_report") for fold in getattr(value, "folds", ()) or ())


def _looks_like_cycle_report(value: Any) -> bool:
    return all(hasattr(value, attr) for attr in ("population", "selection", "winner"))


def _looks_like_selection_outcome(value: Any) -> bool:
    return all(
        hasattr(value, attr)
        for attr in ("baseline", "winner", "accepted", "rejected", "rejection_reasons")
    )


def _looks_like_candidate_evaluation(value: Any) -> bool:
    return all(hasattr(value, attr) for attr in ("genome", "result"))


def _looks_like_backtest_result(value: Any) -> bool:
    return all(hasattr(value, attr) for attr in ("metrics", "scoring", "forecasts", "trades"))
