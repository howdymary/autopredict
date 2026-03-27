"""Minimal local cache helpers for deterministic fixture-backed data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FixtureCache:
    """Tiny JSON cache rooted at a local directory."""

    root: Path

    def __init__(self, root: str | Path) -> None:
        object.__setattr__(self, "root", Path(root))
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        """Return the cache path for one logical key."""

        if not key:
            raise ValueError("key cannot be empty")
        return self.root / f"{key}.json"

    def exists(self, key: str) -> bool:
        """Return whether a cache entry exists."""

        return self.path_for(key).exists()

    def write_json(self, key: str, payload: Any) -> Path:
        """Write JSON payload to cache and return the path."""

        path = self.path_for(key)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return path

    def read_json(self, key: str) -> Any:
        """Read JSON payload from cache."""

        path = self.path_for(key)
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
