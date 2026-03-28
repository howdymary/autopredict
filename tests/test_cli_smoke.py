"""Smoke tests for the documented package CLI entrypoint."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent

# Minimal inline test dataset (2 markets, enough to exercise the CLI)
_TEST_MARKETS = [
    {
        "market_id": "cli-test-001",
        "category": "test",
        "market_prob": 0.44,
        "fair_prob": 0.52,
        "outcome": 1,
        "time_to_expiry_hours": 240.0,
        "next_mid_price": 0.49,
        "order_book": {
            "bids": [[0.43, 180.0], [0.42, 220.0], [0.41, 260.0]],
            "asks": [[0.45, 160.0], [0.46, 210.0], [0.47, 250.0]],
        },
    },
    {
        "market_id": "cli-test-002",
        "category": "test",
        "market_prob": 0.61,
        "fair_prob": 0.54,
        "outcome": 0,
        "time_to_expiry_hours": 96.0,
        "next_mid_price": 0.57,
        "order_book": {
            "bids": [[0.60, 150.0], [0.59, 200.0], [0.58, 250.0]],
            "asks": [[0.62, 140.0], [0.63, 190.0], [0.64, 240.0]],
        },
    },
]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "autopredict.cli", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_module_backtest_outputs_metrics_json() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_TEST_MARKETS, f)
        dataset_path = f.name

    completed = _run_cli("backtest", "--dataset", dataset_path)
    metrics = json.loads(completed.stdout)

    assert metrics["num_trades"] >= 1
    assert metrics["ending_bankroll"] > 0
    assert "agent_feedback" in metrics

    Path(dataset_path).unlink(missing_ok=True)


def test_module_score_latest_reads_saved_metrics() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_TEST_MARKETS, f)
        dataset_path = f.name

    _run_cli("backtest", "--dataset", dataset_path)
    completed = _run_cli("score-latest")
    metrics = json.loads(completed.stdout)

    assert "total_pnl" in metrics
    assert "sharpe" in metrics

    Path(dataset_path).unlink(missing_ok=True)
