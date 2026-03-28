"""Polymarket adapter with real public market-data access and live-order plumbing.

This adapter intentionally splits the Polymarket integration into two layers:

1. Public market discovery and order-book reads use the documented Gamma and CLOB
   HTTP APIs directly, so read-only functionality works without credentials.
2. Authenticated trading uses the official ``py_clob_client`` when available.

The goal is to provide a real venue boundary instead of a placeholder while
remaining honest about verification limits: read-only behavior is exercised
directly against Polymarket's public endpoints, while authenticated order
placement still depends on valid user credentials and the official trading
client being installed in the runtime environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import time
from typing import Any

import requests

from autopredict.config.loader import is_missing_env_placeholder
from autopredict.core.types import (
    ExecutionReport,
    MarketCategory,
    MarketState,
    Order,
    OrderSide,
    OrderType,
)


DEFAULT_CLOB_URL = "https://clob.polymarket.com"
DEFAULT_STAGING_CLOB_URL = "https://clob-staging.polymarket.com"
DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"
DEFAULT_CHAIN_ID = 137
BUY = "BUY"

_CATEGORY_KEYWORDS: tuple[tuple[MarketCategory, tuple[str, ...]], ...] = (
    (
        MarketCategory.CRYPTO,
        ("bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto", "doge"),
    ),
    (
        MarketCategory.POLITICS,
        (
            "election",
            "president",
            "trump",
            "biden",
            "senate",
            "house",
            "approval",
            "poll",
            "vote",
            "campaign",
            "ceasefire",
            "ukraine",
            "russia",
            "israel",
            "geopolitics",
            "treaty",
        ),
    ),
    (
        MarketCategory.ECONOMICS,
        (
            "inflation",
            "cpi",
            "fed",
            "rates",
            "recession",
            "gdp",
            "payrolls",
            "tariff",
            "economy",
            "macro",
        ),
    ),
    (
        MarketCategory.SPORTS,
        (
            "nba",
            "nfl",
            "mlb",
            "nhl",
            "champions",
            "world cup",
            "super bowl",
            "march madness",
            "wimbledon",
            "f1",
        ),
    ),
    (
        MarketCategory.SCIENCE,
        ("science", "launch", "spacex", "nasa", "fda", "trial", "breakthrough"),
    ),
    (
        MarketCategory.ENTERTAINMENT,
        ("oscar", "movie", "album", "box office", "tv", "grammy", "emmy"),
    ),
)


@dataclass(frozen=True)
class _ResolvedToken:
    token_id: str
    outcome: str
    displayed_price: float
    order_side: str = BUY


class PolymarketAdapter:
    """Real Polymarket boundary with public data access and optional live trading."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        api_passphrase: str | None = None,
        private_key: str | None = None,
        funder: str | None = None,
        *,
        signature_type: int = 0,
        chain_id: int = DEFAULT_CHAIN_ID,
        testnet: bool = False,
        base_url: str | None = None,
        gamma_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        session: requests.Session | None = None,
        trading_client: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.private_key = private_key
        self.funder = funder
        self.signature_type = int(signature_type)
        self.chain_id = int(chain_id)
        self.testnet = bool(testnet)
        self.base_url = base_url or (
            DEFAULT_STAGING_CLOB_URL if self.testnet else DEFAULT_CLOB_URL
        )
        self.gamma_url = gamma_url or DEFAULT_GAMMA_URL
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "autopredict-polymarket/0.1")
        self._trading_client = trading_client

    @classmethod
    def from_env(
        cls,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        api_passphrase: str | None = None,
        private_key: str | None = None,
        funder: str | None = None,
        signature_type: int | str | None = None,
        chain_id: int | str | None = None,
        testnet: bool = False,
        base_url: str | None = None,
        gamma_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        session: requests.Session | None = None,
        trading_client: Any | None = None,
    ) -> "PolymarketAdapter":
        """Create an adapter from explicit values plus Polymarket env defaults."""

        return cls(
            api_key=api_key or os.getenv("POLYMARKET_API_KEY"),
            api_secret=api_secret or os.getenv("POLYMARKET_API_SECRET"),
            api_passphrase=api_passphrase or os.getenv("POLYMARKET_API_PASSPHRASE"),
            private_key=private_key or os.getenv("POLYMARKET_PRIVATE_KEY"),
            funder=funder or os.getenv("POLYMARKET_FUNDER"),
            signature_type=int(signature_type or os.getenv("POLYMARKET_SIGNATURE_TYPE", "0")),
            chain_id=int(chain_id or os.getenv("POLYMARKET_CHAIN_ID", str(DEFAULT_CHAIN_ID))),
            testnet=testnet,
            base_url=base_url or os.getenv("POLYMARKET_CLOB_URL"),
            gamma_url=gamma_url or os.getenv("POLYMARKET_GAMMA_URL"),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            session=session,
            trading_client=trading_client,
        )

    def validate_credentials(self, *, require_trading: bool = True) -> None:
        """Validate credential presence for authenticated trading."""

        if not require_trading:
            return True

        required = {
            "POLYMARKET_API_KEY": self.api_key,
            "POLYMARKET_API_SECRET": self.api_secret,
            "POLYMARKET_API_PASSPHRASE": self.api_passphrase,
            "POLYMARKET_PRIVATE_KEY": self.private_key,
            "POLYMARKET_FUNDER": self.funder,
        }
        missing = [
            env_name
            for env_name, value in required.items()
            if not value or is_missing_env_placeholder(value)
        ]
        if missing:
            raise ValueError(
                "Polymarket live trading requires credentials for: "
                + ", ".join(sorted(missing))
            )
        if self.signature_type not in (0, 1, 2):
            raise ValueError("Polymarket signature_type must be one of 0, 1, or 2")
        if self.chain_id <= 0:
            raise ValueError("Polymarket chain_id must be positive")
        return True

    def check_connectivity(self) -> dict[str, Any]:
        """Return a small read-only health snapshot from Polymarket."""

        response = self._request_json("GET", f"{self.base_url}/ok")
        return {"ok": response, "base_url": self.base_url, "gamma_url": self.gamma_url}

    def get_markets(self, filters: dict | None = None) -> list[MarketState]:
        """Fetch active markets from Gamma and enrich them with live order books."""

        filters = dict(filters or {})
        limit = int(filters.pop("limit", 25))
        min_liquidity = float(filters.pop("min_liquidity", 0.0))
        min_volume = float(filters.pop("min_volume", 0.0))
        active_only = bool(filters.pop("active_only", True))
        category_filter = str(filters.pop("category", "")).strip().lower()
        slug_filter = filters.pop("slug", None)

        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": 0,
            "active": str(active_only).lower(),
            "closed": "false",
        }
        if slug_filter:
            params["slug"] = slug_filter

        collected: list[MarketState] = []
        while len(collected) < limit:
            raw_markets = self._request_json("GET", f"{self.gamma_url}/markets", params=params)
            if not isinstance(raw_markets, list) or not raw_markets:
                break

            for raw_market in raw_markets:
                market = self._convert_market(raw_market)
                if market.total_liquidity < min_liquidity:
                    continue
                if market.volume_24h < min_volume:
                    continue
                if category_filter and market.category.value != category_filter:
                    continue
                collected.append(market)
                if len(collected) >= limit:
                    break

            params["offset"] += len(raw_markets)

        return collected

    def get_market(self, market_id: str) -> MarketState | None:
        """Fetch a single market by prefixed condition id, raw id, slug, or condition id."""

        raw_market = self._find_raw_market(market_id)
        if raw_market is None:
            return None
        return self._convert_market(raw_market)

    def place_order(self, order: Order) -> ExecutionReport:
        """Place an order on Polymarket using the official CLOB client."""

        self.validate_credentials(require_trading=True)

        raw_market = self._find_raw_market(order.market_id)
        if raw_market is None:
            raise ValueError(f"Could not resolve Polymarket market '{order.market_id}'")

        token = self._resolve_token_for_order(raw_market, order)
        book = self._get_order_book(token.token_id)
        tick_size = self._extract_tick_size(raw_market, book)
        min_order_size = self._extract_min_order_size(raw_market, book)
        if order.size < min_order_size:
            raise ValueError(
                f"Order size {order.size} is below Polymarket minimum order size {min_order_size}"
            )

        price = self._resolve_order_price(order, book, token, tick_size)
        client = self._get_trading_client()
        order_args, venue_order_type, create_options = self._build_live_order_args(
            client=client,
            token=token,
            order=order,
            price=price,
            tick_size=tick_size,
            raw_market=raw_market,
        )

        if create_options is None:
            signed_order = client.create_order(order_args)
        else:
            signed_order = client.create_order(order_args, create_options)
        response = client.post_order(signed_order, venue_order_type)
        return self._convert_execution_report(
            order=order,
            response=response,
            token=token,
            venue_price=price,
            semantic_price=(price if token.outcome == "YES" else 1.0 - price),
            submitted_price=price,
        )

    def submit_order(self, order: Order) -> ExecutionReport:
        """Compatibility alias for live-trading adapters."""

        return self.place_order(order)

    def cancel_order(self, market_id: str, order_id: str) -> bool:
        """Cancel an outstanding Polymarket order by order id."""

        del market_id
        self.validate_credentials(require_trading=True)
        response = self._get_trading_client().cancel(order_id)
        if isinstance(response, dict):
            if "success" in response:
                return bool(response["success"])
            if "canceled" in response:
                return bool(response["canceled"])
        return bool(response)

    def get_position(self, market_id: str) -> float:
        """Return an approximate YES-equivalent position from authenticated trades."""

        self.validate_credentials(require_trading=True)
        raw_market = self._find_raw_market(market_id)
        if raw_market is None:
            return 0.0

        yes_token, no_token = self._resolve_yes_no_tokens(raw_market)
        trades = self._get_trading_client().get_trades()
        if not isinstance(trades, list):
            return 0.0

        yes_position = 0.0
        no_position = 0.0
        for trade in trades:
            asset_id = str(trade.get("asset_id") or trade.get("assetId") or "")
            size = self._coerce_float(
                trade.get("size")
                or trade.get("matchedAmount")
                or trade.get("takingAmount")
                or trade.get("makerAmount")
                or 0.0
            )
            side = str(trade.get("side", "")).upper()
            signed = size if side == BUY else -size
            if yes_token and asset_id == yes_token:
                yes_position += signed
            if no_token and asset_id == no_token:
                no_position += signed
        return yes_position - no_position

    def get_balance(self) -> float:
        """Return available collateral balance from Polymarket when authenticated."""

        self.validate_credentials(require_trading=True)
        client = self._get_trading_client()
        params = self._build_balance_allowance_params(client)
        response = client.get_balance_allowance(params)
        for key in ("balance", "available", "availableBalance"):
            if key in response:
                return self._coerce_float(response[key])
        if "balance" in response.get("data", {}):
            return self._coerce_float(response["data"]["balance"])
        return 0.0

    def _convert_market(self, raw_market: dict[str, Any]) -> MarketState:
        condition_id = str(raw_market["conditionId"])
        question = str(raw_market["question"]).strip()
        market_prob = self._extract_yes_probability(raw_market)
        book = self._get_order_book(self._resolve_yes_no_tokens(raw_market)[0])
        best_bid = self._best_price(book.get("bids", ()))
        best_ask = self._best_price(book.get("asks", ()))
        tick_size = self._extract_tick_size(raw_market, book)
        if best_bid is None:
            best_bid = max(0.0, market_prob - tick_size)
        if best_ask is None:
            best_ask = min(1.0, market_prob + tick_size)

        expiry = self._parse_timestamp(raw_market.get("endDate"))
        category = self._infer_category(raw_market)
        bid_liquidity = self._total_size(book.get("bids", ()))
        ask_liquidity = self._total_size(book.get("asks", ()))
        clob_token_ids = self._parse_json_list(raw_market.get("clobTokenIds"))
        outcomes = self._parse_json_list(raw_market.get("outcomes"))

        return MarketState(
            market_id=f"polymarket-{condition_id}",
            question=question,
            market_prob=market_prob,
            expiry=expiry,
            category=category,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_liquidity=bid_liquidity,
            ask_liquidity=ask_liquidity,
            volume_24h=self._coerce_float(raw_market.get("volume")),
            num_traders=int(self._coerce_float(raw_market.get("numTraders", 0))),
            metadata={
                "venue": "polymarket",
                "market_id": str(raw_market.get("id", "")),
                "condition_id": condition_id,
                "slug": raw_market.get("slug"),
                "outcomes": outcomes,
                "token_ids": clob_token_ids,
                "yes_token_id": clob_token_ids[0] if clob_token_ids else None,
                "no_token_id": clob_token_ids[1] if len(clob_token_ids) > 1 else None,
                "order_min_size": self._extract_min_order_size(raw_market, book),
                "tick_size": tick_size,
                "accepting_orders": bool(raw_market.get("acceptingOrders", True)),
                "neg_risk": bool(raw_market.get("negRisk", False)),
                "raw_market": raw_market,
            },
        )

    def _find_raw_market(self, market_identifier: str) -> dict[str, Any] | None:
        target = str(market_identifier).removeprefix("polymarket-")
        offset = 0
        limit = 100
        while True:
            raw_markets = self._request_json(
                "GET",
                f"{self.gamma_url}/markets",
                params={"limit": limit, "offset": offset, "active": "true", "closed": "false"},
            )
            if not isinstance(raw_markets, list) or not raw_markets:
                break
            for raw_market in raw_markets:
                if self._raw_market_matches(raw_market, target):
                    return raw_market
            offset += len(raw_markets)
            if len(raw_markets) < limit:
                break
        return None

    @staticmethod
    def _raw_market_matches(raw_market: dict[str, Any], target: str) -> bool:
        return target in {
            str(raw_market.get("id", "")),
            str(raw_market.get("conditionId", "")),
            str(raw_market.get("slug", "")),
        }

    def _get_order_book(self, token_id: str | None) -> dict[str, Any]:
        if not token_id:
            return {"bids": [], "asks": []}
        return self._request_json("GET", f"{self.base_url}/book", params={"token_id": token_id})

    def _resolve_token_for_order(self, raw_market: dict[str, Any], order: Order) -> _ResolvedToken:
        yes_token, no_token = self._resolve_yes_no_tokens(raw_market)
        yes_price = self._extract_yes_probability(raw_market)

        if order.side == OrderSide.BUY:
            if not yes_token:
                raise ValueError("Polymarket market is missing a YES token id")
            return _ResolvedToken(token_id=yes_token, outcome="YES", displayed_price=yes_price)

        if not no_token:
            raise ValueError(
                "Polymarket sell orders are mapped to buying the NO token, "
                "but this market did not expose a NO token id"
            )
        return _ResolvedToken(
            token_id=no_token,
            outcome="NO",
            displayed_price=1.0 - yes_price,
        )

    def _build_live_order_args(
        self,
        *,
        client: Any,
        token: _ResolvedToken,
        order: Order,
        price: float,
        tick_size: float,
        raw_market: dict[str, Any],
    ) -> tuple[Any, Any, Any | None]:
        order_args_type = self._client_attr(client, "OrderArgs")
        order_type_enum = self._client_attr(client, "OrderType")

        order_args = order_args_type(
            token_id=token.token_id,
            price=price,
            size=order.size,
            side=BUY,
        )
        venue_order_type = order_type_enum.GTC
        if order.order_type == OrderType.MARKET:
            venue_order_type = getattr(order_type_enum, "FAK", order_type_enum.GTC)

        options_type = self._client_optional_attr(client, "PartialCreateOrderOptions")
        if options_type is not None:
            options = options_type(
                tick_size=self._format_tick_size(tick_size),
                neg_risk=bool(raw_market.get("negRisk", False)),
            )
            return order_args, venue_order_type, options
        return order_args, venue_order_type, None

    def _resolve_order_price(
        self,
        order: Order,
        book: dict[str, Any],
        token: _ResolvedToken,
        tick_size: float,
    ) -> float:
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("Polymarket limit orders require limit_price")
            if order.side == OrderSide.SELL:
                price = 1.0 - float(order.limit_price)
            else:
                price = float(order.limit_price)
            return self._clamp_probability(self._round_to_tick(price, tick_size))

        best_ask = self._best_price(book.get("asks", ()))
        if best_ask is None:
            best_ask = token.displayed_price
        return self._clamp_probability(self._round_to_tick(best_ask, tick_size))

    def _convert_execution_report(
        self,
        *,
        order: Order,
        response: Any,
        token: _ResolvedToken,
        venue_price: float,
        semantic_price: float,
        submitted_price: float,
    ) -> ExecutionReport:
        payload = response if isinstance(response, dict) else {"raw_response": response}
        status = str(payload.get("status", "")).lower()
        error_message = payload.get("errorMsg") or payload.get("error")
        filled_size = 0.0
        avg_fill_price: float | None = None
        if status in {"filled", "matched"}:
            filled_size = order.size
            avg_fill_price = semantic_price
        slippage_bps = 0.0
        if avg_fill_price is not None and order.limit_price is not None and order.limit_price > 0:
            if order.side == OrderSide.BUY:
                slippage_bps = max(avg_fill_price - order.limit_price, 0.0) / order.limit_price * 10_000.0
            else:
                slippage_bps = max(order.limit_price - avg_fill_price, 0.0) / order.limit_price * 10_000.0

        return ExecutionReport(
            order=order,
            filled_size=filled_size,
            avg_fill_price=avg_fill_price,
            fills=[(avg_fill_price, filled_size)] if avg_fill_price is not None and filled_size > 0 else [],
            slippage_bps=slippage_bps,
            fee_total=0.0,
            execution_mode="live",
            error_message=error_message,
            metadata={
                "venue": "polymarket",
                "status": payload.get("status"),
                "order_id": payload.get("orderID") or payload.get("id"),
                "token_id": token.token_id,
                "outcome": token.outcome,
                "submitted_price": submitted_price,
                "venue_price": venue_price,
                "semantic_price": semantic_price,
                "raw_response": payload,
            },
        )

    def _get_trading_client(self) -> Any:
        if self._trading_client is not None:
            return self._trading_client

        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds, BalanceAllowanceParams, OrderArgs, OrderType
            try:
                from py_clob_client.clob_types import PartialCreateOrderOptions
            except ImportError:
                PartialCreateOrderOptions = None
        except ImportError as exc:
            raise RuntimeError(
                "Authenticated Polymarket trading requires the official py_clob_client "
                "package. Install it in the runtime environment before placing orders."
            ) from exc

        creds = ApiCreds(
            api_key=str(self.api_key),
            api_secret=str(self.api_secret),
            api_passphrase=str(self.api_passphrase),
        )
        client = ClobClient(
            host=self.base_url,
            chain_id=self.chain_id,
            key=str(self.private_key),
            creds=creds,
            signature_type=self.signature_type,
            funder=str(self.funder),
        )
        client.OrderArgs = OrderArgs
        client.OrderType = OrderType
        client.BalanceAllowanceParams = BalanceAllowanceParams
        client.PartialCreateOrderOptions = PartialCreateOrderOptions
        self._trading_client = client
        return client

    def _build_balance_allowance_params(self, client: Any) -> Any:
        params_type = self._client_attr(client, "BalanceAllowanceParams")
        asset_type = self._client_optional_attr(client, "AssetType")
        if asset_type is not None:
            return params_type(asset_type=asset_type.COLLATERAL, signature_type=self.signature_type)
        return params_type(signature_type=self.signature_type)

    @staticmethod
    def _client_attr(client: Any, name: str) -> Any:
        value = getattr(client, name, None)
        if value is None:
            raise RuntimeError(f"Polymarket trading client is missing required attribute {name!r}")
        return value

    @staticmethod
    def _client_optional_attr(client: Any, name: str) -> Any:
        return getattr(client, name, None)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any | None = None,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(
                        f"Polymarket request to {url} failed with status {response.status_code}",
                        response=response,
                    )
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError:
                    return response.text
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                time.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"Polymarket request failed for {url}: {last_error}") from last_error

    @staticmethod
    def _resolve_yes_no_tokens(raw_market: dict[str, Any]) -> tuple[str | None, str | None]:
        token_ids = PolymarketAdapter._parse_json_list(raw_market.get("clobTokenIds"))
        yes_token = token_ids[0] if token_ids else None
        no_token = token_ids[1] if len(token_ids) > 1 else None
        return yes_token, no_token

    @staticmethod
    def _extract_yes_probability(raw_market: dict[str, Any]) -> float:
        prices = PolymarketAdapter._parse_json_list(raw_market.get("outcomePrices"))
        if not prices:
            return 0.5
        return PolymarketAdapter._clamp_probability(
            PolymarketAdapter._coerce_float(prices[0], default=0.5)
        )

    @staticmethod
    def _parse_json_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return list(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [value]
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        return [value]

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _best_price(levels: list[dict[str, Any]] | tuple[Any, ...] | list[Any]) -> float | None:
        if not levels:
            return None
        level = levels[0]
        if isinstance(level, dict):
            return PolymarketAdapter._coerce_float(level.get("price"), default=0.0)
        if isinstance(level, (list, tuple)) and level:
            return PolymarketAdapter._coerce_float(level[0], default=0.0)
        return None

    @staticmethod
    def _total_size(levels: list[dict[str, Any]] | tuple[Any, ...] | list[Any]) -> float:
        total = 0.0
        for level in levels:
            if isinstance(level, dict):
                total += PolymarketAdapter._coerce_float(level.get("size"), default=0.0)
            elif isinstance(level, (list, tuple)) and len(level) >= 2:
                total += PolymarketAdapter._coerce_float(level[1], default=0.0)
        return total

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if isinstance(value, str) and value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.now(timezone.utc)

    @staticmethod
    def _round_to_tick(price: float, tick_size: float) -> float:
        if tick_size <= 0:
            return price
        rounded = round(price / tick_size) * tick_size
        return min(max(rounded, tick_size), 1.0 - tick_size)

    @staticmethod
    def _clamp_probability(value: float) -> float:
        return min(max(value, 0.0), 1.0)

    @staticmethod
    def _format_tick_size(value: float) -> str:
        return f"{value:.4f}".rstrip("0").rstrip(".")

    def _extract_tick_size(self, raw_market: dict[str, Any], book: dict[str, Any]) -> float:
        for key in ("tick_size", "min_tick_size", "orderPriceMinTickSize"):
            if key in book:
                return max(self._coerce_float(book[key], default=0.001), 0.0001)
            if key in raw_market:
                return max(self._coerce_float(raw_market[key], default=0.001), 0.0001)
        return 0.001

    def _extract_min_order_size(self, raw_market: dict[str, Any], book: dict[str, Any]) -> float:
        for key in ("min_order_size", "orderMinSize", "minOrderSize"):
            if key in book:
                return max(self._coerce_float(book[key], default=1.0), 1.0)
            if key in raw_market:
                return max(self._coerce_float(raw_market[key], default=1.0), 1.0)
        return 1.0

    @staticmethod
    def _infer_category(raw_market: dict[str, Any]) -> MarketCategory:
        raw_category = str(raw_market.get("category") or "").strip().lower()
        if raw_category:
            category_map = {
                "politics": MarketCategory.POLITICS,
                "crypto": MarketCategory.CRYPTO,
                "economics": MarketCategory.ECONOMICS,
                "macro": MarketCategory.ECONOMICS,
                "sports": MarketCategory.SPORTS,
                "science": MarketCategory.SCIENCE,
                "entertainment": MarketCategory.ENTERTAINMENT,
                "geopolitics": MarketCategory.POLITICS,
            }
            return category_map.get(raw_category, MarketCategory.OTHER)

        haystack = " ".join(
            str(value or "")
            for value in (
                raw_market.get("question"),
                raw_market.get("slug"),
                raw_market.get("description"),
            )
        ).lower()
        for category, keywords in _CATEGORY_KEYWORDS:
            if any(keyword in haystack for keyword in keywords):
                return category
        return MarketCategory.OTHER
