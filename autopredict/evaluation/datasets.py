"""Dataset loaders that convert resolved snapshot JSON into scaffold backtests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Sequence

from autopredict.core.types import MarketCategory, MarketState
from autopredict.evaluation.backtest import ResolvedMarketSnapshot
from autopredict.prediction_market.types import VenueConfig, VenueName


_DOMAIN_BY_CATEGORY = {
    "politics": "politics",
    "geopolitics": "politics",
    "macro": "finance",
    "economics": "finance",
    "crypto": "finance",
    "weather": "weather",
}

_CATEGORY_BY_NAME = {
    "politics": MarketCategory.POLITICS,
    "geopolitics": MarketCategory.POLITICS,
    "macro": MarketCategory.ECONOMICS,
    "economics": MarketCategory.ECONOMICS,
    "crypto": MarketCategory.CRYPTO,
    "sports": MarketCategory.SPORTS,
    "science": MarketCategory.SCIENCE,
    "entertainment": MarketCategory.ENTERTAINMENT,
}

_TIER_TO_SCORE = {
    "micro": 0.15,
    "small": 0.35,
    "medium": 0.55,
    "large": 0.80,
    "tight": 0.20,
    "normal": 0.50,
    "wide": 0.80,
    "short": 0.20,
    "medium_time": 0.50,
    "medium": 0.50,
    "long": 0.80,
}


def load_resolved_snapshots(
    path: str | Path,
    *,
    venue: VenueConfig | None = None,
) -> tuple[ResolvedMarketSnapshot, ...]:
    """Load a legacy resolved-market dataset into scaffold snapshots."""

    dataset_path = Path(path)
    records = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Resolved market dataset must contain a JSON list")

    active_venue = venue or VenueConfig(
        name=VenueName.POLYMARKET,
        fee_bps=0.0,
        tick_size=0.01,
        min_order_size=1.0,
        metadata={"source": str(dataset_path)},
    )
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        _record_to_snapshot(
            record,
            observed_at=base_time + timedelta(hours=index),
            venue=active_venue,
        )
        for index, record in enumerate(records)
    )


def _record_to_snapshot(
    record: dict[str, Any],
    *,
    observed_at: datetime,
    venue: VenueConfig,
) -> ResolvedMarketSnapshot:
    market_id = str(record["market_id"])
    category_name = str(record.get("category", "other")).lower()
    order_book = record["order_book"]
    bids = order_book.get("bids") or []
    asks = order_book.get("asks") or []
    if not bids or not asks:
        raise ValueError(f"Market {market_id} is missing bids or asks")

    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    bid_liquidity = sum(float(level[1]) for level in bids)
    ask_liquidity = sum(float(level[1]) for level in asks)
    expiry = observed_at + timedelta(hours=float(record["time_to_expiry_hours"]))

    metadata = dict(record.get("metadata", {}))
    domain = _DOMAIN_BY_CATEGORY.get(category_name, "generic")
    market_family = category_name
    regime = _derive_regime(metadata)
    question = str(record.get("question") or _generate_question(market_id))

    market = MarketState(
        market_id=market_id,
        question=question,
        market_prob=float(record["market_prob"]),
        expiry=expiry,
        category=_CATEGORY_BY_NAME.get(category_name, MarketCategory.OTHER),
        best_bid=best_bid,
        best_ask=best_ask,
        bid_liquidity=bid_liquidity,
        ask_liquidity=ask_liquidity,
        volume_24h=float(metadata.get("total_depth", bid_liquidity + ask_liquidity)),
        num_traders=0,
        metadata={
            "category": category_name,
            "domain": domain,
            "market_family": market_family,
            "regime": regime,
            "feature_version": "resolved_dataset_v1",
        },
    )
    features = _build_snapshot_features(
        market=market,
        metadata=metadata,
        time_to_expiry_hours=float(record["time_to_expiry_hours"]),
    )
    merged_metadata = {
        "domain": domain,
        "market_family": market_family,
        "regime": regime,
        "feature_version": "resolved_dataset_v1",
        "category": category_name,
        "source_dataset": "resolved_markets",
    }
    merged_metadata.update(metadata)

    return ResolvedMarketSnapshot(
        market=market,
        venue=venue,
        outcome=int(record["outcome"]),
        observed_at=observed_at,
        context_metadata=merged_metadata,
        snapshot_features=features,
        metadata=merged_metadata,
    )


def _build_snapshot_features(
    *,
    market: MarketState,
    metadata: dict[str, Any],
    time_to_expiry_hours: float,
) -> dict[str, Any]:
    liquidity_tier = str(metadata.get("liquidity_tier", "unknown"))
    spread_tier = str(metadata.get("spread_tier", "unknown"))
    time_tier = str(metadata.get("time_tier", "unknown"))
    total_depth = float(metadata.get("total_depth", market.total_liquidity))

    return {
        "market_prob": market.market_prob,
        "spread_bps": market.spread_bps,
        "total_liquidity": total_depth,
        "time_to_expiry_hours": time_to_expiry_hours,
        "liquidity_tier": liquidity_tier,
        "spread_tier": spread_tier,
        "time_tier": time_tier,
        "liquidity_tier_score": _TIER_TO_SCORE.get(liquidity_tier, 0.5),
        "spread_tier_score": _TIER_TO_SCORE.get(spread_tier, 0.5),
        "time_tier_score": _TIER_TO_SCORE.get(time_tier, 0.5),
        "depth_imbalance": (
            (market.bid_liquidity - market.ask_liquidity) / max(market.total_liquidity, 1.0)
        ),
        "domain": str(market.metadata.get("domain", "generic")),
        "market_family": str(market.metadata.get("market_family", market.category.value)),
        "regime": str(market.metadata.get("regime", "steady")),
        "feature_version": "resolved_dataset_v1",
    }


def _derive_regime(metadata: dict[str, Any]) -> str:
    time_tier = str(metadata.get("time_tier", "steady")).lower()
    spread_tier = str(metadata.get("spread_tier", "")).lower()
    if time_tier == "short":
        return "short"
    if spread_tier == "wide":
        return "breaking_news"
    if metadata.get("liquidity_tier") == "micro":
        return "thin"
    return time_tier if time_tier and time_tier != "unknown" else "steady"


def _generate_question(market_id: str) -> str:
    stem = market_id
    suffix = stem.rsplit("-", 1)[-1]
    if suffix.isdigit():
        stem = stem.rsplit("-", 1)[0]
    words = stem.replace("-", " ").strip()
    return f"Will {words} resolve yes?"


def snapshot_questions(snapshots: Sequence[ResolvedMarketSnapshot]) -> tuple[str, ...]:
    """Return the generated or explicit question strings for loaded snapshots."""

    return tuple(snapshot.market.question for snapshot in snapshots)
