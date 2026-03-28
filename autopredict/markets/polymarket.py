"""Polymarket adapter for fetching market data and placing orders.

Polymarket is the largest decentralized prediction market, running on Polygon.
This adapter integrates with two APIs:

  - Gamma API (https://gamma-api.polymarket.com) — public, read-only market data
  - CLOB API (https://clob.polymarket.com) — authenticated order book + trading

Credentials are loaded exclusively from environment variables:
  POLYMARKET_API_KEY      — CLOB API key (from create_or_derive_api_creds)
  POLYMARKET_API_SECRET   — CLOB API secret
  POLYMARKET_PASSPHRASE   — CLOB API passphrase
  POLYMARKET_PK           — Wallet private key (for signing, optional)
  POLYMARKET_FUNDER       — Funder address (optional, for proxy wallets)

API Documentation: https://docs.polymarket.com/
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

# Rate limiting defaults
DEFAULT_MAX_REQUESTS_PER_MINUTE = 60
DEFAULT_BACKOFF_BASE = 1.0     # seconds
DEFAULT_BACKOFF_MAX = 30.0     # seconds
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 15           # seconds


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Token-bucket rate limiter with exponential backoff on throttle."""

    def __init__(
        self,
        max_per_minute: int = DEFAULT_MAX_REQUESTS_PER_MINUTE,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        backoff_max: float = DEFAULT_BACKOFF_MAX,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    ) -> None:
        self._interval = 60.0 / max(max_per_minute, 1)
        self._last_request: float = -(self._interval + 1.0)  # allow immediate first request
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._backoff_factor = backoff_factor
        self._consecutive_throttles = 0

    def wait(self) -> None:
        """Block until the next request is allowed."""
        now = time.monotonic()
        wait_time = self._interval - (now - self._last_request)
        if self._consecutive_throttles > 0:
            backoff = min(
                self._backoff_base * (self._backoff_factor ** self._consecutive_throttles),
                self._backoff_max,
            )
            wait_time = max(wait_time, backoff)
        if wait_time > 0:
            time.sleep(wait_time)
        self._last_request = time.monotonic()

    def record_success(self) -> None:
        self._consecutive_throttles = 0

    def record_throttle(self) -> None:
        self._consecutive_throttles += 1


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only — no requests/httpx dependency)
# ---------------------------------------------------------------------------

def _http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    rate_limiter: _RateLimiter | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict | list:
    """GET with retry + backoff.  Returns parsed JSON."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        if rate_limiter is not None:
            rate_limiter.wait()
        default_headers = {"User-Agent": "autopredict/0.1", "Accept": "application/json"}
        if headers:
            default_headers.update(headers)
        req = urllib.request.Request(url, headers=default_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode())
                if rate_limiter is not None:
                    rate_limiter.record_success()
                return body
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code == 429 or exc.code >= 500:
                logger.warning("HTTP %d on %s (attempt %d)", exc.code, url, attempt + 1)
                if rate_limiter is not None:
                    rate_limiter.record_throttle()
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            logger.warning("Network error on %s (attempt %d): %s", url, attempt + 1, exc)
            if rate_limiter is not None:
                rate_limiter.record_throttle()
            continue
    raise ConnectionError(f"Failed after {max_retries + 1} attempts: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Data classes for adapter results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PolymarketEvent:
    """A Polymarket event (may contain multiple binary markets)."""
    event_id: str
    title: str
    slug: str
    markets: list[PolymarketMarket]


@dataclass(frozen=True)
class PolymarketMarket:
    """A single Polymarket binary market (one YES/NO outcome)."""
    condition_id: str
    question: str
    token_id_yes: str
    token_id_no: str
    market_prob: float
    volume_24h: float
    liquidity: float
    end_date: str
    active: bool
    closed: bool
    category: str
    best_bid: float
    best_ask: float
    spread: float
    order_book_bids: list[tuple[float, float]]
    order_book_asks: list[tuple[float, float]]
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main adapter
# ---------------------------------------------------------------------------

class PolymarketAdapter:
    """Adapter for Polymarket prediction market.

    Supports two modes:
      - **Read-only** (no credentials): fetch markets, order books, prices
      - **Trading** (requires CLOB credentials): place/cancel orders, positions

    Example:
        >>> adapter = PolymarketAdapter()
        >>> markets = adapter.get_active_markets(limit=10)
        >>> for m in markets:
        ...     print(f"{m.question}: {m.market_prob:.0%}")
    """

    def __init__(
        self,
        *,
        gamma_base: str = GAMMA_API_BASE,
        clob_base: str = CLOB_API_BASE,
        max_requests_per_minute: int = DEFAULT_MAX_REQUESTS_PER_MINUTE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._gamma_base = gamma_base.rstrip("/")
        self._clob_base = clob_base.rstrip("/")
        self._timeout = timeout
        self._limiter = _RateLimiter(max_per_minute=max_requests_per_minute)

        # CLOB credentials (loaded from env, never hardcoded)
        self._api_key = os.environ.get("POLYMARKET_API_KEY")
        self._api_secret = os.environ.get("POLYMARKET_API_SECRET")
        self._passphrase = os.environ.get("POLYMARKET_PASSPHRASE")
        self._private_key = os.environ.get("POLYMARKET_PK")
        self._funder = os.environ.get("POLYMARKET_FUNDER")

        # Optional: py-clob-client for authenticated trading
        self._clob_client: Any | None = None

    # ------------------------------------------------------------------
    # Credential helpers
    # ------------------------------------------------------------------

    @property
    def has_clob_credentials(self) -> bool:
        """True if CLOB API credentials are available."""
        return bool(self._api_key and self._api_secret and self._passphrase)

    def _ensure_clob_client(self) -> Any:
        """Lazily initialize the py-clob-client ClobClient."""
        if self._clob_client is not None:
            return self._clob_client

        if not self.has_clob_credentials:
            raise RuntimeError(
                "CLOB credentials required. Set POLYMARKET_API_KEY, "
                "POLYMARKET_API_SECRET, and POLYMARKET_PASSPHRASE env vars."
            )

        try:
            from py_clob_client.client import ClobClient
        except ImportError as exc:
            raise ImportError(
                "py-clob-client is required for trading. "
                "Install with: pip install py-clob-client"
            ) from exc

        self._clob_client = ClobClient(
            host=self._clob_base,
            chain_id=137,  # Polygon mainnet
            key=self._private_key,
            creds={
                "apiKey": self._api_key,
                "secret": self._api_secret,
                "passphrase": self._passphrase,
            },
            signature_type=0,  # 0=EOA, 1=Magic, 2=Safe
            funder=self._funder,
        )
        return self._clob_client

    # ------------------------------------------------------------------
    # Gamma API — public, read-only
    # ------------------------------------------------------------------

    def get_active_markets(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        category: str | None = None,
        min_volume: float = 0.0,
        min_liquidity: float = 0.0,
    ) -> list[PolymarketMarket]:
        """Fetch active markets from the Gamma API.

        Args:
            limit: Max markets to return (API max ~100 per page).
            offset: Pagination offset.
            category: Filter by category slug (e.g., "politics", "crypto").
            min_volume: Minimum 24h volume filter.
            min_liquidity: Minimum liquidity filter.

        Returns:
            List of PolymarketMarket objects.
        """
        params: dict[str, str] = {
            "limit": str(limit),
            "offset": str(offset),
            "active": "true",
            "closed": "false",
        }
        url = f"{self._gamma_base}/markets?{urllib.parse.urlencode(params)}"
        raw_markets = _http_get(url, timeout=self._timeout, rate_limiter=self._limiter)

        if not isinstance(raw_markets, list):
            logger.warning("Unexpected Gamma /markets response type: %s", type(raw_markets))
            return []

        results: list[PolymarketMarket] = []
        for raw in raw_markets:
            try:
                market = self._parse_gamma_market(raw)
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug("Skipping malformed market %s: %s", raw.get("conditionId", "?"), exc)
                continue

            # Apply client-side filters
            if category and market.category.lower() != category.lower():
                continue
            if market.volume_24h < min_volume:
                continue
            if market.liquidity < min_liquidity:
                continue

            results.append(market)

        return results

    def get_market(self, condition_id: str) -> PolymarketMarket | None:
        """Fetch a single market by condition ID.

        Uses the CLOB API (which supports condition_id lookup) as primary,
        then enriches with Gamma metadata when available.
        """
        # CLOB API reliably resolves condition_id
        clob_url = f"{self._clob_base}/markets/{condition_id}"
        try:
            clob_data = _http_get(clob_url, timeout=self._timeout, rate_limiter=self._limiter)
        except (ConnectionError, urllib.error.HTTPError):
            return None

        if not isinstance(clob_data, dict):
            return None

        # Extract tokens from CLOB response
        tokens = clob_data.get("tokens", [])
        token_id_yes = ""
        token_id_no = ""
        market_prob = 0.5
        for tok in tokens:
            outcome = tok.get("outcome", "")
            tid = tok.get("token_id", "")
            price = float(tok.get("price", 0))
            if outcome == "Yes":
                token_id_yes = tid
                if price > 0:
                    market_prob = price
            elif outcome == "No":
                token_id_no = tid

        # Try Gamma for richer metadata (volume, liquidity, dates)
        gamma_data: dict[str, Any] = {}
        try:
            gamma_url = f"{self._gamma_base}/markets?limit=100&active=true&closed=false"
            gamma_results = _http_get(gamma_url, timeout=self._timeout, rate_limiter=self._limiter)
            if isinstance(gamma_results, list):
                for item in gamma_results:
                    if item.get("conditionId") == condition_id:
                        gamma_data = item
                        break
        except (ConnectionError, urllib.error.HTTPError):
            pass

        question = str(clob_data.get("question", gamma_data.get("question", "")))
        volume_24h = float(gamma_data.get("volume24hr", gamma_data.get("volume", 0)))
        liquidity = float(gamma_data.get("liquidity", 0))
        end_date = str(clob_data.get("end_date_iso", gamma_data.get("endDate", "")))
        active = bool(clob_data.get("active", True))
        closed = bool(clob_data.get("closed", False))
        category = str(gamma_data.get("groupItemTitle", gamma_data.get("category", "other"))).lower()

        market_prob = max(0.001, min(0.999, market_prob))
        best_bid = float(gamma_data.get("bestBid", market_prob - 0.01))
        best_ask = float(gamma_data.get("bestAsk", market_prob + 0.01))

        return PolymarketMarket(
            condition_id=condition_id,
            question=question,
            token_id_yes=token_id_yes,
            token_id_no=token_id_no,
            market_prob=market_prob,
            volume_24h=volume_24h,
            liquidity=liquidity,
            end_date=end_date,
            active=active,
            closed=closed,
            category=category,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=max(best_ask - best_bid, 0.0),
            order_book_bids=[(best_bid, liquidity / 2)] if liquidity > 0 else [],
            order_book_asks=[(best_ask, liquidity / 2)] if liquidity > 0 else [],
            metadata={
                "conditionId": condition_id,
                "slug": gamma_data.get("slug", ""),
                "neg_risk": clob_data.get("neg_risk", gamma_data.get("negRisk", False)),
                "tick_size": str(clob_data.get("minimum_tick_size", "0.01")),
            },
        )

    def get_events(
        self,
        *,
        limit: int = 25,
        offset: int = 0,
        active: bool = True,
    ) -> list[PolymarketEvent]:
        """Fetch events (which group related markets)."""
        params: dict[str, str] = {
            "limit": str(limit),
            "offset": str(offset),
            "active": str(active).lower(),
            "closed": "false",
        }
        url = f"{self._gamma_base}/events?{urllib.parse.urlencode(params)}"
        raw_events = _http_get(url, timeout=self._timeout, rate_limiter=self._limiter)

        if not isinstance(raw_events, list):
            return []

        results: list[PolymarketEvent] = []
        for raw in raw_events:
            try:
                event = self._parse_gamma_event(raw)
                results.append(event)
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug("Skipping malformed event: %s", exc)
                continue

        return results

    # ------------------------------------------------------------------
    # CLOB API — order book (public endpoint, no auth)
    # ------------------------------------------------------------------

    def get_order_book(self, token_id: str) -> dict[str, list[tuple[float, float]]]:
        """Fetch the live order book for a token from the CLOB.

        Args:
            token_id: The YES or NO token ID.

        Returns:
            Dict with "bids" and "asks", each a list of (price, size) tuples
            sorted best-first.
        """
        url = f"{self._clob_base}/book?token_id={token_id}"
        raw = _http_get(url, timeout=self._timeout, rate_limiter=self._limiter)

        bids: list[tuple[float, float]] = []
        asks: list[tuple[float, float]] = []

        for entry in raw.get("bids", []):
            price = float(entry.get("price", 0))
            size = float(entry.get("size", 0))
            if price > 0 and size > 0:
                bids.append((price, size))

        for entry in raw.get("asks", []):
            price = float(entry.get("price", 0))
            size = float(entry.get("size", 0))
            if price > 0 and size > 0:
                asks.append((price, size))

        # Best-first: bids descending, asks ascending
        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        return {"bids": bids, "asks": asks}

    def get_midpoint(self, token_id: str) -> float | None:
        """Fetch the CLOB midpoint price for a token."""
        url = f"{self._clob_base}/midpoint?token_id={token_id}"
        try:
            raw = _http_get(url, timeout=self._timeout, rate_limiter=self._limiter)
            mid = float(raw.get("mid", 0))
            return mid if mid > 0 else None
        except (ConnectionError, ValueError):
            return None

    def get_price(self, token_id: str, side: str = "buy") -> float | None:
        """Fetch the best available price for a token on a given side."""
        url = f"{self._clob_base}/price?token_id={token_id}&side={side}"
        try:
            raw = _http_get(url, timeout=self._timeout, rate_limiter=self._limiter)
            price = float(raw.get("price", 0))
            return price if price > 0 else None
        except (ConnectionError, ValueError):
            return None

    # ------------------------------------------------------------------
    # CLOB API — authenticated trading
    # ------------------------------------------------------------------

    def get_balance(self) -> float:
        """Get USDC balance (requires CLOB credentials)."""
        client = self._ensure_clob_client()
        resp = client.get_balance_allowance()
        # py-clob-client returns balance in wei (USDC has 6 decimals)
        balance_raw = float(resp.get("balance", 0))
        return balance_raw / 1e6

    def get_position(self, condition_id: str) -> dict[str, float]:
        """Get current position sizes for a market.

        Returns:
            Dict with "yes" and "no" position sizes.
        """
        client = self._ensure_clob_client()
        positions = client.get_positions()
        result = {"yes": 0.0, "no": 0.0}
        for pos in positions:
            if pos.get("conditionId") == condition_id or pos.get("asset", {}).get("conditionId") == condition_id:
                token_id = pos.get("tokenId", "") or pos.get("asset", {}).get("tokenId", "")
                size = float(pos.get("size", 0))
                # Determine if YES or NO based on outcomeIndex
                outcome_idx = pos.get("outcomeIndex", pos.get("asset", {}).get("outcomeIndex"))
                if outcome_idx == 0 or str(outcome_idx) == "0":
                    result["yes"] = size
                else:
                    result["no"] = size
        return result

    def place_order(
        self,
        *,
        token_id: str,
        side: str,
        size: float,
        price: float,
        tick_size: str = "0.01",
        neg_risk: bool = False,
    ) -> dict[str, Any]:
        """Place a limit order on the CLOB.

        Args:
            token_id: YES or NO token ID.
            side: "BUY" or "SELL".
            size: Number of contracts.
            price: Limit price (0-1, must align to tick_size).
            tick_size: Minimum price increment ("0.01" or "0.001").
            neg_risk: Whether this is a neg-risk market.

        Returns:
            Order response dict from the CLOB.

        Raises:
            RuntimeError: If credentials are missing.
            ImportError: If py-clob-client is not installed.
        """
        client = self._ensure_clob_client()

        from py_clob_client.order_builder.constants import BUY, SELL

        order_side = BUY if side.upper() == "BUY" else SELL

        order_args = {
            "token_id": token_id,
            "price": price,
            "size": size,
            "side": order_side,
        }

        if neg_risk:
            order_args["neg_risk"] = True

        signed_order = client.create_order(order_args)
        resp = client.post_order(signed_order, tick_size=tick_size)

        logger.info(
            "Order placed: token=%s side=%s size=%.2f price=%.4f resp=%s",
            token_id, side, size, price, resp,
        )
        return resp

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an outstanding order."""
        client = self._ensure_clob_client()
        try:
            client.cancel(order_id)
            return True
        except Exception as exc:
            logger.warning("Cancel failed for %s: %s", order_id, exc)
            return False

    def cancel_all(self) -> bool:
        """Cancel all outstanding orders."""
        client = self._ensure_clob_client()
        try:
            client.cancel_all()
            return True
        except Exception as exc:
            logger.warning("Cancel all failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Bridge: Polymarket -> agent.MarketState (for backtest compatibility)
    # ------------------------------------------------------------------

    def to_agent_market_state(
        self,
        market: PolymarketMarket,
        *,
        fair_prob: float | None = None,
    ) -> "AgentMarketState":
        """Convert a PolymarketMarket to the agent's MarketState type.

        The agent requires a `fair_prob` (the trader's forecast). This must
        be supplied externally — the adapter does not generate forecasts.

        Args:
            market: PolymarketMarket from get_active_markets() or get_market().
            fair_prob: Your probability estimate. If None, uses market_prob
                       (which means zero edge — no trade will be proposed).

        Returns:
            An agent.MarketState suitable for AutoPredictAgent.evaluate_market().
        """
        from autopredict.agent import MarketState as AgentMarketState
        from autopredict.market_env import BookLevel, OrderBook

        bids = [BookLevel(price=p, size=s) for p, s in market.order_book_bids]
        asks = [BookLevel(price=p, size=s) for p, s in market.order_book_asks]
        order_book = OrderBook(
            market_id=market.condition_id,
            bids=bids,
            asks=asks,
        )

        # Parse end_date to hours until expiry
        try:
            expiry_dt = datetime.fromisoformat(market.end_date.replace("Z", "+00:00"))
            delta = expiry_dt - datetime.now(timezone.utc)
            time_to_expiry_hours = max(delta.total_seconds() / 3600.0, 0.0)
        except (ValueError, AttributeError):
            time_to_expiry_hours = 24.0  # fallback

        return AgentMarketState(
            market_id=market.condition_id,
            market_prob=market.market_prob,
            fair_prob=fair_prob if fair_prob is not None else market.market_prob,
            time_to_expiry_hours=time_to_expiry_hours,
            order_book=order_book,
            metadata={
                "category": market.category,
                "question": market.question,
                "volume_24h": market.volume_24h,
                "liquidity": market.liquidity,
                "token_id_yes": market.token_id_yes,
                "token_id_no": market.token_id_no,
            },
        )

    def fetch_markets_for_agent(
        self,
        *,
        limit: int = 50,
        min_liquidity: float = 1000.0,
        fair_prob_fn: Any | None = None,
    ) -> list:
        """Convenience: fetch markets and convert to agent MarketState format.

        Args:
            limit: Max markets to fetch.
            min_liquidity: Minimum liquidity filter.
            fair_prob_fn: Optional callable(PolymarketMarket) -> float that
                          returns your probability estimate. If None, fair_prob
                          defaults to market_prob (no edge).

        Returns:
            List of agent.MarketState objects.
        """
        markets = self.get_active_markets(limit=limit, min_liquidity=min_liquidity)
        results = []
        for market in markets:
            # Enrich with real order book from CLOB if we have a token ID
            if market.token_id_yes:
                try:
                    book = self.get_order_book(market.token_id_yes)
                    market = PolymarketMarket(
                        condition_id=market.condition_id,
                        question=market.question,
                        token_id_yes=market.token_id_yes,
                        token_id_no=market.token_id_no,
                        market_prob=market.market_prob,
                        volume_24h=market.volume_24h,
                        liquidity=market.liquidity,
                        end_date=market.end_date,
                        active=market.active,
                        closed=market.closed,
                        category=market.category,
                        best_bid=book["bids"][0][0] if book["bids"] else market.best_bid,
                        best_ask=book["asks"][0][0] if book["asks"] else market.best_ask,
                        spread=(book["asks"][0][0] - book["bids"][0][0])
                            if book["bids"] and book["asks"]
                            else market.spread,
                        order_book_bids=book["bids"],
                        order_book_asks=book["asks"],
                        metadata=market.metadata,
                    )
                except (ConnectionError, KeyError) as exc:
                    logger.debug("Could not fetch CLOB book for %s: %s", market.condition_id, exc)

            fair_prob = None
            if fair_prob_fn is not None:
                try:
                    fair_prob = float(fair_prob_fn(market))
                except Exception as exc:
                    logger.debug("fair_prob_fn failed for %s: %s", market.condition_id, exc)

            results.append(self.to_agent_market_state(market, fair_prob=fair_prob))

        return results

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _parse_gamma_market(self, raw: dict[str, Any]) -> PolymarketMarket:
        """Parse a Gamma API market response into PolymarketMarket."""
        condition_id = str(raw["conditionId"])
        question = str(raw.get("question", ""))

        # Token IDs (YES = index 0, NO = index 1 in clobTokenIds)
        # Gamma API returns these as JSON strings, not arrays
        clob_token_ids = raw.get("clobTokenIds", [])
        if isinstance(clob_token_ids, str):
            try:
                clob_token_ids = json.loads(clob_token_ids)
            except (json.JSONDecodeError, TypeError):
                clob_token_ids = []
        token_id_yes = str(clob_token_ids[0]) if len(clob_token_ids) > 0 else ""
        token_id_no = str(clob_token_ids[1]) if len(clob_token_ids) > 1 else ""

        # Probability from outcomePrices (YES price = market probability)
        outcome_prices = raw.get("outcomePrices", [])
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except (json.JSONDecodeError, TypeError):
                outcome_prices = []
        if outcome_prices and len(outcome_prices) > 0:
            market_prob = float(outcome_prices[0])
        else:
            market_prob = float(raw.get("lastTradePrice", 0.5))

        # Best bid/ask from Gamma (approximation — CLOB has the real book)
        best_bid = float(raw.get("bestBid", market_prob - 0.01))
        best_ask = float(raw.get("bestAsk", market_prob + 0.01))
        spread = max(best_ask - best_bid, 0.0)

        # Clamp to valid range
        market_prob = max(0.001, min(0.999, market_prob))
        best_bid = max(0.001, min(0.999, best_bid))
        best_ask = max(0.001, min(0.999, best_ask))

        volume_24h = float(raw.get("volume24hr", raw.get("volume", 0)))
        liquidity = float(raw.get("liquidity", 0))
        end_date = str(raw.get("endDate", raw.get("endDateIso", "")))
        active = bool(raw.get("active", True))
        closed = bool(raw.get("closed", False))

        # Category
        category = str(raw.get("groupItemTitle", raw.get("category", "other"))).lower()

        # Gamma doesn't return full order book — use placeholder bids/asks
        # from best bid/ask. Real book is fetched via get_order_book().
        order_book_bids = [(best_bid, liquidity / 2)] if liquidity > 0 else []
        order_book_asks = [(best_ask, liquidity / 2)] if liquidity > 0 else []

        return PolymarketMarket(
            condition_id=condition_id,
            question=question,
            token_id_yes=token_id_yes,
            token_id_no=token_id_no,
            market_prob=market_prob,
            volume_24h=volume_24h,
            liquidity=liquidity,
            end_date=end_date,
            active=active,
            closed=closed,
            category=category,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            order_book_bids=order_book_bids,
            order_book_asks=order_book_asks,
            metadata={
                "conditionId": condition_id,
                "slug": raw.get("slug", ""),
                "neg_risk": raw.get("negRisk", False),
                "tick_size": raw.get("minimumTickSize", "0.01"),
            },
        )

    def _parse_gamma_event(self, raw: dict[str, Any]) -> PolymarketEvent:
        """Parse a Gamma API event response."""
        event_id = str(raw.get("id", ""))
        title = str(raw.get("title", ""))
        slug = str(raw.get("slug", ""))

        markets: list[PolymarketMarket] = []
        for m in raw.get("markets", []):
            try:
                markets.append(self._parse_gamma_market(m))
            except (KeyError, ValueError, TypeError):
                continue

        return PolymarketEvent(
            event_id=event_id,
            title=title,
            slug=slug,
            markets=markets,
        )
