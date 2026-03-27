"""Custom metrics extension for AutoPredict."""

from __future__ import annotations

import sys
from pathlib import Path

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


if __name__ == "__main__":
    # Demonstrate custom metrics on sample trades
    from autopredict.market_env import TradeRecord

    sample_trades = [
        TradeRecord(
            market_id="test1",
            side="buy",
            order_type="market",
            requested_size=10.0,
            filled_size=10.0,
            fill_price=0.52,
            mid_at_decision=0.50,
            next_mid_price=0.55,
            outcome=1,
            pnl=4.8,  # Win
            slippage_bps=200.0,
            market_impact_bps=100.0,
            implementation_shortfall_bps=200.0,
            fill_rate=1.0,
        ),
        TradeRecord(
            market_id="test2",
            side="sell",
            order_type="limit",
            requested_size=10.0,
            filled_size=10.0,
            fill_price=0.48,
            mid_at_decision=0.50,
            next_mid_price=0.45,
            outcome=0,
            pnl=4.8,  # Win
            slippage_bps=-200.0,
            market_impact_bps=0.0,
            implementation_shortfall_bps=-200.0,
            fill_rate=1.0,
        ),
        TradeRecord(
            market_id="test3",
            side="buy",
            order_type="market",
            requested_size=10.0,
            filled_size=10.0,
            fill_price=0.52,
            mid_at_decision=0.50,
            next_mid_price=0.45,
            outcome=0,
            pnl=-5.2,  # Loss
            slippage_bps=200.0,
            market_impact_bps=100.0,
            implementation_shortfall_bps=200.0,
            fill_rate=1.0,
        ),
    ]

    metrics = calculate_all_custom_metrics(sample_trades)

    print("Custom Metrics Demo:")
    print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"  Max Consecutive Wins: {int(metrics['max_consecutive_wins'])}")
    print(f"  Max Consecutive Losses: {int(metrics['max_consecutive_losses'])}")
    print(f"  Current Streak: {int(metrics['current_streak'])}")
    print(f"  Avg Win Size: ${metrics['avg_win_size']:.2f}")
    print(f"  Avg Loss Size: ${metrics['avg_loss_size']:.2f}")
    print(f"  Win/Loss Ratio: {metrics['win_loss_ratio']:.2f}")
