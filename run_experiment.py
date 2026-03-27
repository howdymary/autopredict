"""Experiment loop for evaluating AutoPredict agents on prediction market snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from .agent import AutoPredictAgent, MarketState
from .market_env import BookLevel, ExecutionEngine, ForecastRecord, OrderBook, TradeRecord, evaluate_all


def _load_json(path: str | Path) -> dict | list:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_order_book(market_id: str, payload: dict[str, list[list[float]]]) -> OrderBook:
    return OrderBook(
        market_id=market_id,
        bids=[BookLevel(price=float(price), size=float(size)) for price, size in payload.get("bids", [])],
        asks=[BookLevel(price=float(price), size=float(size)) for price, size in payload.get("asks", [])],
        depth_levels=10,
    )


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

    for record in dataset:
        if not isinstance(record, dict):
            continue

        market_id = str(record["market_id"])
        market_prob = float(record["market_prob"])
        fair_prob = float(record["fair_prob"])
        outcome = int(record["outcome"])
        next_mid = float(record.get("next_mid_price", market_prob))
        expiry_hours = float(record.get("time_to_expiry_hours", 24.0))
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
