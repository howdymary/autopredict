"""Smoke tests for the documented package CLI entrypoint."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "autopredict.cli", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _run_legacy_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "run_experiment.py"), *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _run_live_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_live.py"), *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_module_backtest_outputs_metrics_json() -> None:
    completed = _run_cli("backtest")
    metrics = json.loads(completed.stdout)

    assert metrics["num_trades"] >= 1
    assert metrics["ending_bankroll"] > 0
    assert "agent_feedback" in metrics


def test_module_score_latest_reads_saved_metrics() -> None:
    _run_cli("backtest")
    completed = _run_cli("score-latest")
    metrics = json.loads(completed.stdout)

    assert "total_pnl" in metrics
    assert "sharpe" in metrics


def test_legacy_run_experiment_script_executes_directly() -> None:
    completed = _run_legacy_script(
        "--config",
        str(ROOT / "strategy_configs/baseline.json"),
        "--dataset",
        str(ROOT / "datasets/sample_markets.json"),
        "--strategy-guidance",
        str(ROOT / "strategy.md"),
    )
    metrics = json.loads(completed.stdout)

    assert metrics["num_trades"] >= 1
    assert metrics["forecast_source"] == "dataset_fair_prob"


def test_live_script_dry_run_does_not_require_real_env_vars() -> None:
    completed = _run_live_script(
        "--config",
        str(ROOT / "configs/live_trading.yaml.example"),
        "--dry-run",
    )

    assert "DRY RUN MODE" in completed.stdout
    assert "POLYMARKET_API_KEY" in completed.stdout
