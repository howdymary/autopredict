"""Deterministic v1 evaluation reports over canonical datasets."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from autopredict import __version__
from autopredict.evaluation.contracts import ResolvedDatasetV1
from autopredict.evaluation.scoring import BinaryForecast, ProperScoringRules

EVALUATION_REPORT_VERSION = "autopredict.evaluation.v1"
METHODOLOGY_VERSION = "binary-proper-scoring.v1"
MARKET_BASELINE_PROVIDER = "market-baseline"
MARKET_BASELINE_PROVIDER_VERSION = "1"


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def evaluate_market_baseline(dataset: ResolvedDatasetV1) -> dict[str, Any]:
    """Evaluate the explicit market-implied baseline with full provenance."""

    if dataset.manifest.completeness != "complete":
        raise ValueError("evaluation requires a complete dataset manifest")
    if not dataset.rows:
        raise ValueError("evaluation requires at least one resolved observation")

    rows: list[dict[str, Any]] = []
    candidate_forecasts: list[BinaryForecast] = []
    baseline_forecasts: list[BinaryForecast] = []
    for item in dataset.rows:
        observation = item.observation
        outcome = item.resolution.outcome
        probability = observation.market_probability
        candidate_forecasts.append(
            BinaryForecast(
                market_id=observation.market_id,
                probability=probability,
                outcome=outcome,
            )
        )
        baseline_forecasts.append(
            BinaryForecast(
                market_id=observation.market_id,
                probability=probability,
                outcome=outcome,
            )
        )
        rows.append(
            {
                "record_id": observation.record_id,
                "event_id": observation.event_id,
                "market_id": observation.market_id,
                "observed_at": observation.observed_at.isoformat().replace("+00:00", "Z"),
                "outcome": outcome,
                "candidate_probability": probability,
                "market_probability": probability,
            }
        )

    candidate = ProperScoringRules.evaluate_binary_forecasts(candidate_forecasts).to_dict()
    baseline = ProperScoringRules.evaluate_binary_forecasts(baseline_forecasts).to_dict()
    provider = {
        "name": MARKET_BASELINE_PROVIDER,
        "version": MARKET_BASELINE_PROVIDER_VERSION,
    }
    assumptions = {
        "candidate_source": "point-in-time market_probability",
        "label_join": "separate resolution record joined after forecast boundary",
        "score_direction": {
            "brier_score": "lower_is_better",
            "log_score": "higher_is_better",
        },
    }
    return {
        "report_version": EVALUATION_REPORT_VERSION,
        "valid": True,
        "status": "valid",
        "dataset": {
            "schema_version": "autopredict.dataset.v1",
            "dataset_id": dataset.manifest.dataset_id,
            "venue": dataset.manifest.venue,
            "dataset_sha256": dataset.dataset_sha256,
            "manifest_sha256": dataset.manifest_sha256,
            "records_sha256": dataset.records_sha256,
            "record_count": dataset.manifest.record_count,
            "completeness": dataset.manifest.completeness,
        },
        "code": {"package": "autopredict", "version": __version__},
        "provider": {**provider, "config_sha256": _canonical_hash(provider)},
        "methodology": {
            "name": "binary-proper-scoring",
            "version": METHODOLOGY_VERSION,
            "assumptions": assumptions,
        },
        "counts": {
            "forecasts": len(rows),
            "independent_events": len({row["event_id"] for row in rows}),
            "markets": len({row["market_id"] for row in rows}),
        },
        "candidate": candidate,
        "baseline": baseline,
        "skill": {
            "brier_skill": baseline["brier_score"] - candidate["brier_score"],
            "log_skill": candidate["log_score"] - baseline["log_score"],
        },
        "rows": rows,
        "warnings": list(dataset.manifest.warnings),
    }


def report_json(report: dict[str, Any]) -> str:
    """Return stable report bytes for identical inputs."""

    return json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
