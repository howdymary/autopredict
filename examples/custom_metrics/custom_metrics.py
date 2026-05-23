"""Custom metrics extension for AutoPredict."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from autopredict.market_env import TradeRecord


def calculate_profit_factor(trades: list[TradeRecord]) -> float:
    """
    Calculate profit factor: gross profit / gross loss.

    Profit factor > 1.0 means winners are bigger than losers.
    """
    if not trades:
        return 0.0

    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))

    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def calculate_consecutive_metrics(trades: list[TradeRecord]) -> dict[str, float]:
    """
    Calculate consecutive wins/losses streaks.

    Returns:
        - max_consecutive_wins: Longest winning streak
        - max_consecutive_losses: Longest losing streak
        - current_streak: Current streak (positive for wins, negative for losses)
    """
    if not trades:
        return {
            "max_consecutive_wins": 0.0,
            "max_consecutive_losses": 0.0,
            "current_streak": 0.0,
        }

    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0

    for trade in trades:
        if trade.pnl > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        elif trade.pnl < 0:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)

    # Calculate current streak
    if current_wins > 0:
        current_streak = current_wins
    elif current_losses > 0:
        current_streak = -current_losses
    else:
        current_streak = 0

    return {
        "max_consecutive_wins": float(max_wins),
        "max_consecutive_losses": float(max_losses),
        "current_streak": float(current_streak),
    }


def calculate_win_loss_sizes(trades: list[TradeRecord]) -> dict[str, float]:
    """
    Calculate average win and loss sizes.

    Returns:
        - avg_win_size: Average profit on winning trades
        - avg_loss_size: Average loss on losing trades (absolute value)
        - win_loss_ratio: Ratio of average win to average loss
    """
    if not trades:
        return {
            "avg_win_size": 0.0,
            "avg_loss_size": 0.0,
            "win_loss_ratio": 0.0,
        }

    winners = [t.pnl for t in trades if t.pnl > 0]
    losers = [abs(t.pnl) for t in trades if t.pnl < 0]

    avg_win = sum(winners) / len(winners) if winners else 0.0
    avg_loss = sum(losers) / len(losers) if losers else 0.0

    win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

    return {
        "avg_win_size": avg_win,
        "avg_loss_size": avg_loss,
        "win_loss_ratio": win_loss_ratio,
    }


def calculate_all_custom_metrics(trades: list[TradeRecord]) -> dict[str, float]:
    """Calculate all custom metrics and return as dict."""
    metrics = {}

    metrics["profit_factor"] = calculate_profit_factor(trades)
    metrics.update(calculate_consecutive_metrics(trades))
    metrics.update(calculate_win_loss_sizes(trades))

    return metrics


def load_trade_records(path: Path) -> list[TradeRecord]:
    """Load real trade records from JSON or JSONL.

    JSON input may be either a list of trade objects or an object with a
    ``trades`` list. JSONL input expects one trade object per non-empty line.
    """

    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        raw_records: Any = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        raw_records = json.loads(text)

    if isinstance(raw_records, dict):
        raw_records = raw_records.get("trades")

    if not isinstance(raw_records, list):
        raise ValueError("trade input must be a list or an object with a 'trades' list")

    trade_fields = {field.name for field in fields(TradeRecord)}
    trades: list[TradeRecord] = []
    for index, raw in enumerate(raw_records, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"trade record {index} must be an object")

        missing = sorted(trade_fields.difference(raw))
        if missing:
            raise ValueError(f"trade record {index} is missing required fields: {', '.join(missing)}")

        trades.append(TradeRecord(**{name: raw[name] for name in trade_fields}))

    return trades


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calculate custom metrics for real trade records")
    parser.add_argument(
        "--trades",
        required=True,
        help="Path to JSON or JSONL trade records produced from a real backtest or execution log",
    )
    args = parser.parse_args(argv)

    metrics = calculate_all_custom_metrics(load_trade_records(Path(args.trades)))

    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
