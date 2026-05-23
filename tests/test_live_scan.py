"""Tests for the packaged live Polymarket scanner.

The payloads below are test fixtures shaped like public Polymarket Gamma and
CLOB responses. They are not product defaults and are never used by the scanner
outside these tests.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from autopredict.live_scan import (
    EventScanReport,
    LivePolymarketScanner,
    MarketScanReport,
    ObservedMarket,
    OrderBookSnapshot,
    format_event_scan,
    reports_to_json,
)


TEST_FIXTURE_GAMMA_MARKET = {
    "conditionId": "0xmarket1",
    "question": "Will BTC trade above $150k by December 31, 2026?",
    "outcomes": '["Yes", "No"]',
    "outcomePrices": '["0.42", "0.58"]',
    "clobTokenIds": '["yes-token-1", "no-token-1"]',
    "volume24hr": "125000.50",
    "volume": "2750000.25",
    "liquidity": "50000.0",
    "endDate": "2026-12-31T23:59:59Z",
    "active": True,
    "closed": False,
    "groupItemTitle": "crypto",
    "slug": "btc-above-150k-2026",
}

TEST_FIXTURE_SECOND_GAMMA_MARKET = {
    "conditionId": "0xmarket2",
    "question": "Will ETH trade above $8k by December 31, 2026?",
    "outcomes": ["Yes", "No"],
    "outcomePrices": ["0.31", "0.69"],
    "clobTokenIds": ["yes-token-2", "no-token-2"],
    "volume24hr": "2000",
    "liquidity": "1500",
    "endDate": "2026-12-31T23:59:59Z",
    "active": True,
    "closed": False,
    "groupItemTitle": "crypto",
    "slug": "eth-above-8k-2026",
}

TEST_FIXTURE_CLOB_BOOK = {
    "bids": [
        {"price": "0.41", "size": "500.0"},
        {"price": "0.40", "size": "750.0"},
    ],
    "asks": [
        {"price": "0.43", "size": "480.0"},
        {"price": "0.44", "size": "600.0"},
    ],
}

TEST_FIXTURE_EVENT = {
    "id": "event-1",
    "title": "2026 Crypto price milestones",
    "slug": "2026-crypto-price-milestones",
    "markets": [
        TEST_FIXTURE_GAMMA_MARKET,
        {
            **TEST_FIXTURE_SECOND_GAMMA_MARKET,
            "conditionId": "0xmarket3",
            "question": "Will SOL trade above $500 by December 31, 2026?",
            "outcomePrices": '["0.53", "0.47"]',
            "slug": "sol-above-500-2026",
        },
    ],
}


class FakePolymarketClient:
    def __init__(
        self,
        *,
        market_pages: list[list[dict[str, Any]]] | None = None,
        event_pages: list[list[dict[str, Any]]] | None = None,
        books: dict[str, dict[str, Any]] | None = None,
        failing_books: set[str] | None = None,
    ) -> None:
        self.market_pages = market_pages or []
        self.event_pages = event_pages or []
        self.books = books or {}
        self.failing_books = failing_books or set()
        self.book_requests: list[str] = []

    def fetch_markets_page(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        del limit
        page_index = 0 if offset == 0 else 1
        return self.market_pages[page_index] if page_index < len(self.market_pages) else []

    def fetch_events_page(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        del limit
        page_index = 0 if offset == 0 else 1
        return self.event_pages[page_index] if page_index < len(self.event_pages) else []

    def fetch_order_book(self, token_id: str):
        self.book_requests.append(token_id)
        if token_id in self.failing_books:
            raise RuntimeError("fixture CLOB outage")
        return OrderBookSnapshot.from_raw(token_id, self.books[token_id])


def test_observed_market_parses_live_shaped_gamma_without_default_probability() -> None:
    market = ObservedMarket.from_gamma(TEST_FIXTURE_GAMMA_MARKET)

    assert market.condition_id == "0xmarket1"
    assert market.market_prob == pytest.approx(0.42)
    assert market.yes_token_id == "yes-token-1"
    assert market.no_token_id == "no-token-1"
    assert market.volume_24h == pytest.approx(125000.50)
    assert market.volume_total == pytest.approx(2750000.25)

    missing_price = ObservedMarket.from_gamma(
        {
            **TEST_FIXTURE_GAMMA_MARKET,
            "conditionId": "0xmissingprice",
            "outcomePrices": [],
        }
    )
    assert missing_price.market_prob is None


def test_scan_markets_uses_gamma_prices_and_real_clob_book_levels() -> None:
    client = FakePolymarketClient(
        market_pages=[[TEST_FIXTURE_GAMMA_MARKET, TEST_FIXTURE_SECOND_GAMMA_MARKET]],
        books={"yes-token-1": TEST_FIXTURE_CLOB_BOOK, "yes-token-2": {"bids": [], "asks": []}},
    )
    scanner = LivePolymarketScanner(client=client)

    reports = scanner.scan_markets(limit=2, top=1, min_liquidity=1000, category="crypto")

    assert len(reports) == 1
    report = reports[0]
    assert isinstance(report, MarketScanReport)
    assert report.condition_id == "0xmarket1"
    assert report.market_prob == pytest.approx(0.42)
    assert report.best_bid == pytest.approx(0.41)
    assert report.best_ask == pytest.approx(0.43)
    assert report.bid_depth == pytest.approx(1250.0)
    assert report.ask_depth == pytest.approx(1080.0)
    assert report.book_source == "clob"
    assert client.book_requests == ["yes-token-1"]


def test_scan_markets_keeps_book_fields_missing_when_clob_unavailable() -> None:
    client = FakePolymarketClient(
        market_pages=[[TEST_FIXTURE_GAMMA_MARKET]],
        failing_books={"yes-token-1"},
    )
    scanner = LivePolymarketScanner(client=client)

    report = scanner.scan_markets(limit=1, top=1)[0]

    assert report.market_prob == pytest.approx(0.42)
    assert report.best_bid is None
    assert report.best_ask is None
    assert report.spread is None
    assert report.bid_depth is None
    assert report.ask_depth is None
    assert report.book_levels == 0
    assert report.book_source == "unavailable"
    assert "fixture CLOB outage" in str(report.book_error)


def test_scan_events_reports_observed_sibling_sum_without_normalized_prices() -> None:
    client = FakePolymarketClient(event_pages=[[TEST_FIXTURE_EVENT]])
    scanner = LivePolymarketScanner(client=client)

    reports = scanner.scan_events(limit=1, top=1, tolerance=0.02)

    assert len(reports) == 1
    report = reports[0]
    assert isinstance(report, EventScanReport)
    assert report.market_count == 2
    assert report.priced_market_count == 2
    assert report.observed_probability_sum == pytest.approx(0.95)
    assert report.deviation_from_one == pytest.approx(-0.05)
    assert report.status == "observed_under_one"
    assert "fair" not in report.to_dict()
    assert "alpha" not in report.to_dict()


def test_event_formatter_avoids_fair_language() -> None:
    report = EventScanReport.from_event(
        event=LivePolymarketScanner(
            client=FakePolymarketClient(event_pages=[[TEST_FIXTURE_EVENT]])
        )._fetch_events(limit=1)[0],
        tolerance=0.02,
    )

    rendered = format_event_scan([report])

    assert "observed_yes_sum=0.950" in rendered
    assert "fair" not in rendered.lower()
    assert "alpha" not in rendered.lower()


def test_json_output_contains_observed_keys_only() -> None:
    client = FakePolymarketClient(
        market_pages=[[TEST_FIXTURE_GAMMA_MARKET]],
        books={"yes-token-1": TEST_FIXTURE_CLOB_BOOK},
    )
    report = LivePolymarketScanner(client=client).scan_markets(limit=1, top=1)[0]

    payload = json.loads(reports_to_json([report]))

    assert payload[0]["market_prob"] == pytest.approx(0.42)
    assert payload[0]["best_bid"] == pytest.approx(0.41)
    assert "fair_prob" not in payload[0]
    assert "alpha" not in payload[0]
