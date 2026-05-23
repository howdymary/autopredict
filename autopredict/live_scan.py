"""Live Polymarket scanner built only from public Polymarket data.

The scanner is intentionally read-only. It reports observed Gamma market prices
and observed CLOB book levels, but it does not generate forecasts, trading
recommendations, or synthetic replacement quotes when public data is missing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import sys
import time
from typing import Any, Sequence

import requests


DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"
DEFAULT_CLOB_URL = "https://clob.polymarket.com"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3


@dataclass(frozen=True)
class OrderBookLevel:
    """One observed CLOB order book level."""

    price: float
    size: float

    @classmethod
    def from_raw(cls, raw: Any) -> "OrderBookLevel | None":
        if isinstance(raw, dict):
            price = _coerce_probability(raw.get("price"))
            size = _coerce_positive_float(raw.get("size"))
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            price = _coerce_probability(raw[0])
            size = _coerce_positive_float(raw[1])
        else:
            return None

        if price is None or size is None:
            return None
        return cls(price=price, size=size)

    def to_dict(self) -> dict[str, float]:
        return {"price": self.price, "size": self.size}


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Observed order book for one Polymarket CLOB token."""

    token_id: str
    bids: tuple[OrderBookLevel, ...] = ()
    asks: tuple[OrderBookLevel, ...] = ()

    @classmethod
    def from_raw(cls, token_id: str, raw: Any) -> "OrderBookSnapshot":
        if not isinstance(raw, dict):
            return cls(token_id=token_id)

        bids = tuple(
            sorted(
                (
                    level
                    for level in (OrderBookLevel.from_raw(item) for item in raw.get("bids", ()))
                    if level
                ),
                key=lambda level: level.price,
                reverse=True,
            )
        )
        asks = tuple(
            sorted(
                (
                    level
                    for level in (OrderBookLevel.from_raw(item) for item in raw.get("asks", ()))
                    if level
                ),
                key=lambda level: level.price,
            )
        )
        return cls(token_id=token_id, bids=bids, asks=asks)

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def bid_depth(self) -> float:
        return sum(level.size for level in self.bids)

    @property
    def ask_depth(self) -> float:
        return sum(level.size for level in self.asks)

    @property
    def level_count(self) -> int:
        return len(self.bids) + len(self.asks)


@dataclass(frozen=True)
class ObservedMarket:
    """A Polymarket Gamma market with no generated replacement values."""

    condition_id: str
    question: str
    market_prob: float | None
    yes_token_id: str | None
    no_token_id: str | None
    volume_24h: float | None
    volume_total: float | None
    liquidity: float | None
    end_date: datetime | None
    active: bool | None
    closed: bool | None
    category: str | None
    slug: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_gamma(cls, raw: dict[str, Any]) -> "ObservedMarket":
        if not isinstance(raw, dict):
            raise ValueError("Gamma market payload must be a dictionary")

        condition_id = str(raw.get("conditionId") or raw.get("condition_id") or "").strip()
        if not condition_id:
            raise ValueError("Gamma market payload is missing conditionId")

        outcomes = [str(value).strip().lower() for value in _parse_json_list(raw.get("outcomes"))]
        yes_index = outcomes.index("yes") if "yes" in outcomes else None
        no_index = outcomes.index("no") if "no" in outcomes else None
        token_ids = _parse_json_list(raw.get("clobTokenIds"))
        prices = _parse_json_list(raw.get("outcomePrices"))

        yes_token_id = _list_str_at(token_ids, yes_index) if yes_index is not None else None
        no_token_id = _list_str_at(token_ids, no_index) if no_index is not None else None
        market_prob = (
            _coerce_probability(_list_at(prices, yes_index)) if yes_index is not None else None
        )

        return cls(
            condition_id=condition_id,
            question=str(raw.get("question") or "").strip(),
            market_prob=market_prob,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            volume_24h=_first_float(raw, ("volume24hr", "volume24h", "volume24hrClob")),
            volume_total=_first_float(raw, ("volume", "volumeClob")),
            liquidity=_first_float(raw, ("liquidity", "liquidityClob")),
            end_date=_parse_timestamp(raw.get("endDate") or raw.get("endDateIso")),
            active=_coerce_optional_bool(raw.get("active")),
            closed=_coerce_optional_bool(raw.get("closed")),
            category=_first_text(raw, ("groupItemTitle", "category")),
            slug=_first_text(raw, ("slug",)),
            raw=dict(raw),
        )

    @property
    def activity_volume(self) -> float:
        return self.volume_24h if self.volume_24h is not None else self.volume_total or 0.0

    @property
    def hours_to_expiry(self) -> float | None:
        if self.end_date is None:
            return None
        now = datetime.now(self.end_date.tzinfo or timezone.utc)
        return max((self.end_date - now).total_seconds() / 3600.0, 0.0)


@dataclass(frozen=True)
class ObservedEvent:
    """A Polymarket Gamma event and its child markets."""

    event_id: str
    title: str
    slug: str | None
    markets: tuple[ObservedMarket, ...]

    @classmethod
    def from_gamma(cls, raw: dict[str, Any]) -> "ObservedEvent":
        if not isinstance(raw, dict):
            raise ValueError("Gamma event payload must be a dictionary")

        markets = []
        for market_payload in raw.get("markets", ()) or ():
            try:
                markets.append(ObservedMarket.from_gamma(market_payload))
            except (TypeError, ValueError):
                continue

        return cls(
            event_id=str(raw.get("id") or raw.get("eventId") or "").strip(),
            title=str(raw.get("title") or "").strip(),
            slug=_first_text(raw, ("slug",)),
            markets=tuple(markets),
        )


@dataclass(frozen=True)
class MarketScanReport:
    """CLI-friendly market report made from observed public data."""

    condition_id: str
    question: str
    market_prob: float | None
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    spread_pct: float | None
    bid_depth: float | None
    ask_depth: float | None
    depth_imbalance: float | None
    liquidity: float | None
    volume_24h: float | None
    volume_total: float | None
    hours_to_expiry: float | None
    category: str | None
    slug: str | None
    book_levels: int
    book_source: str
    book_error: str | None = None

    @classmethod
    def from_market(
        cls,
        market: ObservedMarket,
        *,
        order_book: OrderBookSnapshot | None,
        book_source: str,
        book_error: str | None = None,
    ) -> "MarketScanReport":
        best_bid = order_book.best_bid if order_book else None
        best_ask = order_book.best_ask if order_book else None
        spread = order_book.spread if order_book else None
        mid = (best_bid + best_ask) / 2.0 if best_bid is not None and best_ask is not None else None
        bid_depth = order_book.bid_depth if order_book else None
        ask_depth = order_book.ask_depth if order_book else None
        total_depth = (bid_depth or 0.0) + (ask_depth or 0.0)

        return cls(
            condition_id=market.condition_id,
            question=market.question,
            market_prob=market.market_prob,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            spread_pct=(spread / mid if spread is not None and mid and mid > 0 else None),
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            depth_imbalance=(
                ((bid_depth or 0.0) - (ask_depth or 0.0)) / total_depth if total_depth > 0 else None
            ),
            liquidity=market.liquidity,
            volume_24h=market.volume_24h,
            volume_total=market.volume_total,
            hours_to_expiry=market.hours_to_expiry,
            category=market.category,
            slug=market.slug,
            book_levels=order_book.level_count if order_book else 0,
            book_source=book_source,
            book_error=book_error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "question": self.question,
            "market_prob": self.market_prob,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "spread": self.spread,
            "spread_pct": self.spread_pct,
            "bid_depth": self.bid_depth,
            "ask_depth": self.ask_depth,
            "depth_imbalance": self.depth_imbalance,
            "liquidity": self.liquidity,
            "volume_24h": self.volume_24h,
            "volume_total": self.volume_total,
            "hours_to_expiry": self.hours_to_expiry,
            "category": self.category,
            "slug": self.slug,
            "book_levels": self.book_levels,
            "book_source": self.book_source,
            "book_error": self.book_error,
        }


@dataclass(frozen=True)
class EventMarketLine:
    """One observed child market inside an event scan report."""

    condition_id: str
    question: str
    market_prob: float | None
    slug: str | None

    @classmethod
    def from_market(cls, market: ObservedMarket) -> "EventMarketLine":
        return cls(
            condition_id=market.condition_id,
            question=market.question,
            market_prob=market.market_prob,
            slug=market.slug,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "question": self.question,
            "market_prob": self.market_prob,
            "slug": self.slug,
        }


@dataclass(frozen=True)
class EventScanReport:
    """Observed event-level sibling price inventory."""

    event_id: str
    title: str
    slug: str | None
    market_count: int
    priced_market_count: int
    observed_probability_sum: float | None
    status: str
    markets: tuple[EventMarketLine, ...]

    @classmethod
    def from_event(cls, event: ObservedEvent, *, tolerance: float) -> "EventScanReport":
        del tolerance
        priced = [market.market_prob for market in event.markets if market.market_prob is not None]
        prob_sum = sum(priced) if len(priced) >= 2 else None

        if prob_sum is None:
            status = "insufficient_priced_markets"
        else:
            status = "observed_sibling_prices_nonexclusive"

        return cls(
            event_id=event.event_id,
            title=event.title,
            slug=event.slug,
            market_count=len(event.markets),
            priced_market_count=len(priced),
            observed_probability_sum=prob_sum,
            status=status,
            markets=tuple(EventMarketLine.from_market(market) for market in event.markets),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "slug": self.slug,
            "market_count": self.market_count,
            "priced_market_count": self.priced_market_count,
            "observed_probability_sum": self.observed_probability_sum,
            "status": self.status,
            "markets": [market.to_dict() for market in self.markets],
        }


class PublicPolymarketClient:
    """Read-only client for Polymarket Gamma and CLOB public endpoints."""

    def __init__(
        self,
        *,
        gamma_url: str = DEFAULT_GAMMA_URL,
        clob_url: str = DEFAULT_CLOB_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        session: requests.Session | None = None,
    ) -> None:
        self.gamma_url = gamma_url.rstrip("/")
        self.clob_url = clob_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.session = session or requests.Session()
        self.session.headers.setdefault("Accept", "application/json")
        self.session.headers.setdefault("User-Agent", "autopredict-live-scan/0.1")

    def fetch_markets_page(
        self,
        *,
        limit: int,
        offset: int,
        active: bool = True,
        closed: bool = False,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            "GET",
            f"{self.gamma_url}/markets",
            params={
                "limit": int(limit),
                "offset": int(offset),
                "active": str(active).lower(),
                "closed": str(closed).lower(),
            },
        )
        return payload if isinstance(payload, list) else []

    def fetch_events_page(
        self,
        *,
        limit: int,
        offset: int,
        active: bool = True,
        closed: bool = False,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            "GET",
            f"{self.gamma_url}/events",
            params={
                "limit": int(limit),
                "offset": int(offset),
                "active": str(active).lower(),
                "closed": str(closed).lower(),
            },
        )
        return payload if isinstance(payload, list) else []

    def fetch_order_book(self, token_id: str) -> OrderBookSnapshot:
        payload = self._request_json(
            "GET",
            f"{self.clob_url}/book",
            params={"token_id": token_id},
        )
        return OrderBookSnapshot.from_raw(token_id, payload)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        last_error: Exception | None = None
        attempts = max(self.max_retries, 1)
        for attempt in range(attempts):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(
                        f"Polymarket request to {url} failed with status {response.status_code}",
                        response=response,
                    )
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == attempts - 1:
                    break
                time.sleep(0.25 * (2**attempt))
        raise RuntimeError(
            f"Polymarket public request failed for {url}: {last_error}"
        ) from last_error


class LivePolymarketScanner:
    """Scanner service that returns typed reports for CLI or library callers."""

    def __init__(self, client: PublicPolymarketClient | None = None) -> None:
        self.client = client or PublicPolymarketClient()

    def scan_markets(
        self,
        *,
        limit: int = 100,
        top: int = 15,
        min_liquidity: float = 0.0,
        min_volume: float = 0.0,
        category: str | None = None,
        include_books: bool = True,
    ) -> list[MarketScanReport]:
        markets = self._fetch_markets(limit=limit)
        candidates = [
            market
            for market in markets
            if _passes_market_filters(
                market,
                category=category,
                min_liquidity=min_liquidity,
                min_volume=min_volume,
            )
        ]
        candidates.sort(key=lambda market: market.activity_volume, reverse=True)

        reports: list[MarketScanReport] = []
        for market in candidates[: max(top, 0)]:
            order_book = None
            book_source = "not_requested"
            book_error = None
            if include_books:
                if not market.yes_token_id:
                    book_source = "missing_yes_token"
                else:
                    try:
                        order_book = self.client.fetch_order_book(market.yes_token_id)
                        book_source = "clob" if order_book.level_count else "clob_empty"
                    except RuntimeError as exc:
                        book_source = "unavailable"
                        book_error = str(exc)
            reports.append(
                MarketScanReport.from_market(
                    market,
                    order_book=order_book,
                    book_source=book_source,
                    book_error=book_error,
                )
            )
        return reports

    def scan_events(
        self,
        *,
        limit: int = 50,
        top: int = 15,
        min_markets: int = 2,
        tolerance: float = 0.02,
    ) -> list[EventScanReport]:
        events = self._fetch_events(limit=limit)
        reports = [
            EventScanReport.from_event(event, tolerance=tolerance)
            for event in events
            if len(event.markets) >= min_markets
        ]
        reports.sort(key=_event_report_sort_key)
        return reports[: max(top, 0)]

    def _fetch_markets(self, *, limit: int) -> list[ObservedMarket]:
        raw_markets = self._fetch_pages(self.client.fetch_markets_page, limit=limit)
        markets: list[ObservedMarket] = []
        for raw in raw_markets:
            try:
                markets.append(ObservedMarket.from_gamma(raw))
            except (TypeError, ValueError):
                continue
        return markets

    def _fetch_events(self, *, limit: int) -> list[ObservedEvent]:
        raw_events = self._fetch_pages(self.client.fetch_events_page, limit=limit)
        events: list[ObservedEvent] = []
        for raw in raw_events:
            try:
                events.append(ObservedEvent.from_gamma(raw))
            except (TypeError, ValueError):
                continue
        return events

    @staticmethod
    def _fetch_pages(fetch_page: Any, *, limit: int) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        offset = 0
        page_size = min(max(limit, 0), 100) or 100
        while len(collected) < limit:
            page_limit = min(page_size, limit - len(collected))
            page = fetch_page(limit=page_limit, offset=offset)
            if not page:
                break
            collected.extend(page)
            offset += len(page)
            if len(page) < page_limit:
                break
        return collected[:limit]


def scan_markets(
    *,
    client: PublicPolymarketClient | None = None,
    limit: int = 100,
    top: int = 15,
    min_liquidity: float = 0.0,
    min_volume: float = 0.0,
    category: str | None = None,
    include_books: bool = True,
) -> list[MarketScanReport]:
    """Convenience wrapper for callers that do not need to manage a scanner."""

    return LivePolymarketScanner(client).scan_markets(
        limit=limit,
        top=top,
        min_liquidity=min_liquidity,
        min_volume=min_volume,
        category=category,
        include_books=include_books,
    )


def scan_events(
    *,
    client: PublicPolymarketClient | None = None,
    limit: int = 50,
    top: int = 15,
    min_markets: int = 2,
    tolerance: float = 0.02,
) -> list[EventScanReport]:
    """Convenience wrapper for event-level sibling price scans."""

    return LivePolymarketScanner(client).scan_events(
        limit=limit,
        top=top,
        min_markets=min_markets,
        tolerance=tolerance,
    )


def reports_to_json(reports: Sequence[MarketScanReport | EventScanReport]) -> str:
    """Serialize scan reports to JSON without adding derived estimates."""

    return json.dumps([report.to_dict() for report in reports], indent=2, sort_keys=True)


def format_market_scan(reports: Sequence[MarketScanReport], *, verbose: bool = False) -> str:
    if not reports:
        return "No active Polymarket markets matched the scan filters."

    lines = [
        (
            f"{'Question':<50} {'Price':>7} {'Bid':>7} {'Ask':>7} "
            f"{'Sprd%':>7} {'BidDepth':>10} {'AskDepth':>10} {'Vol24h':>10} {'Expiry':>8}"
        ),
        "-" * 126,
    ]
    for report in reports:
        lines.append(
            f"{_truncate(report.question, 50):<50} "
            f"{_fmt_prob(report.market_prob):>7} "
            f"{_fmt_price(report.best_bid):>7} "
            f"{_fmt_price(report.best_ask):>7} "
            f"{_fmt_percent(report.spread_pct):>7} "
            f"{_fmt_money(report.bid_depth):>10} "
            f"{_fmt_money(report.ask_depth):>10} "
            f"{_fmt_money(report.volume_24h):>10} "
            f"{_fmt_hours(report.hours_to_expiry):>8}"
        )
        if verbose:
            lines.append(
                f"    id={report.condition_id} source={report.book_source} "
                f"levels={report.book_levels} category={report.category or 'n/a'}"
            )
            if report.book_error:
                lines.append(f"    book_error={report.book_error}")
    lines.append("")
    lines.append("Data sources: Polymarket Gamma API prices and public CLOB order books.")
    return "\n".join(lines)


def format_event_scan(reports: Sequence[EventScanReport], *, verbose: bool = False) -> str:
    if not reports:
        return "No Polymarket events matched the scan filters."

    lines: list[str] = []
    for report in reports:
        lines.append(f"Event: {report.title or report.event_id or 'untitled'}")
        lines.append(
            "  "
            f"markets={report.market_count} priced={report.priced_market_count} "
            f"observed_yes_sum={_fmt_decimal(report.observed_probability_sum)} "
            f"status={report.status}"
        )
        for market in sorted(
            report.markets,
            key=lambda item: item.market_prob if item.market_prob is not None else -1.0,
            reverse=True,
        ):
            lines.append(
                f"    {_fmt_prob(market.market_prob):>7}  " f"{_truncate(market.question, 72)}"
            )
            if verbose:
                lines.append(f"      id={market.condition_id} slug={market.slug or 'n/a'}")
        lines.append("")
    lines.append(
        "Event sums are observed sibling YES prices only; they are not normalized and exclusivity is not assumed."
    )
    return "\n".join(lines).rstrip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan live public Polymarket data")
    parser.add_argument("--events", action="store_true", help="Scan event sibling price sums")
    parser.add_argument("--category", help="Filter market scan by observed category")
    parser.add_argument(
        "--min-liquidity", type=float, default=0.0, help="Minimum observed liquidity"
    )
    parser.add_argument("--min-volume", type=float, default=0.0, help="Minimum observed volume")
    parser.add_argument("--limit", type=int, default=100, help="Number of Gamma objects to inspect")
    parser.add_argument("--top", type=int, default=15, help="Number of reports to print")
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show IDs and source details")
    parser.add_argument(
        "--no-books",
        action="store_true",
        help="Skip CLOB book fetches in market scan and report Gamma prices only",
    )
    return parser


def run(args: argparse.Namespace, *, stdout: Any = None) -> int:
    output = stdout or sys.stdout
    client = PublicPolymarketClient(timeout_seconds=args.timeout)
    scanner = LivePolymarketScanner(client)
    if args.events:
        event_reports = scanner.scan_events(limit=args.limit, top=args.top)
        print(
            (
                reports_to_json(event_reports)
                if args.json
                else format_event_scan(event_reports, verbose=args.verbose)
            ),
            file=output,
        )
    else:
        market_reports = scanner.scan_markets(
            limit=args.limit,
            top=args.top,
            min_liquidity=args.min_liquidity,
            min_volume=args.min_volume,
            category=args.category,
            include_books=not args.no_books,
        )
        print(
            (
                reports_to_json(market_reports)
                if args.json
                else format_market_scan(market_reports, verbose=args.verbose)
            ),
            file=output,
        )
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    raise SystemExit(run(parser.parse_args(argv)))


def _passes_market_filters(
    market: ObservedMarket,
    *,
    category: str | None,
    min_liquidity: float,
    min_volume: float,
) -> bool:
    if category and (market.category or "").lower() != category.lower():
        return False
    if min_liquidity > 0 and (market.liquidity is None or market.liquidity < min_liquidity):
        return False
    if min_volume > 0 and market.activity_volume < min_volume:
        return False
    return True


def _event_report_sort_key(report: EventScanReport) -> tuple[int, float, str]:
    rank_by_status = {
        "observed_sibling_prices_nonexclusive": 0,
        "insufficient_priced_markets": 3,
    }
    return (
        rank_by_status.get(report.status, 9),
        -report.priced_market_count,
        report.title,
    )


def _parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else [parsed]
    return [value]


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _coerce_positive_float(value: Any) -> float | None:
    numeric = _coerce_float(value)
    return numeric if numeric is not None and numeric > 0 else None


def _coerce_probability(value: Any) -> float | None:
    numeric = _coerce_float(value)
    return numeric if numeric is not None and 0.0 <= numeric <= 1.0 else None


def _coerce_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _first_float(raw: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _coerce_float(raw.get(key))
        if value is not None:
            return value
    return None


def _first_text(raw: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _list_at(values: Sequence[Any], index: int) -> Any | None:
    return values[index] if 0 <= index < len(values) else None


def _list_str_at(values: Sequence[Any], index: int) -> str | None:
    value = _list_at(values, index)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(value: str, length: int) -> str:
    if len(value) <= length:
        return value
    if length <= 3:
        return value[:length]
    return value[: length - 3] + "..."


def _fmt_prob(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _fmt_price(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _fmt_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _fmt_signed_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1%}"


def _fmt_money(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.0f}"


def _fmt_hours(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f}h"


def _fmt_decimal(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    main()
