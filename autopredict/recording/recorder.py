"""Credential-free Polymarket capture orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Callable, Protocol
from urllib.parse import parse_qsl, urlparse

import requests  # type: ignore[import-untyped]

from autopredict.recording.contracts import (
    CaptureBundle,
    CaptureRecord,
    CaptureValidationError,
    PublicResponse,
    canonical_json,
    parse_utc,
)


class PolymarketCaptureSource(Protocol):
    """The complete source surface available to the read-only recorder."""

    def fetch_gamma_market(self, gamma_market_id: str) -> PublicResponse: ...

    def fetch_clob_book(self, condition_id: str, token_id: str) -> PublicResponse: ...

    def fetch_public_trades(self, condition_id: str) -> tuple[PublicResponse, ...]: ...

    def fetch_gamma_resolution(self, gamma_market_id: str) -> PublicResponse | None: ...


class PublicJSONTransport(Protocol):
    """Trusted injected GET-only transport."""

    def get_json(self, endpoint: str, *, params: dict[str, str] | None = None) -> Any: ...


class RequestsPublicJSONTransport:
    """Unauthenticated GET transport restricted to official public HTTPS hosts."""

    ALLOWED_HOSTS = frozenset(
        {
            "gamma-api.polymarket.com",
            "clob.polymarket.com",
            "data-api.polymarket.com",
        }
    )

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._session = session or requests.Session()
        if session is None:
            # Disable requests' ambient netrc and proxy discovery on the default
            # transport. The new session has no auth or cookies.
            self._session.trust_env = False
        self._timeout_seconds = float(timeout_seconds)

    def get_json(self, endpoint: str, *, params: dict[str, str] | None = None) -> Any:
        self._validate_public_url(endpoint)
        self._validate_parameter_keys(params or {})
        self._validate_credential_free_session()
        request = requests.Request("GET", endpoint, params=params)
        prepared = self._session.prepare_request(request)
        if prepared.url is None:
            raise CaptureValidationError("public transport request URL is missing")
        self._validate_public_url(prepared.url)
        self._validate_headers(prepared.headers)
        response = self._session.send(
            prepared, timeout=self._timeout_seconds, allow_redirects=False
        )
        if getattr(response, "is_redirect", False):
            raise CaptureValidationError("public transport refuses redirects")
        response.raise_for_status()
        return response.json()

    def _validate_credential_free_session(self) -> None:
        if getattr(self._session, "auth", None):
            raise CaptureValidationError("public transport refuses session authentication")
        if getattr(self._session, "cert", None):
            raise CaptureValidationError("public transport refuses client certificates")
        cookies = getattr(self._session, "cookies", ())
        if cookies and list(cookies):
            raise CaptureValidationError("public transport refuses cookies")
        if getattr(self._session, "trust_env", False):
            raise CaptureValidationError("public transport refuses ambient environment credentials")
        if getattr(self._session, "proxies", {}):
            raise CaptureValidationError("public transport refuses configured proxies")
        if getattr(self._session, "params", {}):
            raise CaptureValidationError("public transport refuses session query parameters")
        self._validate_headers(getattr(self._session, "headers", {}))

    @staticmethod
    def _normalized_key(name: str) -> str:
        return name.strip().lower().replace("-", "_")

    @classmethod
    def _validate_headers(cls, headers: Any) -> None:
        allowed = {"accept", "accept_encoding", "connection", "user_agent"}
        for name in headers:
            if cls._normalized_key(str(name)) not in allowed:
                raise CaptureValidationError(
                    "public transport refuses non-public or credential-bearing headers"
                )

    @classmethod
    def _validate_parameter_keys(cls, params: dict[str, str]) -> None:
        allowed = {"limit", "market", "offset", "token_id"}
        for name in params:
            if cls._normalized_key(str(name)) not in allowed:
                raise CaptureValidationError("public transport refuses non-public query parameters")

    @classmethod
    def _validate_public_url(cls, endpoint: str) -> None:
        parsed = urlparse(endpoint)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in cls.ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise CaptureValidationError("public transport requires an allowlisted HTTPS endpoint")
        cls._validate_parameter_keys(dict(parse_qsl(parsed.query, keep_blank_values=True)))


class ReadOnlyPolymarketSource:
    """Public Gamma/CLOB/Data client around a trusted injected GET-only transport."""

    def __init__(
        self,
        *,
        transport: PublicJSONTransport,
        clock: Callable[[], datetime],
        gamma_url: str = "https://gamma-api.polymarket.com",
        clob_url: str = "https://clob.polymarket.com",
        data_url: str = "https://data-api.polymarket.com",
        trade_page_size: int = 100,
        max_trade_pages: int = 1000,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._gamma_url = gamma_url.rstrip("/")
        self._clob_url = clob_url.rstrip("/")
        self._data_url = data_url.rstrip("/")
        self._trade_page_size = trade_page_size
        self._max_trade_pages = max_trade_pages
        if trade_page_size <= 0 or max_trade_pages <= 0:
            raise CaptureValidationError("trade pagination limits must be positive")

    def _get(
        self,
        *,
        stream: str,
        endpoint: str,
        source_record_id: str,
        params: dict[str, str] | None = None,
    ) -> PublicResponse:
        requested_at = self._clock()
        payload = self._transport.get_json(endpoint, params=params)
        received_at = self._clock()
        return PublicResponse.create(
            stream=stream,
            endpoint=endpoint,
            requested_at=requested_at,
            received_at=received_at,
            source_record_id=source_record_id,
            payload=payload,
            request_params=params,
        )

    def fetch_gamma_market(self, gamma_market_id: str) -> PublicResponse:
        response = self._get(
            stream="gamma",
            endpoint=f"{self._gamma_url}/markets/{gamma_market_id}",
            source_record_id=f"gamma-market-{gamma_market_id}",
        )
        raw = _require_object(response.payload(), "Gamma market response")
        identity = _gamma_identity(raw, requested_gamma_id=gamma_market_id)
        outcomes = [str(value).strip().lower() for value in _json_list(raw.get("outcomes"))]
        prices = _json_list(raw.get("outcomePrices"))
        tokens = [str(value) for value in _json_list(raw.get("clobTokenIds"))]
        if "yes" not in outcomes or outcomes.index("yes") >= len(prices):
            raise CaptureValidationError("Gamma market is missing a YES outcome price")
        yes_index = outcomes.index("yes")
        if yes_index >= len(tokens) or not tokens[yes_index]:
            raise CaptureValidationError("Gamma market is missing a YES token id")
        raw_event = identity["raw_event"]
        category = str(raw.get("category") or raw_event.get("category") or "other")
        normalized = {
            "event": {
                "category": category,
                "event_id": identity["event_id"],
                "title": str(raw_event.get("title") or raw.get("question")),
            },
            "market": {
                "category": category,
                "event_id": identity["event_id"],
                "expiry": _require_text(raw.get("endDate") or raw.get("end_date"), "Gamma expiry"),
                "gamma_market_id": identity["gamma_market_id"],
                "market_id": identity["condition_id"],
                "market_probability": float(prices[yes_index]),
                "question": _require_text(raw.get("question"), "Gamma question"),
                "yes_token_id": tokens[yes_index],
            },
        }
        return _with_payload(response, normalized, source_at=_payload_source_at(raw))

    def fetch_clob_book(self, condition_id: str, token_id: str) -> PublicResponse:
        response = self._get(
            stream="clob-book",
            endpoint=f"{self._clob_url}/book",
            source_record_id=f"clob-book-{condition_id}-{token_id}",
            params={"token_id": token_id},
        )
        payload = _require_object(response.payload(), "CLOB book response")
        if _require_text(payload.get("market"), "CLOB market") != condition_id:
            raise CaptureValidationError("CLOB market condition does not match Gamma")
        if _require_text(payload.get("asset_id"), "CLOB asset_id") != token_id:
            raise CaptureValidationError("CLOB asset_id does not match Gamma YES token")
        normalized = {
            "asks": _book_levels(payload.get("asks"), descending=False),
            "bids": _book_levels(payload.get("bids"), descending=True),
            "market_id": condition_id,
            "token_id": token_id,
        }
        return _with_payload(response, normalized, source_at=_payload_source_at(payload))

    def fetch_public_trades(self, condition_id: str) -> tuple[PublicResponse, ...]:
        pages: list[PublicResponse] = []
        for page_number in range(self._max_trade_pages):
            offset = page_number * self._trade_page_size
            params = {
                "limit": str(self._trade_page_size),
                "market": condition_id,
                "offset": str(offset),
            }
            response = self._get(
                stream="data-trades",
                endpoint=f"{self._data_url}/trades",
                source_record_id=f"data-trades-{condition_id}-{offset}",
                params=params,
            )
            payload = response.payload()
            if not isinstance(payload, list):
                raise CaptureValidationError("public Data API trades response must be an array")
            normalized: list[dict[str, Any]] = []
            source_times: list[datetime] = []
            for item in payload:
                trade = _require_object(item, "public trade")
                returned_condition = _require_text(trade.get("conditionId"), "trade.conditionId")
                if returned_condition != condition_id:
                    raise CaptureValidationError("public trade conditionId does not match request")
                source_at = _payload_source_at(trade)
                if source_at is not None:
                    source_times.append(source_at)
                normalized.append({**trade, "market_id": condition_id})
            partial_reason = None
            if len(payload) == self._trade_page_size and page_number + 1 == self._max_trade_pages:
                partial_reason = "trade_pagination_limit"
            pages.append(
                _with_payload(
                    response,
                    {"trades": normalized},
                    source_at=max(source_times) if source_times else None,
                    partial_reason=partial_reason,
                )
            )
            if len(payload) < self._trade_page_size:
                break
        return tuple(pages)

    def fetch_gamma_resolution(self, gamma_market_id: str) -> PublicResponse | None:
        response = self._get(
            stream="gamma-resolution",
            endpoint=f"{self._gamma_url}/markets/{gamma_market_id}",
            source_record_id=f"gamma-resolution-{gamma_market_id}",
        )
        payload = _require_object(response.payload(), "Gamma resolution response")
        identity = _gamma_identity(payload, requested_gamma_id=gamma_market_id)
        if not payload.get("closed"):
            return None
        prices = [float(value) for value in _json_list(payload.get("outcomePrices"))]
        outcomes = [str(value).strip().lower() for value in _json_list(payload.get("outcomes"))]
        if "yes" not in outcomes or outcomes.index("yes") >= len(prices):
            return None
        yes_price = prices[outcomes.index("yes")]
        resolved_at = payload.get("resolutionTime") or payload.get("closedTime")
        if yes_price not in {0.0, 1.0} or not resolved_at:
            return None
        normalized = {
            "resolution": {
                "event_id": identity["event_id"],
                "gamma_market_id": identity["gamma_market_id"],
                "market_id": identity["condition_id"],
                "outcome": int(yes_price),
                "resolved_at": resolved_at,
            }
        }
        return _with_payload(response, normalized, source_at=_payload_source_at(payload))


class PolymarketRecorder:
    """Record observations now and append labels only after later resolution."""

    def __init__(self, source: PolymarketCaptureSource) -> None:
        self._source = source
        self._records: list[CaptureRecord] = []
        self._last_source_sequence: dict[str, int] = {}
        self._warnings: list[str] = []
        self._identity_by_gamma: dict[str, tuple[str, str, str]] = {}
        self._venue = "polymarket"
        self._prior_partial = False

    @classmethod
    def from_bundle(
        cls, source: PolymarketCaptureSource, bundle: CaptureBundle
    ) -> "PolymarketRecorder":
        """Restore a persisted observation bundle for later resolution capture."""

        if bundle.completeness not in {"complete", "partial"}:
            raise CaptureValidationError("restored completeness must be complete or partial")
        recorder = cls(source)
        recorder._records = list(bundle.records)
        recorder._warnings = list(bundle.warnings)
        recorder._venue = bundle.venue
        recorder._prior_partial = bundle.completeness == "partial"
        seen_responses: set[tuple[str, str, str]] = set()
        for record in recorder._records:
            response_key = (
                record.stream,
                record.source_record_id,
                record.received_at.isoformat(),
            )
            if response_key not in seen_responses and record.source_sequence is not None:
                recorder._last_source_sequence[record.stream] = record.source_sequence
            seen_responses.add(response_key)
            if record.record_type != "market_metadata":
                continue
            payload = _require_object(record.payload(), "restored market metadata")
            gamma_id = str(payload.get("gamma_market_id"))
            identity = (
                _require_text(payload.get("event_id"), "restored event_id"),
                _require_text(payload.get("market_id"), "restored market_id"),
                _require_text(payload.get("yes_token_id"), "restored yes_token_id"),
            )
            previous = recorder._identity_by_gamma.get(gamma_id)
            if previous is not None and previous != identity:
                raise CaptureValidationError("conflicting restored Gamma identity")
            recorder._identity_by_gamma[gamma_id] = identity
        return recorder

    def capture_market(self, gamma_market_id: str) -> None:
        """Compatibility alias for observation-only capture; never fetches a label."""

        self.capture_snapshot(gamma_market_id)

    def capture_snapshot(self, gamma_market_id: str) -> None:
        """Atomically capture metadata, book and exhaustively paginated trades."""

        self._atomic(lambda: self._capture_snapshot(gamma_market_id))

    def capture_resolution(self, gamma_market_id: str) -> bool:
        """Fetch and append a later resolution, returning false while unresolved."""

        result = False

        def capture() -> None:
            nonlocal result
            result = self._capture_resolution(gamma_market_id)

        self._atomic(capture)
        return result

    def _atomic(self, operation: Callable[[], None]) -> None:
        state = (
            len(self._records),
            len(self._warnings),
            dict(self._last_source_sequence),
            dict(self._identity_by_gamma),
        )
        try:
            operation()
        except Exception:
            del self._records[state[0] :]
            del self._warnings[state[1] :]
            self._last_source_sequence = state[2]
            self._identity_by_gamma = state[3]
            raise

    def _capture_snapshot(self, gamma_market_id: str) -> None:
        gamma = self._source.fetch_gamma_market(gamma_market_id)
        payload = _require_object(gamma.payload(), "Gamma market response")
        event = _require_object(payload.get("event"), "Gamma event")
        market = _require_object(payload.get("market"), "Gamma market")
        event_id = _require_text(event.get("event_id"), "event.event_id")
        condition_id = _require_text(market.get("market_id"), "market.market_id")
        token_id = _require_text(market.get("yes_token_id"), "market.yes_token_id")
        normalized_gamma = str(market.get("gamma_market_id"))
        if normalized_gamma != str(gamma_market_id):
            raise CaptureValidationError("Gamma numeric id does not match requested market")
        identity = (event_id, condition_id, token_id)
        previous = self._identity_by_gamma.get(str(gamma_market_id))
        if previous is not None and previous != identity:
            raise CaptureValidationError("Gamma identity changed across capture lifecycle")
        self._identity_by_gamma[str(gamma_market_id)] = identity
        snapshot_id = _snapshot_id(gamma, condition_id)
        self._before_response(gamma, snapshot_id=snapshot_id)
        self._append("event", gamma, snapshot_id, event)
        self._append("market_metadata", gamma, snapshot_id, market)

        book = self._source.fetch_clob_book(condition_id, token_id)
        self._before_response(book, snapshot_id=snapshot_id)
        book_payload = _require_object(book.payload(), "CLOB book response")
        if (
            book_payload.get("market_id") != condition_id
            or book_payload.get("token_id") != token_id
        ):
            raise CaptureValidationError("CLOB identity does not match Gamma")
        self._append("order_book", book, snapshot_id, book_payload)

        for trades in self._source.fetch_public_trades(condition_id):
            self._before_response(trades, snapshot_id=snapshot_id)
            if trades.partial_reason:
                self._append_gap(
                    trades,
                    snapshot_id=snapshot_id,
                    kind=trades.partial_reason,
                    expected_sequence=None,
                    observed_sequence=None,
                )
            trade_items = _require_object(trades.payload(), "public trades response").get("trades")
            if not isinstance(trade_items, list):
                raise CaptureValidationError("public trades response must contain a trades array")
            self._append(
                "trade_page",
                trades,
                snapshot_id,
                {"trade_count": len(trade_items)},
            )
            for trade in trade_items:
                item = _require_object(trade, "public trade")
                if item.get("market_id") != condition_id or item.get("conditionId") != condition_id:
                    raise CaptureValidationError("public trade condition does not match Gamma")
                self._append("trade", trades, snapshot_id, item)

    def _capture_resolution(self, gamma_market_id: str) -> bool:
        identity = self._identity_by_gamma.get(str(gamma_market_id))
        if identity is None:
            raise CaptureValidationError("capture a snapshot before requesting its resolution")
        response = self._source.fetch_gamma_resolution(gamma_market_id)
        if response is None:
            return False
        self._before_response(response, snapshot_id=None)
        payload = _require_object(
            _require_object(response.payload(), "Gamma resolution response").get("resolution"),
            "Gamma resolution",
        )
        if str(payload.get("gamma_market_id")) != str(gamma_market_id):
            raise CaptureValidationError("resolution Gamma id does not match snapshot")
        if (payload.get("event_id"), payload.get("market_id")) != identity[:2]:
            raise CaptureValidationError("resolution identity does not match snapshot")
        resolved_at = parse_utc(payload.get("resolved_at"), field="resolution.resolved_at")
        if resolved_at > response.received_at:
            raise CaptureValidationError(
                "resolution cannot be captured before its resolved_at timestamp"
            )
        if any(
            record.record_type == "resolution"
            and _require_object(record.payload(), "resolution").get("market_id") == identity[1]
            for record in self._records
        ):
            raise CaptureValidationError("resolution already captured for market")
        self._append("resolution", response, None, payload)
        return True

    def bundle(self) -> CaptureBundle:
        has_gap = any(record.record_type == "gap" for record in self._records)
        return CaptureBundle(
            venue=self._venue,
            records=tuple(self._records),
            completeness="partial" if has_gap or self._prior_partial else "complete",
            warnings=tuple(self._warnings),
        )

    def _before_response(self, response: PublicResponse, *, snapshot_id: str | None) -> None:
        previous = self._last_source_sequence.get(response.stream)
        if response.reconnected:
            self._append_gap(
                response,
                snapshot_id=snapshot_id,
                kind="reconnect",
                expected_sequence=(previous + 1) if previous is not None else None,
                observed_sequence=response.source_sequence,
            )
        if (
            previous is not None
            and response.source_sequence is not None
            and response.source_sequence != previous + 1
        ):
            self._append_gap(
                response,
                snapshot_id=snapshot_id,
                kind="sequence_gap",
                expected_sequence=previous + 1,
                observed_sequence=response.source_sequence,
            )
        if response.source_sequence is not None:
            self._last_source_sequence[response.stream] = response.source_sequence

    def _append_gap(
        self,
        response: PublicResponse,
        *,
        snapshot_id: str | None,
        kind: str,
        expected_sequence: int | None,
        observed_sequence: int | None,
    ) -> None:
        message = f"{kind} on {response.stream}: expected={expected_sequence}, observed={observed_sequence}"
        self._warnings.append(message)
        self._append(
            "gap",
            response,
            snapshot_id,
            {
                "expected_sequence": expected_sequence,
                "kind": kind,
                "observed_sequence": observed_sequence,
                "stream": response.stream,
            },
        )

    def _append(
        self, record_type: str, response: PublicResponse, snapshot_id: str | None, payload: Any
    ) -> None:
        self._records.append(
            CaptureRecord.create(
                record_type=record_type,
                capture_sequence=len(self._records) + 1,
                snapshot_id=snapshot_id,
                response=response,
                payload=payload,
            )
        )


def _gamma_identity(raw: dict[str, Any], *, requested_gamma_id: str) -> dict[str, Any]:
    raw_id = raw.get("id")
    if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)) or not str(raw_id).isdigit():
        raise CaptureValidationError("Gamma market id must be numeric")
    if str(raw_id) != str(requested_gamma_id):
        raise CaptureValidationError("Gamma response id does not match request")
    condition_id = _require_text(raw.get("conditionId"), "Gamma conditionId")
    events = _json_list(raw.get("events"))
    raw_event = _require_object(events[0], "Gamma event") if events else {}
    raw_event_id = raw_event.get("id") or raw.get("eventId")
    if isinstance(raw_event_id, bool) or not isinstance(raw_event_id, (str, int)):
        raise CaptureValidationError("Gamma event id must be text or numeric")
    event_id = str(raw_event_id)
    if not event_id:
        raise CaptureValidationError("Gamma event id must be non-empty")
    return {
        "condition_id": condition_id,
        "event_id": event_id,
        "gamma_market_id": int(str(raw_id)),
        "raw_event": raw_event,
    }


def _snapshot_id(response: PublicResponse, market_id: str) -> str:
    value = {
        "market_id": market_id,
        "received_at": response.received_at.isoformat(),
        "source_record_id": response.source_record_id,
    }
    return "snapshot-" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CaptureValidationError(f"{location} must be an object")
    return value


def _require_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise CaptureValidationError(f"{location} must be a non-empty string")
    return value


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CaptureValidationError("expected a JSON-encoded array") from exc
        if isinstance(parsed, list):
            return parsed
    return []


def _with_payload(
    response: PublicResponse,
    payload: Any,
    *,
    source_at: datetime | None = None,
    partial_reason: str | None = None,
) -> PublicResponse:
    return PublicResponse.create(
        stream=response.stream,
        endpoint=response.endpoint,
        requested_at=response.requested_at,
        received_at=response.received_at,
        source_record_id=response.source_record_id,
        payload=payload,
        request_params=response.request_params(),
        source_at=source_at,
        source_sequence=response.source_sequence,
        reconnected=response.reconnected,
        partial_reason=partial_reason,
    )


def _payload_source_at(payload: dict[str, Any]) -> datetime | None:
    value = next(
        (
            payload[key]
            for key in ("timestamp", "updatedAt", "updated_at")
            if key in payload and payload[key] is not None
        ),
        None,
    )
    if value is None:
        return None
    if isinstance(value, bool):
        raise CaptureValidationError("source timestamp must be a UTC time")
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise CaptureValidationError("source timestamp is out of range") from exc
    return parse_utc(value, field="source timestamp")


def _book_levels(value: Any, *, descending: bool) -> list[list[float]]:
    if not isinstance(value, list) or not value:
        raise CaptureValidationError("CLOB book sides must be non-empty arrays")
    levels: list[list[float]] = []
    for item in value:
        if isinstance(item, dict):
            price, size = item.get("price"), item.get("size")
        elif isinstance(item, list) and len(item) == 2:
            price, size = item
        else:
            raise CaptureValidationError("CLOB book levels must contain price and size")
        try:
            parsed_price = float(str(price))
            parsed_size = float(str(size))
        except (TypeError, ValueError) as exc:
            raise CaptureValidationError("CLOB book price and size must be numeric") from exc
        if not math.isfinite(parsed_price) or not 0.0 <= parsed_price <= 1.0:
            raise CaptureValidationError("CLOB book prices must be finite probabilities")
        if not math.isfinite(parsed_size) or parsed_size <= 0.0:
            raise CaptureValidationError("CLOB book sizes must be finite and positive")
        levels.append([parsed_price, parsed_size])
    return sorted(levels, key=lambda level: level[0], reverse=descending)
