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
