"""Frontier storage for promoted meta-harness runs."""

from __future__ import annotations

import json
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Mapping

from autopredict.self_improvement.archive import (
    rebuild_promotion_attempt,
    rebuild_trusted_promotion_attempt,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - fcntl is available on production POSIX targets.
    fcntl = None  # type: ignore[assignment]

FRONTIER_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class FrontierPromotion:
    """Outcome of attempting to promote a run onto the frontier."""

    accepted: bool
    key: str
    entry: dict[str, Any]
    previous: dict[str, Any] | None = None


def frontier_key(dataset_hash: str, split_mode: str | Enum, strategy_kind: str) -> str:
    """Return the stable frontier key for a dataset/split/strategy tuple."""

    dataset_hash_value = str(dataset_hash).strip()
    split_mode_value = _string_value(split_mode).strip()
    strategy_kind_value = str(strategy_kind).strip()
    if not dataset_hash_value:
        raise ValueError("dataset_hash must be non-empty")
    if not split_mode_value:
        raise ValueError("split_mode must be non-empty")
    if not strategy_kind_value:
        raise ValueError("strategy_kind must be non-empty")
    return "|".join((dataset_hash_value, split_mode_value, strategy_kind_value))


class FrontierStore:
    """JSON-backed store of best run entries keyed by frontier identity."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        """Load the frontier JSON payload, or return an empty frontier."""

        if not self.path.exists():
            return {"schema_version": FRONTIER_SCHEMA_VERSION, "entries": {}}
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("frontier file must contain a JSON object")
        if payload.get("schema_version") != FRONTIER_SCHEMA_VERSION:
            raise ValueError(
                "legacy frontier schema is not promotable; migrate or rebuild as schema 2"
            )
        entries = payload.setdefault("entries", {})
        if not isinstance(entries, dict):
            raise ValueError("frontier entries must be a JSON object")
        return payload

    def entries(self) -> dict[str, dict[str, Any]]:
        """Return the current frontier entries."""

        payload = self.load()
        return {
            str(key): dict(value)
            for key, value in payload["entries"].items()
            if isinstance(value, Mapping)
        }

    def get(
        self,
        *,
        dataset_hash: str,
        split_mode: str | Enum,
        strategy_kind: str,
    ) -> dict[str, Any] | None:
        """Return the entry for a frontier key, if one exists."""

        key = frontier_key(dataset_hash, split_mode, strategy_kind)
        entry = self.load()["entries"].get(key)
        return dict(entry) if isinstance(entry, Mapping) else None

    def promote(
        self,
        **_: Any,
    ) -> FrontierPromotion:
        """Reject unsupported scalar-only promotion attempts.

        Callers must use :func:`promote_archive`, which recomputes and verifies
        paired out-of-fold evidence before this store is mutated.
        """

        raise ValueError(
            "direct scalar frontier promotion is disabled; use promote_archive "
            "with a schema-2 evidence archive"
        )

    def _promote_verified(
        self,
        *,
        dataset_hash: str,
        split_mode: str | Enum,
        strategy_kind: str,
        score: float,
        metric_name: str = "score",
        higher_is_better: bool = True,
        archive_path: str | Path | None = None,
        genome: Any | None = None,
        metrics: Mapping[str, Any] | None = None,
        run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        promoted_at: datetime | str | None = None,
    ) -> FrontierPromotion:
        """Promote a run if its score beats the current entry for its key."""

        score_value = float(score)
        if not math.isfinite(score_value):
            raise ValueError("score must be a finite number")
        if not metric_name:
            raise ValueError("metric_name must be non-empty")
        metrics_payload = _json_ready(dict(metrics)) if metrics is not None else None
        if isinstance(metrics_payload, Mapping) and metric_name in metrics_payload:
            metric_score = _coerce_metric_score(metrics_payload, metric_name)
            if not math.isclose(score_value, metric_score, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(
                    f"score {score_value!r} does not match metrics[{metric_name!r}] "
                    f"{metric_score!r}"
                )

        key = frontier_key(dataset_hash, split_mode, strategy_kind)
        entry = {
            "dataset_hash": str(dataset_hash),
            "split_mode": _string_value(split_mode),
            "strategy_kind": str(strategy_kind),
            "score": score_value,
            "metric_name": metric_name,
            "higher_is_better": bool(higher_is_better),
            "promoted_at": _coerce_timestamp(promoted_at),
        }
        if archive_path is not None:
            entry["archive_path"] = str(archive_path)
        if genome is not None:
            entry["genome"] = _json_ready(genome)
        if metrics_payload is not None:
            entry["metrics"] = metrics_payload
        if run_id:
            entry["run_id"] = run_id
        if metadata is not None:
            entry["metadata"] = _json_ready(dict(metadata))

        with _locked_frontier(self.path):
            payload = self.load()
            entries = payload["entries"]
            attempt_id = (
                str(metadata.get("attempt_id", "")).strip() if isinstance(metadata, Mapping) else ""
            )
            if attempt_id:
                for existing in entries.values():
                    if not isinstance(existing, Mapping):
                        continue
                    existing_metadata = existing.get("metadata")
                    if (
                        isinstance(existing_metadata, Mapping)
                        and existing_metadata.get("attempt_id") == attempt_id
                    ):
                        entry["frontier_rejection_reasons"] = ["duplicate_attempt_id"]
                        return FrontierPromotion(
                            accepted=False,
                            key=key,
                            entry=entry,
                            previous=dict(existing),
                        )
            previous = entries.get(key)
            if previous is not None and not isinstance(previous, Mapping):
                raise ValueError(f"frontier entry for {key!r} must be a JSON object")

            if previous is not None:
                _validate_comparable(previous, metric_name, higher_is_better)
                previous_score = float(previous["score"])
                is_better = (
                    score_value > previous_score
                    if higher_is_better
                    else score_value < previous_score
                )
                if not is_better:
                    entry["frontier_rejection_reasons"] = ["not_better_than_current_frontier"]
                    return FrontierPromotion(
                        accepted=False,
                        key=key,
                        entry=entry,
                        previous=dict(previous),
                    )

            entries[key] = entry
            _atomic_write_json(self.path, payload)

        return FrontierPromotion(
            accepted=True,
            key=key,
            entry=entry,
            previous=dict(previous) if previous is not None else None,
        )


def promote_archive(
    frontier_path: str | Path,
    archive: Mapping[str, Any],
    *,
    score: float | None = None,
    metric_name: str = "score",
    higher_is_better: bool = True,
    archive_path: str | Path | None = None,
    run_id: str | None = None,
    promoted_at: datetime | str | None = None,
) -> FrontierPromotion:
    """Promote an archive only when its corrected paired evidence accepts it.

    ``score`` and ``metric_name`` remain accepted for CLI compatibility, but
    neither can override the archived statistical decision. New frontier
    entries always compare the archived mean paired Brier improvement.
    """

    schema_version = archive.get("schema_version")
    if schema_version != 2:
        raise ValueError(
            "legacy archive cannot be promoted: rebuild it with archive schema 2 "
            "to include paired out-of-fold promotion evidence"
        )

    dataset = archive.get("dataset")
    if not isinstance(dataset, Mapping) or not dataset.get("sha256"):
        raise ValueError("archive must include dataset.sha256 to promote")
    if not dataset.get("version"):
        raise ValueError("archive must include dataset.version to promote")

    split_mode = _archive_split_mode(archive)
    strategy_kind = _archive_strategy_kind(archive)
    attempt = archive.get("promotion_attempt")
    if not isinstance(attempt, Mapping):
        raise ValueError("archive must include promotion_attempt evidence")
    rebuilt_attempt = rebuild_promotion_attempt(archive)
    if dict(attempt) != rebuilt_attempt:
        raise ValueError("promotion_attempt does not match the archive's raw out-of-fold evidence")
    provenance = archive.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get("attempt_id") != attempt.get(
        "attempt_id"
    ):
        raise ValueError("provenance.attempt_id must match the canonical promotion attempt")
    trusted_attempt = rebuild_trusted_promotion_attempt(archive)
    evidence = trusted_attempt.get("evidence_summary")
    if not isinstance(evidence, Mapping):
        raise ValueError("promotion_attempt must include evidence_summary")
    attempt_id = str(attempt.get("attempt_id", "")).strip()
    if not attempt_id:
        raise ValueError("promotion_attempt must include attempt_id")
    for version_field in ("method_version", "provider_version", "dataset_version"):
        if not str(attempt.get(version_field, "")).strip():
            raise ValueError(f"promotion_attempt must include {version_field}")
    if score is not None:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError("legacy score argument must be a number when supplied")
        if not math.isfinite(score):
            raise ValueError("legacy score argument must be finite when supplied")
    genome = trusted_attempt.get("trajectory")
    if not isinstance(genome, Mapping):
        raise ValueError("promotion evidence must identify the evaluated trajectory")
    rejection_reasons = trusted_attempt.get("rejection_reasons", [])
    if not isinstance(rejection_reasons, list):
        raise ValueError("promotion_attempt.rejection_reasons must be a list")
    evidence_accepted = attempt.get("accepted") is True and trusted_attempt.get("accepted") is True
    raw_archive_score = evidence.get("mean_brier_improvement")
    raw_lower_bound = evidence.get("corrected_lower_bound")
    archive_score = (
        float(raw_archive_score)
        if isinstance(raw_archive_score, (int, float)) and math.isfinite(float(raw_archive_score))
        else 0.0
    )
    corrected_lower_bound = (
        float(raw_lower_bound)
        if isinstance(raw_lower_bound, (int, float)) and math.isfinite(float(raw_lower_bound))
        else None
    )

    key = frontier_key(str(dataset["sha256"]), split_mode, strategy_kind)
    entry_metadata = {
        "attempt_id": attempt_id,
        "dataset_version": attempt["dataset_version"],
        "method_version": attempt["method_version"],
        "provider_version": attempt["provider_version"],
        "content_sha256": attempt.get("content_sha256"),
        "evidence_sha256": attempt.get("evidence_sha256"),
        "archive_policy": attempt.get("policy"),
        "corrected_threshold": trusted_attempt.get("corrected_threshold"),
        "evidence_summary": evidence,
        "rejection_reasons": rejection_reasons,
        "trajectory": genome,
        "uncertainty_unit": trusted_attempt.get("uncertainty_unit"),
        "outcome_consistency_unit": trusted_attempt.get("outcome_consistency_unit"),
        "repeated_run_caveat": trusted_attempt.get("repeated_run_caveat"),
        "legacy_requested_metric": metric_name,
    }
    if (
        not evidence_accepted
        or rejection_reasons
        or corrected_lower_bound is None
        or corrected_lower_bound <= 0.0
    ):
        previous = FrontierStore(frontier_path).get(
            dataset_hash=str(dataset["sha256"]),
            split_mode=split_mode,
            strategy_kind=strategy_kind,
        )
        return FrontierPromotion(
            accepted=False,
            key=key,
            entry={
                "dataset_hash": str(dataset["sha256"]),
                "split_mode": split_mode,
                "strategy_kind": strategy_kind,
                "score": archive_score,
                "metric_name": "mean_brier_improvement",
                "higher_is_better": True,
                "metadata": entry_metadata,
            },
            previous=previous,
        )

    archive_score = _coerce_metric_score(evidence, "mean_brier_improvement")
    corrected_lower_bound = _coerce_metric_score(evidence, "corrected_lower_bound")

    return FrontierStore(frontier_path)._promote_verified(
        dataset_hash=str(dataset["sha256"]),
        split_mode=split_mode,
        strategy_kind=strategy_kind,
        score=archive_score,
        metric_name="mean_brier_improvement",
        higher_is_better=True,
        archive_path=archive_path,
        genome=genome,
        metrics={
            "mean_brier_improvement": archive_score,
            "candidate_brier_score": evidence.get("candidate_brier_score"),
            "market_brier_score": evidence.get("market_brier_score"),
            "corrected_lower_bound": corrected_lower_bound,
            "independent_event_count": evidence.get("independent_event_count"),
        },
        run_id=run_id
        or (
            str(provenance["run_id"])
            if isinstance(provenance, Mapping) and provenance.get("run_id")
            else None
        ),
        metadata=entry_metadata,
        promoted_at=promoted_at,
    )


def _archive_split_mode(archive: Mapping[str, Any]) -> str:
    config = archive.get("config")
    if isinstance(config, Mapping):
        walk_forward = config.get("walk_forward")
        if isinstance(walk_forward, Mapping) and walk_forward.get("split_mode"):
            return str(walk_forward["split_mode"])
        if config.get("split_mode"):
            return str(config["split_mode"])
    if archive.get("split_mode"):
        return str(archive["split_mode"])
    raise ValueError("archive must include a split mode to promote")


def _archive_strategy_kind(archive: Mapping[str, Any]) -> str:
    genome = _archive_final_genome(archive)
    if isinstance(genome, Mapping) and genome.get("strategy_kind"):
        return str(genome["strategy_kind"])
    raise ValueError("archive must include final genome strategy_kind to promote")


def _archive_final_genome(archive: Mapping[str, Any]) -> Any:
    run = archive.get("run")
    if isinstance(run, Mapping) and run.get("final_genome") is not None:
        return run["final_genome"]
    if archive.get("genome") is not None:
        return archive["genome"]
    raise ValueError("archive must include a genome to promote")


def _validate_comparable(
    previous: Mapping[str, Any],
    metric_name: str,
    higher_is_better: bool,
) -> None:
    if "score" not in previous:
        raise ValueError("existing frontier entry is missing score")
    if previous.get("metric_name") != metric_name:
        raise ValueError("existing frontier entry uses a different metric_name")
    if bool(previous.get("higher_is_better", True)) != bool(higher_is_better):
        raise ValueError("existing frontier entry uses a different score direction")


def _coerce_metric_score(metrics: Mapping[str, Any], metric_name: str) -> float:
    if metric_name not in metrics:
        raise ValueError(f"metrics are missing required metric {metric_name!r}")
    score = float(metrics[metric_name])
    if not math.isfinite(score):
        raise ValueError(f"metric {metric_name!r} must be finite")
    return score


@contextmanager
def _locked_frontier(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


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


def _coerce_timestamp(value: datetime | str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
        timestamp = value
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _string_value(value: str | Enum) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("frontier entries cannot contain non-finite numeric values")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_ready(value.to_dict())
    try:
        json.dumps(value, allow_nan=False)
    except TypeError:
        return repr(value)
    return value


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
