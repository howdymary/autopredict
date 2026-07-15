"""Built-in and user-adapted forecast providers."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, Mapping

from autopredict.domains.recalibration import (
    MAX_SCALE,
    MAX_SHIFT,
    MIN_SCALE,
    MIN_SHIFT,
    sigmoid,
    logit,
)
from autopredict.forecasting.contracts import (
    ForecastCallable,
    ForecastOutput,
    ForecastRequest,
    ForecastResult,
    ProviderProvenance,
    canonical_config_copy,
    canonical_config_hash,
)


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


@dataclass(frozen=True)
class MarketBaselineProvider:
    """Return the recorded point-in-time market probability."""

    _provenance: ProviderProvenance = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_provenance",
            ProviderProvenance(
                name="market-baseline",
                version="1",
                config_sha256=canonical_config_hash({"name": "market-baseline", "version": "1"}),
            ),
        )

    @property
    def provenance(self) -> ProviderProvenance:
        return self._provenance

    def forecast(self, request: ForecastRequest) -> ForecastResult:
        return ForecastResult(
            probability=request.market_probability,
            confidence=1.0,
            as_of=request.observed_at,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class RecalibrationProvider:
    """Apply an explicit monotonic log-odds recalibration."""

    scale: float = 1.0
    shift: float = 0.0
    fit_sample_size: int = 0
    _provenance: ProviderProvenance = field(init=False)

    def __post_init__(self) -> None:
        if not math.isfinite(self.scale) or not MIN_SCALE <= self.scale <= MAX_SCALE:
            raise ValueError(f"scale must be finite and in [{MIN_SCALE}, {MAX_SCALE}]")
        if not math.isfinite(self.shift) or not MIN_SHIFT <= self.shift <= MAX_SHIFT:
            raise ValueError(f"shift must be finite and in [{MIN_SHIFT}, {MAX_SHIFT}]")
        if (
            isinstance(self.fit_sample_size, bool)
            or not isinstance(self.fit_sample_size, int)
            or self.fit_sample_size < 0
        ):
            raise ValueError("fit_sample_size must be a non-negative integer")
        config = {
            "fit_sample_size": self.fit_sample_size,
            "scale": self.scale,
            "shift": self.shift,
        }
        object.__setattr__(
            self,
            "_provenance",
            ProviderProvenance(
                name="market-recalibration",
                version="1",
                config_sha256=canonical_config_hash(config),
            ),
        )

    @property
    def provenance(self) -> ProviderProvenance:
        return self._provenance

    def forecast(self, request: ForecastRequest) -> ForecastResult:
        if self.scale == 1.0 and self.shift == 0.0:
            probability = request.market_probability
        else:
            probability = sigmoid(self.scale * logit(request.market_probability) + self.shift)
        edge = abs(probability - request.market_probability)
        return ForecastResult(
            probability=probability,
            confidence=min(0.95, 0.5 + edge * 4.0),
            as_of=request.observed_at,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class CallableForecastProvider:
    """Adapt a user callable without placing opaque model objects in snapshots."""

    callback: ForecastCallable
    name: str
    version: str
    config: Mapping[str, Any]
    _provenance: ProviderProvenance = field(init=False)

    def __post_init__(self) -> None:
        if not callable(self.callback):
            raise TypeError("callback must be callable")
        config = canonical_config_copy(self.config)
        object.__setattr__(self, "config", _freeze_json(config))
        object.__setattr__(
            self,
            "_provenance",
            ProviderProvenance(
                name=self.name,
                version=self.version,
                config_sha256=canonical_config_hash(config),
            ),
        )

    @property
    def provenance(self) -> ProviderProvenance:
        return self._provenance

    def forecast(self, request: ForecastRequest) -> ForecastOutput:
        return self.callback(request)
