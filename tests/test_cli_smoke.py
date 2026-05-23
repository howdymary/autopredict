"""Smoke tests for the documented package CLI entrypoint."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent


def _write_resolved_dataset(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "market_id": "fixture-cli-market",
                    "market_prob": 0.50,
                    "fair_prob": 0.58,
                    "outcome": 1,
                    "time_to_expiry_hours": 24.0,
                    "next_mid_price": 0.54,
                    "order_book": {
                        "bids": [[0.49, 100.0]],
                        "asks": [[0.51, 100.0]],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )


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


def test_module_backtest_requires_explicit_real_dataset() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "autopredict.cli", "backtest"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "requires --dataset" in completed.stderr


def test_module_backtest_outputs_metrics_json(tmp_path: Path) -> None:
    dataset_path = tmp_path / "resolved_markets.json"
    _write_resolved_dataset(dataset_path)

    completed = _run_cli("backtest", "--dataset", str(dataset_path))
    metrics = json.loads(completed.stdout)

    assert metrics["num_trades"] >= 1
    assert metrics["ending_bankroll"] > 0
    assert "agent_feedback" in metrics


def test_module_score_latest_reads_saved_metrics(tmp_path: Path) -> None:
    dataset_path = tmp_path / "resolved_markets.json"
    _write_resolved_dataset(dataset_path)

    _run_cli("backtest", "--dataset", str(dataset_path))
    completed = _run_cli("score-latest")
    metrics = json.loads(completed.stdout)

    assert "total_pnl" in metrics
    assert "sharpe" in metrics


def test_legacy_run_experiment_script_executes_directly(tmp_path: Path) -> None:
    dataset_path = tmp_path / "resolved_markets.json"
    _write_resolved_dataset(dataset_path)

    completed = _run_legacy_script(
        "--config",
        str(ROOT / "strategy_configs/baseline.json"),
        "--dataset",
        str(dataset_path),
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
