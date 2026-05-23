"""Package shim for the legacy root ``run_experiment_with_validation.py`` module."""

from __future__ import annotations

from pathlib import Path

_LEGACY_PATH = Path(__file__).resolve().parent.parent / "run_experiment_with_validation.py"
exec(compile(_LEGACY_PATH.read_text(encoding="utf-8"), str(_LEGACY_PATH), "exec"), globals())
