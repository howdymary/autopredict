"""Typed, forecast-safe provider contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import TYPE_CHECKING, Any, Callable, Mapping, Protocol, Union

if TYPE_CHECKING:
    from autopredict.evaluation.contracts import MarketObservationV1


class ForecastValidationError(ValueError):
    """Raised when a provider request or output violates the contract."""


class ForecastProviderFailure(RuntimeError):
    """Raised when provider execution fails rather than explicitly abstaining."""


def canonical_config_copy(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and deep-copy strict JSON provider configuration."""

    def copy_value(value: Any, *, location: str) -> Any:
        if value is None or isinstance(value, (bool, str)):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(float(value)):
                raise ForecastValidationError(f"{location} must be finite")
            return value
        if isinstance(value, list):
            return [
                copy_value(item, location=f"{location}[{index}]")
                for index, item in enumerate(value)
            ]
        if isinstance(value, Mapping):
            result: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ForecastValidationError(f"{location} object keys must be strings")
                result[key] = copy_value(item, location=f"{location}.{key}")
            return result
        raise ForecastValidationError(f"{location} must contain strict JSON values")

    copied = copy_value(config, location="provider config")
    if not isinstance(copied, dict):  # pragma: no cover - Mapping guarantees this shape
        raise ForecastValidationError("provider config must be a JSON object")
    return copied


def canonical_config_hash(config: Mapping[str, Any]) -> str:
    """Hash a JSON-compatible provider configuration deterministically."""

    canonical = canonical_config_copy(config)
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_utc(value: datetime, *, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ForecastValidationError(f"{field} must be timezone-aware UTC")


def _require_probability(value: float, *, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForecastValidationError(f"{field} must be numeric")
    if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise ForecastValidationError(f"{field} must be finite and in [0, 1]")


@dataclass(frozen=True)
class ForecastPriceLevel:
    """Immutable forecast-side price level."""

    price: float
    size: float

    def __post_init__(self) -> None:
        _require_probability(self.price, field="order_book price")
        if (
            isinstance(self.size, bool)
            or not isinstance(self.size, (int, float))
            or not math.isfinite(float(self.size))
            or self.size <= 0
        ):
            raise ForecastValidationError("order_book size must be finite and positive")


@dataclass(frozen=True)
class ForecastOrderBook:
    """Exact immutable order-book shape allowed across the forecast boundary."""

    bids: tuple[ForecastPriceLevel, ...]
    asks: tuple[ForecastPriceLevel, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bids, tuple) or not isinstance(self.asks, tuple):
            raise ForecastValidationError("order_book sides must be tuples")
        if not self.bids or not self.asks:
            raise ForecastValidationError("order_book sides must be non-empty")
        if not all(isinstance(level, ForecastPriceLevel) for level in (*self.bids, *self.asks)):
            raise ForecastValidationError("order_book levels must use ForecastPriceLevel")
        if tuple(sorted(self.bids, key=lambda item: item.price, reverse=True)) != self.bids:
            raise ForecastValidationError("order_book bids must be descending")
        if tuple(sorted(self.asks, key=lambda item: item.price)) != self.asks:
            raise ForecastValidationError("order_book asks must be ascending")
        if self.bids[0].price > self.asks[0].price:
            raise ForecastValidationError("order_book must not be crossed")


@dataclass(frozen=True)
class ObservationProvenance:
    """Exact source identity allowed across the forecast boundary."""

    source: str
    source_record_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source, str)
            or not self.source.strip()
            or not isinstance(self.source_record_id, str)
            or not self.source_record_id.strip()
        ):
            raise ForecastValidationError("observation provenance fields must be non-empty")


@dataclass(frozen=True)
class ForecastRequest:
    """Point-in-time provider input that structurally excludes realized labels."""

    record_id: str
    event_id: str
    market_id: str
    question: str
    category: str
    observed_at: datetime
    expiry: datetime
    market_probability: float
    order_book: ForecastOrderBook
    provenance: ObservationProvenance

    def __post_init__(self) -> None:
        for field_name in ("record_id", "event_id", "market_id", "question", "category"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ForecastValidationError(f"{field_name} must be a non-empty string")
        _require_utc(self.observed_at, field="observed_at")
        _require_utc(self.expiry, field="expiry")
        if self.observed_at >= self.expiry:
            raise ForecastValidationError("observed_at must precede expiry")
        _require_probability(self.market_probability, field="market_probability")
        if not isinstance(self.provenance, ObservationProvenance):
            raise ForecastValidationError("provenance must use ObservationProvenance")
        if not isinstance(self.order_book, ForecastOrderBook):
            raise ForecastValidationError("order_book must use ForecastOrderBook")

    @classmethod
    def from_observation(cls, observation: "MarketObservationV1") -> "ForecastRequest":
        """Copy only forecast-safe fields from a canonical observation."""

        return cls(
            record_id=observation.record_id,
            event_id=observation.event_id,
            market_id=observation.market_id,
            question=observation.question,
            category=observation.category,
            observed_at=observation.observed_at,
            expiry=observation.expiry,
            market_probability=observation.market_probability,
            order_book=ForecastOrderBook(
                bids=tuple(
                    ForecastPriceLevel(price=level.price, size=level.size)
                    for level in observation.order_book.bids
                ),
                asks=tuple(
                    ForecastPriceLevel(price=level.price, size=level.size)
                    for level in observation.order_book.asks
                ),
            ),
            provenance=ObservationProvenance(
                source=str(observation.provenance["source"]),
                source_record_id=str(observation.provenance["source_record_id"]),
            ),
        )


@dataclass(frozen=True)
class ProviderProvenance:
    """Stable identity and configuration fingerprint for a provider."""

    name: str
    version: str
    config_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or not isinstance(self.version, str)
            or not self.version.strip()
        ):
            raise ForecastValidationError("provider name and version must be non-empty")
        if (
            not isinstance(self.config_sha256, str)
            or len(self.config_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.config_sha256)
        ):
            raise ForecastValidationError("config_sha256 must be 64 lowercase hex characters")

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "config_sha256": self.config_sha256,
        }


@dataclass(frozen=True)
class ForecastResult:
    """A provider probability with confidence, time, and provenance."""

    probability: float
    confidence: float
    as_of: datetime
    provenance: ProviderProvenance

    def __post_init__(self) -> None:
        _require_probability(self.probability, field="probability")
        _require_probability(self.confidence, field="confidence")
        _require_utc(self.as_of, field="as_of")
        if not isinstance(self.provenance, ProviderProvenance):
            raise ForecastValidationError("result provenance must use ProviderProvenance")


@dataclass(frozen=True)
class ForecastAbstention:
    """An intentional no-forecast decision, distinct from provider failure."""

    reason: str
    as_of: datetime
    provenance: ProviderProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ForecastValidationError("abstention reason must be non-empty")
        _require_utc(self.as_of, field="as_of")
        if not isinstance(self.provenance, ProviderProvenance):
            raise ForecastValidationError("abstention provenance must use ProviderProvenance")


ForecastOutput = Union[ForecastResult, ForecastAbstention]


class ForecastProvider(Protocol):
    """Interface shared by built-in and user-supplied forecast providers."""

    @property
    def provenance(self) -> ProviderProvenance: ...

    def forecast(self, request: ForecastRequest) -> ForecastOutput: ...


def invoke_provider(provider: ForecastProvider, request: ForecastRequest) -> ForecastOutput:
    """Run and validate one provider call at the observation boundary."""

    provenance = provider.provenance
    if not isinstance(provenance, ProviderProvenance):
        raise ForecastValidationError("provider provenance must use ProviderProvenance")
    try:
        output = provider.forecast(request)
    except ForecastProviderFailure:
        raise
    except Exception as exc:
        raise ForecastProviderFailure(f"provider {provenance.name!r} failed: {exc}") from exc
    if not isinstance(output, (ForecastResult, ForecastAbstention)):
        raise ForecastValidationError("provider returned an unsupported output type")
    if provider.provenance != provenance:
        raise ForecastValidationError("provider provenance changed during invocation")
    if output.provenance != provenance:
        raise ForecastValidationError("output provenance does not match provider provenance")
    if output.as_of != request.observed_at:
        direction = "stale" if output.as_of < request.observed_at else "future"
        raise ForecastValidationError(f"provider as_of is {direction} for the observation")
    return output


ForecastCallable = Callable[[ForecastRequest], ForecastOutput]
