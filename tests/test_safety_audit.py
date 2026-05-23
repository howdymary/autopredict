"""Tests for production safety audit checks."""

from __future__ import annotations

from pathlib import Path

from autopredict.live.safety_audit import run_safety_audit


def test_safety_audit_passes_without_live_config() -> None:
    result = run_safety_audit()

    assert result.passed is True
    assert result.checks["explicit_data_required"] is True
    assert result.checks["default_domain_models_are_no_edge"] is True


def test_safety_audit_blocks_live_config_with_missing_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for env_name in (
        "POLYMARKET_API_KEY",
        "POLYMARKET_API_SECRET",
        "POLYMARKET_API_PASSPHRASE",
        "POLYMARKET_PRIVATE_KEY",
        "POLYMARKET_FUNDER",
    ):
        monkeypatch.delenv(env_name, raising=False)
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
    assert result.metadata["missing_env_vars"] == [
        "POLYMARKET_API_KEY",
        "POLYMARKET_API_PASSPHRASE",
        "POLYMARKET_API_SECRET",
        "POLYMARKET_FUNDER",
        "POLYMARKET_PRIVATE_KEY",
    ]


def test_safety_audit_requires_all_polymarket_trading_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for env_name in (
        "POLYMARKET_API_KEY",
        "POLYMARKET_API_SECRET",
        "POLYMARKET_API_PASSPHRASE",
        "POLYMARKET_PRIVATE_KEY",
        "POLYMARKET_FUNDER",
    ):
        monkeypatch.delenv(env_name, raising=False)
    config = tmp_path / "live.yaml"
    config.write_text(
        "venue:\n"
        "  name: polymarket\n"
        "  mode: live\n"
        "  api_key: ${POLYMARKET_API_KEY}\n"
        "  api_secret: ${POLYMARKET_API_SECRET}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("POLYMARKET_API_KEY", "key")
    monkeypatch.setenv("POLYMARKET_API_SECRET", "secret")

    result = run_safety_audit(config)

    assert result.passed is False
    assert result.metadata["missing_env_vars"] == [
        "POLYMARKET_API_PASSPHRASE",
        "POLYMARKET_FUNDER",
        "POLYMARKET_PRIVATE_KEY",
    ]


def test_safety_audit_passes_live_config_when_required_credentials_are_present(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for env_name in (
        "POLYMARKET_API_KEY",
        "POLYMARKET_API_SECRET",
        "POLYMARKET_API_PASSPHRASE",
        "POLYMARKET_PRIVATE_KEY",
        "POLYMARKET_FUNDER",
    ):
        monkeypatch.delenv(env_name, raising=False)
    config = tmp_path / "live.yaml"
    config.write_text(
        "venue:\n"
        "  name: polymarket\n"
        "  mode: live\n"
        "  api_key: ${POLYMARKET_API_KEY}\n"
        "  api_secret: ${POLYMARKET_API_SECRET}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("POLYMARKET_API_KEY", "key")
    monkeypatch.setenv("POLYMARKET_API_SECRET", "secret")
    monkeypatch.setenv("POLYMARKET_API_PASSPHRASE", "passphrase")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "private-key")
    monkeypatch.setenv("POLYMARKET_FUNDER", "0xfunder")

    result = run_safety_audit(config)

    assert result.passed is True
    assert result.metadata["missing_env_vars"] == []
