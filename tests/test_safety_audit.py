"""Tests for production safety audit checks."""

from __future__ import annotations

from pathlib import Path

from autopredict.live.safety_audit import run_safety_audit


def test_safety_audit_passes_without_live_config() -> None:
    result = run_safety_audit()

    assert result.passed is True
    assert result.checks["explicit_data_required"] is True
    assert result.checks["default_domain_models_are_no_edge"] is True


def test_safety_audit_blocks_live_config_with_missing_env(tmp_path: Path) -> None:
    config = tmp_path / "live.yaml"
    config.write_text(
        "venue:\n"
        "  mode: live\n"
        "  api_key: ${POLYMARKET_API_KEY}\n",
        encoding="utf-8",
    )

    result = run_safety_audit(config)

    assert result.passed is False
    assert result.checks["live_credentials_present"] is False
    assert result.metadata["missing_env_vars"] == ["POLYMARKET_API_KEY"]
