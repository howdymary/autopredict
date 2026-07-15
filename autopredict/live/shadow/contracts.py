"""Immutable contracts for deterministic, credential-free shadow execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Union

PRICE_SCALE = 1_000_000_000
QUANTITY_SCALE = 1_000_000
CASH_SCALE = 1_000_000


class ShadowValidationError(ValueError):
    """Raised when shadow input cannot be processed safely."""


class ShadowIntegrityError(RuntimeError):
    """Raised when durable state disagrees with its authoritative journal."""


def _require_int(value: object, *, field: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ShadowValidationError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise ShadowValidationError(f"{field} must be at least {minimum}")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stable_id(prefix: str, value: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def to_fixed(value: object, scale: int, *, field: str) -> int:
    if isinstance(value, bool):
        raise ShadowValidationError(f"{field} must be numeric")
    try:
        decimal = Decimal(str(value))
    except Exception as exc:
        raise ShadowValidationError(f"{field} must be numeric") from exc
    if not decimal.is_finite():
        raise ShadowValidationError(f"{field} must be finite")
    return int((decimal * scale).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def from_fixed(value: int, scale: int) -> Decimal:
    return Decimal(value) / Decimal(scale)


def utc_text(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise ShadowValidationError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ShadowValidationError("timestamp must be timezone-aware UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ShadowValidationError("timestamp must be ISO-8601 UTC") from exc
    utc_text(parsed)
    return parsed.astimezone(timezone.utc)


class ShadowSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is ShadowSide.BUY else -1


class ShadowOrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class BreakerReason(str, Enum):
    GAP = "gap"
    RECONNECT = "reconnect"
    STALE = "stale"
    OUT_OF_ORDER = "out_of_order"
    INTEGRITY = "integrity"
    ACCOUNTING = "accounting"
    ERROR = "error"
    DAILY_LOSS = "daily_loss"
    MANUAL = "manual"


@dataclass(frozen=True)
class BookLevel:
    price_nanos: int
    quantity_micros: int

    def __post_init__(self) -> None:
        _require_int(self.price_nanos, field="book price", minimum=0)
        _require_int(self.quantity_micros, field="book quantity", minimum=1)
        if not 0 <= self.price_nanos <= PRICE_SCALE:
            raise ShadowValidationError("book price must be in [0, 1]")
        if self.quantity_micros <= 0:
            raise ShadowValidationError("book quantity must be positive")


@dataclass(frozen=True)
class BookObservation:
    event_id: str
    capture_sequence: int
    market_id: str
    event_market_id: str
    question: str
    category: str
    observed_at: datetime
    expiry: datetime
    market_probability_nanos: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    source: str
    source_record_id: str
    reconnected: bool = False

    def __post_init__(self) -> None:
        for value in (
            self.event_id,
            self.market_id,
            self.event_market_id,
            self.question,
            self.category,
            self.source,
            self.source_record_id,
        ):
            if not isinstance(value, str) or not value.strip():
                raise ShadowValidationError("observation identifiers must be non-empty")
        if not isinstance(self.reconnected, bool):
            raise ShadowValidationError("reconnected must be boolean")
        if not isinstance(self.bids, tuple) or not isinstance(self.asks, tuple):
            raise ShadowValidationError("book sides must be tuples")
        if not all(isinstance(level, BookLevel) for level in (*self.bids, *self.asks)):
            raise ShadowValidationError("book sides must contain BookLevel values")
        _require_int(self.capture_sequence, field="capture_sequence", minimum=1)
        _require_int(self.market_probability_nanos, field="market probability", minimum=0)
        utc_text(self.observed_at)
        utc_text(self.expiry)
        if self.observed_at >= self.expiry:
            raise ShadowValidationError("observation must precede expiry")
        if not 0 <= self.market_probability_nanos <= PRICE_SCALE:
            raise ShadowValidationError("market probability must be in [0, 1]")
        if not self.bids or not self.asks:
            raise ShadowValidationError("both book sides are required")
        if tuple(sorted(self.bids, key=lambda level: level.price_nanos, reverse=True)) != self.bids:
            raise ShadowValidationError("bids must be descending")
        if tuple(sorted(self.asks, key=lambda level: level.price_nanos)) != self.asks:
            raise ShadowValidationError("asks must be ascending")
        if self.bids[0].price_nanos > self.asks[0].price_nanos:
            raise ShadowValidationError("book must not be crossed")


@dataclass(frozen=True)
class TradePrint:
    event_id: str
    capture_sequence: int
    trade_id: str
    market_id: str
    observed_at: datetime
    executed_at: datetime
    side: ShadowSide
    price_nanos: int
    quantity_micros: int

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.event_id, self.trade_id, self.market_id)
        ):
            raise ShadowValidationError("trade identifiers must be non-empty")
        _require_int(self.capture_sequence, field="capture_sequence", minimum=1)
        if not isinstance(self.side, ShadowSide):
            raise ShadowValidationError("trade side must use ShadowSide")
        _require_int(self.price_nanos, field="trade price", minimum=0)
        _require_int(self.quantity_micros, field="trade quantity", minimum=1)
        utc_text(self.observed_at)
        utc_text(self.executed_at)
        if self.executed_at > self.observed_at:
            raise ShadowValidationError("trade execution cannot follow capture observation")
        BookLevel(self.price_nanos, self.quantity_micros)


@dataclass(frozen=True)
class FeedFault:
    event_id: str
    capture_sequence: int
    observed_at: datetime
    reason: BreakerReason
    detail: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.event_id, self.detail)
        ):
            raise ShadowValidationError("feed fault identity and detail must be non-empty")
        _require_int(self.capture_sequence, field="capture_sequence", minimum=1)
        if not isinstance(self.reason, BreakerReason):
            raise ShadowValidationError("fault reason must use BreakerReason")
        utc_text(self.observed_at)


@dataclass(frozen=True)
class FeedMarker:
    """A persisted capture record that has no direct execution effect."""

    event_id: str
    capture_sequence: int
    observed_at: datetime
    kind: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip() for value in (self.event_id, self.kind)
        ):
            raise ShadowValidationError("feed marker fields must be non-empty")
        _require_int(self.capture_sequence, field="capture_sequence", minimum=1)
        utc_text(self.observed_at)


ShadowFeedEvent = Union[BookObservation, TradePrint, FeedFault, FeedMarker]


@dataclass(frozen=True)
class ShadowOrder:
    client_order_id: str
    decision_id: str
    market_id: str
    side: ShadowSide
    order_type: ShadowOrderType
    quantity_micros: int
    limit_price_nanos: int | None
    reduce_only: bool
    created_at: datetime

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.client_order_id, self.decision_id, self.market_id)
        ):
            raise ShadowValidationError("order identifiers must be non-empty")
        _require_int(self.quantity_micros, field="order quantity", minimum=1)
        if not isinstance(self.side, ShadowSide) or not isinstance(
            self.order_type, ShadowOrderType
        ):
            raise ShadowValidationError("order side/type must use shadow enums")
        if not isinstance(self.reduce_only, bool):
            raise ShadowValidationError("reduce_only must be boolean")
        if self.limit_price_nanos is not None:
            _require_int(self.limit_price_nanos, field="limit price", minimum=0)
        if self.order_type is ShadowOrderType.LIMIT and self.limit_price_nanos is None:
            raise ShadowValidationError("limit order requires limit_price")
        if self.order_type is ShadowOrderType.MARKET and self.limit_price_nanos is not None:
            raise ShadowValidationError("market order cannot have limit_price")
        if self.limit_price_nanos is not None and not 0 <= self.limit_price_nanos <= PRICE_SCALE:
            raise ShadowValidationError("limit price must be in [0, 1]")
        utc_text(self.created_at)


@dataclass(frozen=True)
class ShadowFill:
    fill_id: str
    client_order_id: str
    market_id: str
    side: ShadowSide
    quantity_micros: int
    price_nanos: int
    source_event_id: str
    filled_at: datetime
    fee_cash_micros: int = 0

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.fill_id,
                self.client_order_id,
                self.market_id,
                self.source_event_id,
            )
        ):
            raise ShadowValidationError("fill identifiers must be non-empty")
        _require_int(self.quantity_micros, field="fill quantity", minimum=1)
        _require_int(self.price_nanos, field="fill price", minimum=0)
        _require_int(self.fee_cash_micros, field="fill fee", minimum=0)
        if not isinstance(self.side, ShadowSide):
            raise ShadowValidationError("fill side must use ShadowSide")
        if not 0 <= self.price_nanos <= PRICE_SCALE:
            raise ShadowValidationError("fill price must be in [0, 1]")
        if self.fee_cash_micros < 0:
            raise ShadowValidationError("fill fee must be non-negative")
        utc_text(self.filled_at)


@dataclass(frozen=True)
class ShadowRiskLimits:
    max_position_micros: int
    max_total_exposure_cash_micros: int
    max_open_markets: int
    max_daily_loss_cash_micros: int = 0

    def __post_init__(self) -> None:
        _require_int(self.max_position_micros, field="max position", minimum=1)
        _require_int(self.max_total_exposure_cash_micros, field="max exposure", minimum=1)
        _require_int(self.max_open_markets, field="max open markets", minimum=1)
        _require_int(self.max_daily_loss_cash_micros, field="max daily loss", minimum=0)
        if self.max_position_micros <= 0 or self.max_total_exposure_cash_micros <= 0:
            raise ShadowValidationError("risk limits must be positive")
        if self.max_open_markets <= 0:
            raise ShadowValidationError("max_open_markets must be positive")
