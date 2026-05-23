"""Factory registry for prediction-market strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from autopredict.prediction_market.strategy import PredictionMarketStrategy


@dataclass(frozen=True)
class StrategyRegistration:
    """Metadata about one registered strategy factory."""

    name: str
    factory: Callable[..., PredictionMarketStrategy]
    description: str = ""
    tags: tuple[str, ...] = ()


class StrategyRegistry:
    """Register and instantiate named strategy factories."""

    def __init__(self) -> None:
        self._registrations: dict[str, StrategyRegistration] = {}

    def register(
        self,
        name: str,
        *,
        factory: Callable[..., PredictionMarketStrategy],
        description: str = "",
        tags: tuple[str, ...] = (),
    ) -> None:
        """Register a named strategy factory."""

        if not name.strip():
            raise ValueError("name must be non-empty")
        if name in self._registrations:
            raise ValueError(f"strategy '{name}' is already registered")
        self._registrations[name] = StrategyRegistration(
            name=name,
            factory=factory,
            description=description,
            tags=tags,
        )

    def create(self, name: str, **kwargs: object) -> PredictionMarketStrategy:
        """Instantiate a strategy from its registered factory."""

        registration = self._registrations.get(name)
        if registration is None:
            raise KeyError(f"unknown strategy '{name}'")
        return registration.factory(**kwargs)

    def get(self, name: str) -> StrategyRegistration | None:
        """Return the registration metadata for one strategy name."""

        return self._registrations.get(name)

    def names(self) -> tuple[str, ...]:
        """Return registered names in insertion order."""

        return tuple(self._registrations)

    def registrations(self) -> tuple[StrategyRegistration, ...]:
        """Return all registrations in insertion order."""

        return tuple(self._registrations.values())
