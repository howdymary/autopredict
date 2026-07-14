"""End-to-end CLI tests for canonical validation and evaluation."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests/fixtures/datasets/resolved-v1/manifest.json"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "autopredict.cli", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_validate_and_evaluate_canonical_fixture(tmp_path: Path) -> None:
    validation = json.loads(_run("validate", "--dataset", str(MANIFEST)).stdout)
    assert validation["valid"] is True
    assert validation["schema_version"] == "autopredict.dataset.v1"
    assert validation["independent_events"] == 2

    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = _run(
        "evaluate",
        "--dataset",
        str(MANIFEST),
        "--provider",
        "market-baseline",
        "--output",
        str(first_path),
    )
    second = _run(
        "evaluate",
        "--dataset",
        str(MANIFEST),
        "--provider",
        "market-baseline",
        "--output",
        str(second_path),
    )

    assert first.stdout == second.stdout
    assert first_path.read_bytes() == second_path.read_bytes()
    assert json.loads(first.stdout)["valid"] is True


def test_validate_fails_clearly_for_unknown_schema(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["schema_version"] = "unknown"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "autopredict.cli", "validate", "--dataset", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "dataset validation failed" in completed.stderr
    assert "unsupported schema_version" in completed.stderr
