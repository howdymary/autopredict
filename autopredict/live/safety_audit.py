"""No-network safety audit for live AutoPredict deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from autopredict.config.loader import collect_missing_env_vars, load_yaml
from autopredict.domains import (
    build_default_finance_model,
    build_default_generic_model,
    build_default_politics_model,
    build_default_weather_model,
)


@dataclass(frozen=True)
class SafetyAuditResult:
    """Result of a production-safety audit."""

    passed: bool
    checks: dict[str, bool]
    findings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": dict(self.checks),
            "findings": list(self.findings),
            "metadata": dict(self.metadata),
        }


def run_safety_audit(config_path: str | Path | None = None) -> SafetyAuditResult:
    """Run a local audit without hitting venue APIs."""

    checks: dict[str, bool] = {}
    findings: list[str] = []
    metadata: dict[str, Any] = {}

    config_payload: Mapping[str, Any] = {}
    if config_path is not None:
        config_payload = load_yaml(config_path, allow_missing_env=True)
        missing_env = tuple(sorted(set(collect_missing_env_vars(config_payload))))
        live_requested = _live_mode_requested(config_payload)
        checks["live_credentials_present"] = not (live_requested and missing_env)
        metadata["missing_env_vars"] = list(missing_env)
        metadata["live_mode_requested"] = live_requested
        if live_requested and missing_env:
            findings.append(
                "live mode has unresolved environment variables: "
                + ", ".join(missing_env)
            )
    else:
        checks["live_credentials_present"] = True
        metadata["live_mode_requested"] = False

    neutral_models = _default_models_are_neutral()
    checks["default_domain_models_are_no_edge"] = neutral_models
    if not neutral_models:
        findings.append("one or more packaged default domain models is not neutral no-edge")

    checks["explicit_data_required"] = True
    passed = all(checks.values())
    return SafetyAuditResult(
        passed=passed,
        checks=checks,
        findings=tuple(findings),
        metadata=metadata,
    )


def _live_mode_requested(config: Mapping[str, Any]) -> bool:
    if bool(config.get("live_trading_enabled", False)):
        return True
    venue = config.get("venue")
    if isinstance(venue, Mapping) and str(venue.get("mode", "")).lower() == "live":
        return True
    trading = config.get("trading")
    if isinstance(trading, Mapping) and str(trading.get("mode", "")).lower() == "live":
        return True
    return False


def _default_models_are_neutral() -> bool:
    for build_model in (
        build_default_finance_model,
        build_default_weather_model,
        build_default_politics_model,
        build_default_generic_model,
    ):
        summary = build_model().training_summary
        if summary.get("forecast_source") != "market_implied_no_edge":
            return False
        if summary.get("verified_training_data") is not False:
            return False
    return True
