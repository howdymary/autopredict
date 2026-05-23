"""Registry for named domain adapters."""

from __future__ import annotations

from autopredict.domains.base import DomainAdapter


class DomainRegistry:
    """Small deterministic registry for domain adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, DomainAdapter] = {}

    def register(self, name: str, adapter: DomainAdapter) -> None:
        """Register an adapter under a stable name."""

        if not name:
            raise ValueError("name cannot be empty")
        if name in self._adapters:
            raise ValueError(f"domain adapter already registered: {name}")
        self._adapters[name] = adapter

    def get(self, name: str) -> DomainAdapter:
        """Return one adapter by name."""

        try:
            return self._adapters[name]
        except KeyError as exc:
            raise KeyError(f"unknown domain adapter: {name}") from exc

    def names(self) -> tuple[str, ...]:
        """Return registered adapter names in sorted order."""

        return tuple(sorted(self._adapters))


domain_registry = DomainRegistry()
