"""Frontier storage for promoted meta-harness runs."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

FRONTIER_SCHEMA_VERSION = 1


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
        entries = payload.setdefault("entries", {})
        if not isinstance(entries, dict):
            raise ValueError("frontier entries must be a JSON object")
        payload.setdefault("schema_version", FRONTIER_SCHEMA_VERSION)
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

        key = frontier_key(dataset_hash, split_mode, strategy_kind)
        payload = self.load()
        entries = payload["entries"]
        previous = entries.get(key)
        if previous is not None and not isinstance(previous, Mapping):
            raise ValueError(f"frontier entry for {key!r} must be a JSON object")

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
        if metrics is not None:
            entry["metrics"] = _json_ready(dict(metrics))
        if run_id:
            entry["run_id"] = run_id
        if metadata is not None:
            entry["metadata"] = _json_ready(dict(metadata))

        if previous is not None:
            _validate_comparable(previous, metric_name, higher_is_better)
            previous_score = float(previous["score"])
            is_better = (
                score_value > previous_score
                if higher_is_better
                else score_value < previous_score
            )
            if not is_better:
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
    score: float,
    metric_name: str = "score",
    higher_is_better: bool = True,
    archive_path: str | Path | None = None,
    run_id: str | None = None,
    promoted_at: datetime | str | None = None,
) -> FrontierPromotion:
    """Promote an archive payload with an explicit score."""

    dataset = archive.get("dataset")
    if not isinstance(dataset, Mapping) or not dataset.get("sha256"):
        raise ValueError("archive must include dataset.sha256 to promote")

    split_mode = _archive_split_mode(archive)
    strategy_kind = _archive_strategy_kind(archive)
    metrics = _archive_winner_metrics(archive)
    genome = _archive_final_genome(archive)
    provenance = archive.get("provenance", {})

    return FrontierStore(frontier_path).promote(
        dataset_hash=str(dataset["sha256"]),
        split_mode=split_mode,
        strategy_kind=strategy_kind,
        score=score,
        metric_name=metric_name,
        higher_is_better=higher_is_better,
        archive_path=archive_path,
        genome=genome,
        metrics=metrics,
        run_id=run_id or (
            str(provenance["run_id"])
            if isinstance(provenance, Mapping) and provenance.get("run_id")
            else None
        ),
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


def _archive_winner_metrics(archive: Mapping[str, Any]) -> Mapping[str, Any] | None:
    run = archive.get("run")
    if not isinstance(run, Mapping):
        return None
    folds = run.get("folds")
    if isinstance(folds, list) and folds:
        last_fold = folds[-1]
        if isinstance(last_fold, Mapping):
            winner_metrics = last_fold.get("winner_metrics")
            if isinstance(winner_metrics, Mapping):
                return winner_metrics
            metrics = last_fold.get("metrics")
            if isinstance(metrics, Mapping):
                validation = metrics.get("validation")
                if isinstance(validation, Mapping) and isinstance(
                    validation.get("winner"),
                    Mapping,
                ):
                    return validation["winner"]
    metrics = run.get("metrics")
    return metrics if isinstance(metrics, Mapping) else None


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
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
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
    if value is None or isinstance(value, (str, int, float, bool)):
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
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value
