"""Experiment loop for evaluating AutoPredict agents on prediction market snapshots."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .agent import AutoPredictAgent, MarketState
from .market_env import BookLevel, ExecutionEngine, ForecastRecord, OrderBook, TradeRecord, evaluate_all


def _load_json(path: str | Path) -> dict | list:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validate_probability(value: object, field_name: str) -> float:
    probability = float(value)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError(f"{field_name} must be a finite probability in [0, 1], got {value!r}")
    return probability


def _validate_non_negative_float(value: object, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative float, got {value!r}")
    return number


def _build_levels(market_id: str, side: str, raw_levels: object) -> list[BookLevel]:
    if raw_levels is None:
        return []
    if not isinstance(raw_levels, list):
        raise TypeError(f"{market_id} {side} levels must be a list, got {type(raw_levels).__name__}")

    levels: list[BookLevel] = []
    for index, level in enumerate(raw_levels):
        if not isinstance(level, (list, tuple)) or len(level) != 2:
            raise ValueError(
                f"{market_id} {side}[{index}] must be a [price, size] pair, got {level!r}"
            )
        price = _validate_probability(level[0], f"{market_id} {side}[{index}] price")
        size = float(level[1])
        if not math.isfinite(size) or size <= 0.0:
            raise ValueError(f"{market_id} {side}[{index}] size must be a finite positive float, got {level[1]!r}")
        levels.append(BookLevel(price=price, size=size))

    return levels


def _build_order_book(market_id: str, payload: dict[str, list[list[float]]]) -> OrderBook:
    if not isinstance(payload, dict):
        raise TypeError(f"{market_id} order_book must be an object, got {type(payload).__name__}")

    book = OrderBook(
        market_id=market_id,
        bids=_build_levels(market_id, "bids", payload.get("bids", [])),
        asks=_build_levels(market_id, "asks", payload.get("asks", [])),
        depth_levels=10,
    )
    if book.bids and book.asks and book.bids[0].price > book.asks[0].price:
        raise ValueError(
            f"{market_id} has a crossed order book: best bid {book.bids[0].price:.4f} "
            f"> best ask {book.asks[0].price:.4f}"
        )
    return book


def _realized_pnl(side: str, fill_price: float, outcome: int, filled_size: float) -> float:
    if side == "buy":
        return (float(outcome) - fill_price) * filled_size
    return (fill_price - float(outcome)) * filled_size


def run_backtest(
    *,
    config_path: str | Path,
    dataset_path: str | Path,
    strategy_guidance_path: str | Path | None = None,
    starting_bankroll: float = 1_000.0,
) -> dict[str, object]:
    """Run a simple prediction market backtest and return combined metrics."""

    config = _load_json(config_path)
    dataset = _load_json(dataset_path)
    if not isinstance(config, dict):
        raise TypeError("Strategy config must be a JSON object")
    if not isinstance(dataset, list):
        raise TypeError("Dataset must be a JSON array")

    guidance = ""
    if strategy_guidance_path and Path(strategy_guidance_path).exists():
        guidance = Path(strategy_guidance_path).read_text(encoding="utf-8")

    agent = AutoPredictAgent.from_mapping(config)
    engine = ExecutionEngine()
    bankroll = starting_bankroll
    forecasts: list[ForecastRecord] = []
    trades: list[TradeRecord] = []

    for index, record in enumerate(dataset):
        if not isinstance(record, dict):
            raise TypeError(f"Dataset record {index} must be an object, got {type(record).__name__}")

        market_id = str(record["market_id"]).strip()
        if not market_id:
            raise ValueError(f"Dataset record {index} has an empty market_id")

        market_prob = _validate_probability(record["market_prob"], f"{market_id} market_prob")
        fair_prob = _validate_probability(record["fair_prob"], f"{market_id} fair_prob")
        outcome = int(record["outcome"])
        if outcome not in (0, 1):
            raise ValueError(f"{market_id} outcome must be 0 or 1, got {record['outcome']!r}")
        next_mid = _validate_probability(record.get("next_mid_price", market_prob), f"{market_id} next_mid_price")
        expiry_hours = _validate_non_negative_float(
            record.get("time_to_expiry_hours", 24.0),
            f"{market_id} time_to_expiry_hours",
        )
        order_book = _build_order_book(market_id, record["order_book"])

        state = MarketState(
            market_id=market_id,
            market_prob=market_prob,
            fair_prob=fair_prob,
            time_to_expiry_hours=expiry_hours,
            order_book=order_book,
            metadata={"category": record.get("category", "unknown")},
        )
        forecasts.append(ForecastRecord(market_id=market_id, probability=fair_prob, outcome=outcome))

        proposal = agent.evaluate_market(state, bankroll)
        if proposal is None:
            continue

        order_sizes = proposal.split_sizes or [proposal.size]
        for order_size in order_sizes:
            if proposal.order_type == "market":
                report = engine.execute_market_order(order_size, proposal.side, order_book)
            else:
                report = engine.execute_limit_order(
                    price=float(proposal.limit_price or order_book.get_mid_price()),
                    size=order_size,
                    side=proposal.side,
                    order_book=order_book,
                    time_in_force="GTC",
                )

            if report.filled_size <= 0 or report.average_fill_price is None:
                continue

            pnl = _realized_pnl(
                side=proposal.side,
                fill_price=report.average_fill_price,
                outcome=outcome,
                filled_size=report.filled_size,
            )
            bankroll += pnl
            trades.append(
                TradeRecord(
                    market_id=market_id,
                    side=proposal.side,
                    order_type=proposal.order_type,
                    requested_size=report.requested_size,
                    filled_size=report.filled_size,
                    fill_price=report.average_fill_price,
                    mid_at_decision=report.reference_mid_price,
                    next_mid_price=next_mid,
                    outcome=outcome,
                    pnl=pnl,
                    slippage_bps=report.slippage_bps,
                    market_impact_bps=report.market_impact_bps,
                    implementation_shortfall_bps=report.implementation_shortfall_bps,
                    fill_rate=report.fill_rate,
                )
            )

    metrics = evaluate_all(forecasts, trades)
    metrics["starting_bankroll"] = starting_bankroll
    metrics["ending_bankroll"] = bankroll
    metrics["agent_feedback"] = agent.analyze_performance(metrics, guidance)
    return metrics
