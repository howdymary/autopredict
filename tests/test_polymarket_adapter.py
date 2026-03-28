"""Tests for the real Polymarket adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from autopredict.core.types import Order
from autopredict.markets.polymarket import PolymarketAdapter


RAW_MARKET = {
    "id": "540816",
    "question": "Russia-Ukraine Ceasefire before GTA VI?",
    "slug": "russia-ukraine-ceasefire-before-gta-vi-554",
    "conditionId": "0x9c1a953fe92c8357f1b646ba25d983aa83e90c525992db14fb726fa895cb5763",
    "outcomes": '["Yes", "No"]',
    "outcomePrices": '["0.54", "0.46"]',
    "clobTokenIds": '["yes-token", "no-token"]',
    "endDate": "2026-07-31T12:00:00Z",
    "volume": "1403713.15",
    "liquidity": "122377.89",
    "active": True,
    "closed": False,
    "acceptingOrders": True,
    "negRisk": False,
    "orderMinSize": 5,
    "orderPriceMinTickSize": 0.01,
}

YES_BOOK = {
    "bids": [{"price": "0.53", "size": "100.0"}],
    "asks": [{"price": "0.55", "size": "125.0"}],
    "tick_size": "0.01",
    "min_order_size": "5",
}

NO_BOOK = {
    "bids": [{"price": "0.45", "size": "90.0"}],
    "asks": [{"price": "0.47", "size": "135.0"}],
    "tick_size": "0.01",
    "min_order_size": "5",
}


@dataclass
class FakeOrderArgs:
    token_id: str
    price: float
    size: float
    side: str


@dataclass
class FakePartialCreateOrderOptions:
    tick_size: str
    neg_risk: bool


class FakeOrderType:
    GTC = "GTC"
    FAK = "FAK"


class FakeTradingClient:
    OrderArgs = FakeOrderArgs
    OrderType = FakeOrderType
    PartialCreateOrderOptions = FakePartialCreateOrderOptions

    def __init__(self):
        self.created_args = None
        self.created_options = None
        self.posted_order_type = None

    def create_order(self, order_args, options=None):
        self.created_args = order_args
        self.created_options = options
        return {"signed": True, "token_id": order_args.token_id}

    def post_order(self, signed_order, order_type):
        self.posted_order_type = order_type
        return {"success": True, "status": "live", "orderID": "order-123"}


def test_get_markets_uses_live_shaped_market_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = PolymarketAdapter()

    def fake_request(method, url, params=None, payload=None):
        del method, params, payload
        if url.endswith("/markets"):
            return [RAW_MARKET]
        if url.endswith("/book"):
            return YES_BOOK
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(adapter, "_request_json", fake_request)

    markets = adapter.get_markets({"limit": 1})

    assert len(markets) == 1
    market = markets[0]
    assert market.market_id == f"polymarket-{RAW_MARKET['conditionId']}"
    assert market.question == RAW_MARKET["question"]
    assert market.market_prob == 0.54
    assert market.best_bid == 0.53
    assert market.best_ask == 0.55
    assert market.metadata["yes_token_id"] == "yes-token"
    assert market.metadata["no_token_id"] == "no-token"
    assert market.category.value == "politics"


def test_validate_credentials_respects_dry_run_placeholders() -> None:
    adapter = PolymarketAdapter(api_key="__AUTOPREDICT_MISSING_ENV__:POLYMARKET_API_KEY")
    adapter.validate_credentials(require_trading=False)
    with pytest.raises(ValueError, match="POLYMARKET_API_KEY"):
        adapter.validate_credentials(require_trading=True)


def test_place_order_maps_bearish_order_to_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = PolymarketAdapter(
        api_key="key",
        api_secret="secret",
        api_passphrase="passphrase",
        private_key="private",
        funder="0xfunder",
        trading_client=FakeTradingClient(),
    )

    monkeypatch.setattr(adapter, "_find_raw_market", lambda market_id: RAW_MARKET)
    monkeypatch.setattr(
        adapter,
        "_get_order_book",
        lambda token_id: YES_BOOK if token_id == "yes-token" else NO_BOOK,
    )

    order = Order(
        market_id=f"polymarket-{RAW_MARKET['conditionId']}",
        side="sell",
        order_type="limit",
        size=10.0,
        limit_price=0.42,
    )
    report = adapter.place_order(order)

    client = adapter._trading_client
    assert client.created_args.token_id == "no-token"
    assert client.created_args.side == "BUY"
    assert client.created_args.price == pytest.approx(0.58)
    assert client.posted_order_type == "GTC"
    assert report.metadata["outcome"] == "NO"
    assert report.metadata["submitted_price"] == pytest.approx(0.58)
