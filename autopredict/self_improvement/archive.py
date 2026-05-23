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

DEFAULT_DEPENDENCY_NAMES = ("autopredict", "PyYAML", "requests")
ARCHIVE_SCHEMA_VERSION = 1


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
) -> dict[str, Any]:
    """Build a JSON-ready archive payload from an in-memory run object."""

    timestamp = _coerce_timestamp(created_at)
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
        "run": serialize_run(run),
    }

    dataset = _dataset_payload(dataset_path=dataset_path, dataset_hash=dataset_hash)
    if dataset:
        archive["dataset"] = dataset

    if config is not None:
        archive["config"] = _json_ready(config)
    if genome is not None:
        archive["genome"] = _json_ready(genome)

    warning_values = _collect_warnings(run, warnings)
    if warning_values is not None:
        archive["warnings"] = warning_values

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
        "metrics": {
            f"fold_{fold['fold_index']}": fold["metrics"]
            for fold in folds
        },
        "report_cards": [
            report_card
            for fold in folds
            for report_card in fold["report_cards"]
        ],
        "rejection_reasons": {
            f"fold_{fold['fold_index']}": fold["rejection_reasons"]
            for fold in folds
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
    return (
        value.replace(":", "")
        .replace(".", "")
        .replace("+", "")
        .replace("/", "-")
    )


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
