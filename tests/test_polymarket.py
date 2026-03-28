"""Tests for the Polymarket adapter.

Tests the adapter's parsing, rate limiting, error handling, and bridge to
agent.MarketState — all without hitting the real Polymarket API.
"""

from __future__ import annotations

import json
import time
from unittest.mock import patch, MagicMock

import pytest

from autopredict.markets.polymarket import (
    PolymarketAdapter,
    PolymarketMarket,
    PolymarketEvent,
    _RateLimiter,
    _http_get,
)


# ---------------------------------------------------------------------------
# Fixtures: realistic Gamma API responses
# ---------------------------------------------------------------------------

SAMPLE_GAMMA_MARKET = {
    "conditionId": "0xabc123",
    "question": "Will BTC hit $150k by end of 2026?",
    "clobTokenIds": ["token-yes-123", "token-no-456"],
    "outcomePrices": ["0.42", "0.58"],
    "bestBid": "0.41",
    "bestAsk": "0.43",
    "volume24hr": "125000.50",
    "liquidity": "50000.0",
    "endDate": "2026-12-31T23:59:59Z",
    "active": True,
    "closed": False,
    "groupItemTitle": "Crypto",
    "slug": "will-btc-hit-150k",
    "negRisk": False,
    "minimumTickSize": "0.01",
}

SAMPLE_GAMMA_EVENT = {
    "id": "event-001",
    "title": "2026 Crypto Predictions",
    "slug": "2026-crypto-predictions",
    "markets": [SAMPLE_GAMMA_MARKET],
}

SAMPLE_CLOB_BOOK = {
    "bids": [
        {"price": "0.41", "size": "500.0"},
        {"price": "0.40", "size": "750.0"},
        {"price": "0.39", "size": "1000.0"},
    ],
    "asks": [
        {"price": "0.43", "size": "480.0"},
        {"price": "0.44", "size": "600.0"},
        {"price": "0.45", "size": "800.0"},
    ],
}


# ---------------------------------------------------------------------------
# Rate limiter tests
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_first_request_immediate(self):
        limiter = _RateLimiter(max_per_minute=60)
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # should be near-instant

    def test_backoff_on_throttle(self):
        limiter = _RateLimiter(max_per_minute=6000, backoff_base=0.01, backoff_factor=2.0)
        limiter.record_throttle()
        limiter.record_throttle()
        # After 2 throttles, backoff = 0.01 * 2^2 = 0.04
        # Just verify it doesn't error
        limiter.wait()

    def test_success_resets_backoff(self):
        limiter = _RateLimiter(max_per_minute=6000, backoff_base=0.01)
        limiter.record_throttle()
        limiter.record_throttle()
        limiter.record_success()
        assert limiter._consecutive_throttles == 0


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------

class TestGammaMarketParsing:
    def setup_method(self):
        self.adapter = PolymarketAdapter()

    def test_parse_basic_fields(self):
        market = self.adapter._parse_gamma_market(SAMPLE_GAMMA_MARKET)
        assert market.condition_id == "0xabc123"
        assert market.question == "Will BTC hit $150k by end of 2026?"
        assert market.token_id_yes == "token-yes-123"
        assert market.token_id_no == "token-no-456"
        assert market.active is True
        assert market.closed is False

    def test_parse_probability(self):
        market = self.adapter._parse_gamma_market(SAMPLE_GAMMA_MARKET)
        assert abs(market.market_prob - 0.42) < 0.001

    def test_parse_bid_ask(self):
        market = self.adapter._parse_gamma_market(SAMPLE_GAMMA_MARKET)
        assert abs(market.best_bid - 0.41) < 0.001
        assert abs(market.best_ask - 0.43) < 0.001
        assert market.spread > 0

    def test_parse_volume_liquidity(self):
        market = self.adapter._parse_gamma_market(SAMPLE_GAMMA_MARKET)
        assert market.volume_24h == 125000.50
        assert market.liquidity == 50000.0

    def test_parse_metadata(self):
        market = self.adapter._parse_gamma_market(SAMPLE_GAMMA_MARKET)
        assert market.metadata["neg_risk"] is False
        assert market.metadata["tick_size"] == "0.01"
        assert market.metadata["slug"] == "will-btc-hit-150k"

    def test_clamps_probability(self):
        raw = {**SAMPLE_GAMMA_MARKET, "outcomePrices": ["0.0", "1.0"]}
        market = self.adapter._parse_gamma_market(raw)
        assert market.market_prob >= 0.001
        assert market.market_prob <= 0.999

    def test_missing_clob_token_ids(self):
        raw = {**SAMPLE_GAMMA_MARKET, "clobTokenIds": []}
        market = self.adapter._parse_gamma_market(raw)
        assert market.token_id_yes == ""
        assert market.token_id_no == ""

    def test_fallback_price_when_no_outcome_prices(self):
        raw = {**SAMPLE_GAMMA_MARKET, "outcomePrices": []}
        raw["lastTradePrice"] = 0.55
        market = self.adapter._parse_gamma_market(raw)
        assert abs(market.market_prob - 0.55) < 0.001

    def test_missing_optional_fields_use_defaults(self):
        minimal = {"conditionId": "0xmin"}
        market = self.adapter._parse_gamma_market(minimal)
        assert market.condition_id == "0xmin"
        assert market.question == ""
        assert market.volume_24h == 0.0


class TestGammaEventParsing:
    def setup_method(self):
        self.adapter = PolymarketAdapter()

    def test_parse_event(self):
        event = self.adapter._parse_gamma_event(SAMPLE_GAMMA_EVENT)
        assert event.event_id == "event-001"
        assert event.title == "2026 Crypto Predictions"
        assert len(event.markets) == 1
        assert event.markets[0].condition_id == "0xabc123"

    def test_skips_malformed_markets_in_event(self):
        raw = {
            **SAMPLE_GAMMA_EVENT,
            "markets": [SAMPLE_GAMMA_MARKET, {"bad": "data"}],
        }
        # The bad market has no conditionId — should be silently skipped
        event = self.adapter._parse_gamma_event(raw)
        assert len(event.markets) == 1


# ---------------------------------------------------------------------------
# Order book parsing tests
# ---------------------------------------------------------------------------

class TestOrderBookParsing:
    def setup_method(self):
        self.adapter = PolymarketAdapter()

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_order_book(self, mock_get):
        mock_get.return_value = SAMPLE_CLOB_BOOK
        book = self.adapter.get_order_book("token-yes-123")

        assert len(book["bids"]) == 3
        assert len(book["asks"]) == 3
        # Bids sorted descending
        assert book["bids"][0][0] == 0.41
        assert book["bids"][1][0] == 0.40
        # Asks sorted ascending
        assert book["asks"][0][0] == 0.43
        assert book["asks"][1][0] == 0.44

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_order_book_empty(self, mock_get):
        mock_get.return_value = {"bids": [], "asks": []}
        book = self.adapter.get_order_book("token-yes-123")
        assert book["bids"] == []
        assert book["asks"] == []

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_order_book_filters_invalid(self, mock_get):
        mock_get.return_value = {
            "bids": [{"price": "0", "size": "100"}, {"price": "0.50", "size": "0"}],
            "asks": [{"price": "0.55", "size": "200"}],
        }
        book = self.adapter.get_order_book("token")
        assert len(book["bids"]) == 0  # both filtered out
        assert len(book["asks"]) == 1


# ---------------------------------------------------------------------------
# Bridge to agent.MarketState tests
# ---------------------------------------------------------------------------

class TestAgentBridge:
    def setup_method(self):
        self.adapter = PolymarketAdapter()
        self.market = self.adapter._parse_gamma_market(SAMPLE_GAMMA_MARKET)

    def test_to_agent_market_state_basic(self):
        state = self.adapter.to_agent_market_state(self.market, fair_prob=0.50)
        assert state.market_id == "0xabc123"
        assert abs(state.market_prob - 0.42) < 0.001
        assert abs(state.fair_prob - 0.50) < 0.001
        assert state.time_to_expiry_hours > 0
        assert state.order_book is not None

    def test_to_agent_market_state_default_fair_prob(self):
        # Without fair_prob, defaults to market_prob (zero edge)
        state = self.adapter.to_agent_market_state(self.market)
        assert abs(state.fair_prob - state.market_prob) < 0.001

    def test_to_agent_market_state_metadata(self):
        state = self.adapter.to_agent_market_state(self.market, fair_prob=0.50)
        assert state.metadata["category"] == "crypto"
        assert state.metadata["question"] == "Will BTC hit $150k by end of 2026?"
        assert state.metadata["token_id_yes"] == "token-yes-123"

    def test_to_agent_market_state_order_book(self):
        state = self.adapter.to_agent_market_state(self.market, fair_prob=0.50)
        book = state.order_book
        assert book.market_id == "0xabc123"
        # Gamma provides approximate book from liquidity
        assert book.get_total_depth() > 0

    def test_agent_can_evaluate(self):
        """End-to-end: Polymarket data -> agent evaluation."""
        from autopredict.agent import AutoPredictAgent, AgentConfig

        state = self.adapter.to_agent_market_state(self.market, fair_prob=0.50)
        # Use a config with wider spread tolerance to match the Gamma
        # placeholder book (spread_pct ~4.8% from bestBid/bestAsk)
        config = AgentConfig(max_spread_pct=0.06)
        agent = AutoPredictAgent(config)
        proposal = agent.evaluate_market(state, bankroll=1000.0)
        # With edge of 0.08 (0.50 - 0.42) and default min_edge of 0.05,
        # the agent should propose a trade
        assert proposal is not None
        assert proposal.side == "buy"
        assert proposal.size > 0


# ---------------------------------------------------------------------------
# Credential handling tests
# ---------------------------------------------------------------------------

class TestCredentials:
    def test_no_credentials_by_default(self):
        adapter = PolymarketAdapter()
        assert adapter.has_clob_credentials is False

    def test_credentials_from_env(self):
        env = {
            "POLYMARKET_API_KEY": "test-key",
            "POLYMARKET_API_SECRET": "test-secret",
            "POLYMARKET_PASSPHRASE": "test-pass",
        }
        with patch.dict("os.environ", env):
            adapter = PolymarketAdapter()
            assert adapter.has_clob_credentials is True

    def test_ensure_clob_client_raises_without_creds(self):
        adapter = PolymarketAdapter()
        with pytest.raises(RuntimeError, match="CLOB credentials required"):
            adapter._ensure_clob_client()

    def test_get_balance_raises_without_creds(self):
        adapter = PolymarketAdapter()
        with pytest.raises(RuntimeError, match="CLOB credentials required"):
            adapter.get_balance()

    def test_place_order_raises_without_creds(self):
        adapter = PolymarketAdapter()
        with pytest.raises(RuntimeError, match="CLOB credentials required"):
            adapter.place_order(
                token_id="test", side="BUY", size=10.0, price=0.50
            )


# ---------------------------------------------------------------------------
# API fetch tests (mocked HTTP)
# ---------------------------------------------------------------------------

class TestAPIFetching:
    def setup_method(self):
        self.adapter = PolymarketAdapter()

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_active_markets(self, mock_get):
        mock_get.return_value = [SAMPLE_GAMMA_MARKET]
        markets = self.adapter.get_active_markets(limit=10)
        assert len(markets) == 1
        assert markets[0].condition_id == "0xabc123"

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_active_markets_filters_by_liquidity(self, mock_get):
        mock_get.return_value = [SAMPLE_GAMMA_MARKET]
        markets = self.adapter.get_active_markets(min_liquidity=999999.0)
        assert len(markets) == 0  # liquidity is 50k, filter requires 999k

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_active_markets_filters_by_category(self, mock_get):
        mock_get.return_value = [SAMPLE_GAMMA_MARKET]
        # Correct category
        markets = self.adapter.get_active_markets(category="crypto")
        assert len(markets) == 1
        # Wrong category
        markets = self.adapter.get_active_markets(category="sports")
        assert len(markets) == 0

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_active_markets_skips_malformed(self, mock_get):
        mock_get.return_value = [SAMPLE_GAMMA_MARKET, {"bad": "data"}]
        markets = self.adapter.get_active_markets()
        assert len(markets) == 1  # malformed entry silently skipped

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_active_markets_unexpected_response_type(self, mock_get):
        mock_get.return_value = {"error": "not a list"}
        markets = self.adapter.get_active_markets()
        assert markets == []

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_market_success(self, mock_get):
        mock_get.return_value = SAMPLE_GAMMA_MARKET
        market = self.adapter.get_market("0xabc123")
        assert market is not None
        assert market.condition_id == "0xabc123"

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_market_not_found(self, mock_get):
        mock_get.side_effect = ConnectionError("Failed")
        market = self.adapter.get_market("0xnonexistent")
        assert market is None

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_events(self, mock_get):
        mock_get.return_value = [SAMPLE_GAMMA_EVENT]
        events = self.adapter.get_events(limit=5)
        assert len(events) == 1
        assert events[0].title == "2026 Crypto Predictions"
        assert len(events[0].markets) == 1

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_midpoint(self, mock_get):
        mock_get.return_value = {"mid": "0.42"}
        mid = self.adapter.get_midpoint("token-yes-123")
        assert mid is not None
        assert abs(mid - 0.42) < 0.001

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_midpoint_failure(self, mock_get):
        mock_get.side_effect = ConnectionError("Failed")
        mid = self.adapter.get_midpoint("token-yes-123")
        assert mid is None

    @patch("autopredict.markets.polymarket._http_get")
    def test_get_price(self, mock_get):
        mock_get.return_value = {"price": "0.41"}
        price = self.adapter.get_price("token-yes-123", side="buy")
        assert price is not None
        assert abs(price - 0.41) < 0.001
