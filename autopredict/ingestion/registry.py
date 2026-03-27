"""Registry for named fixture-backed ingestors."""

from __future__ import annotations

from autopredict.ingestion.base import Ingestor


class IngestionRegistry:
    """Small deterministic registry for fixture-backed ingestors."""

    def __init__(self) -> None:
        self._ingestors: dict[str, Ingestor] = {}

    def register(self, name: str, ingestor: Ingestor) -> None:
        """Register an ingestor under a stable name."""

        if not name:
            raise ValueError("name cannot be empty")
        if name in self._ingestors:
            raise ValueError(f"ingestor already registered: {name}")
        self._ingestors[name] = ingestor

    def get(self, name: str) -> Ingestor:
        """Return one ingestor by name."""

        try:
            return self._ingestors[name]
        except KeyError as exc:
            raise KeyError(f"unknown ingestor: {name}") from exc

    def names(self) -> tuple[str, ...]:
        """Return registered ingestor names in sorted order."""

        return tuple(sorted(self._ingestors))


ingestion_registry = IngestionRegistry()
