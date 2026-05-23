"""Backtesting helpers for the package-native prediction-market scaffold."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from autopredict.core.types import MarketState, Order, Portfolio, Position
from autopredict.domains.base import DomainFeatureBundle
from autopredict.evaluation.scoring import (
    BinaryForecast,
    ProperScoringRules,
    ScoringReport,
)
from autopredict.prediction_market import (
    AgentDecision,
    PredictionMarketAgent,
    VenueConfig,
)

EPSILON = 1e-9
BPS_MULTIPLIER = 10_000.0


@dataclass(frozen=True)
class ExecutionAssumptions:
    """Deterministic execution assumptions for Step 2 scaffold backtests."""

    market_impact_spread_fraction: float = 0.5
    maker_fee_fraction: float = 0.5

    def __post_init__(self) -> None:
        if not (0.0 <= self.market_impact_spread_fraction <= 1.0):
            raise ValueError(
                "market_impact_spread_fraction must be in [0, 1], "
                f"got {self.market_impact_spread_fraction}"
            )
        if not (0.0 <= self.maker_fee_fraction <= 1.0):
            raise ValueError(
                "maker_fee_fraction must be in [0, 1], "
                f"got {self.maker_fee_fraction}"
            )


@dataclass(frozen=True)
class ResolvedMarketSnapshot:
    """One scaffold market plus realized outcome for backtesting."""

    market: MarketState
    venue: VenueConfig
    outcome: int
    observed_at: datetime = field(default_factory=datetime.now)
    context_metadata: dict[str, Any] = field(default_factory=dict)
    snapshot_features: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    domain_bundle: DomainFeatureBundle | None = None

    def __post_init__(self) -> None:
        if self.outcome not in (0, 1):
            raise ValueError(f"outcome must be 0 or 1, got {self.outcome}")

    def merged_context_metadata(self) -> dict[str, Any]:
        """Return runtime context metadata merged with an optional domain bundle."""

        merged = dict(self.domain_bundle.metadata) if self.domain_bundle is not None else {}
        merged.update(self.context_metadata)
        return merged

    def merged_snapshot_features(self) -> dict[str, Any]:
        """Return snapshot features merged with an optional domain bundle."""

        merged = dict(self.domain_bundle.features) if self.domain_bundle is not None else {}
        merged.update(self.snapshot_features)
        return merged

    def merged_metadata(self) -> dict[str, Any]:
        """Return evaluation metadata merged with an optional domain bundle."""

        merged = dict(self.domain_bundle.metadata) if self.domain_bundle is not None else {}
        merged.update(self.metadata)
        merged.setdefault("category", self.market.category.value)
        return merged


@dataclass(frozen=True)
class BacktestTrade:
    """Simulated execution outcome for one order."""

    market_id: str
    venue: str
    side: str
    order_type: str
    requested_size: float
    filled_size: float
    fill_price: float
    reference_price: float
    outcome: int
    pnl: float
    fee_paid: float
    slippage_bps: float
    fill_rate: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_filled(self) -> bool:
        """Return whether any size was filled."""

        return self.filled_size > EPSILON


@dataclass(frozen=True)
class BacktestResult:
    """Full backtest output for the scaffold-level evaluation layer."""

    decisions: tuple[AgentDecision, ...]
    forecasts: tuple[BinaryForecast, ...]
    trades: tuple[BacktestTrade, ...]
    scoring: ScoringReport
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result for reporting and snapshots."""

        return {
            "metrics": self.metrics,
            "scoring": self.scoring.to_dict(),
            "num_decisions": len(self.decisions),
            "num_forecasts": len(self.forecasts),
            "num_trades": len(self.trades),
        }


class PredictionMarketBacktester:
    """Deterministic backtester for the new prediction-market scaffold."""

    def __init__(self, assumptions: ExecutionAssumptions | None = None) -> None:
        self.assumptions = assumptions or ExecutionAssumptions()

    def run(
        self,
        agent: PredictionMarketAgent,
        snapshots: Sequence[ResolvedMarketSnapshot],
        *,
        starting_cash: float = 1000.0,
    ) -> BacktestResult:
        """Run a scaffold backtest over resolved market snapshots."""

        portfolio = Portfolio(cash=starting_cash, starting_capital=starting_cash)
        decisions: list[AgentDecision] = []
        forecasts: list[BinaryForecast] = []
        trades: list[BacktestTrade] = []

        for snapshot in snapshots:
            merged_context = snapshot.merged_context_metadata()
            merged_features = snapshot.merged_snapshot_features()
            merged_metadata = snapshot.merged_metadata()
            decision = agent.evaluate_market(
                snapshot.market,
                venue=snapshot.venue,
                portfolio=portfolio,
                context_metadata=merged_context,
                snapshot_features=merged_features,
            )
            decisions.append(decision)

            if decision.signal is not None:
                forecasts.append(
                    BinaryForecast(
                        market_id=snapshot.market.market_id,
                        probability=decision.signal.fair_prob,
                        outcome=snapshot.outcome,
                        metadata={
                            **merged_metadata,
                            **decision.signal.metadata,
                            "confidence": decision.signal.confidence,
                            "venue": snapshot.venue.name.value,
                        },
                    )
                )

            for order in decision.orders:
                trade = self._simulate_trade(order, snapshot)
                trades.append(trade)
                self._apply_trade_to_portfolio(portfolio, trade, snapshot.market.market_prob)

        scoring = ProperScoringRules.evaluate_binary_forecasts(forecasts)
        metrics = self._aggregate_metrics(
            decisions=decisions,
            trades=trades,
            scoring=scoring,
            num_markets=len(snapshots),
            ending_cash=portfolio.cash,
        )
        return BacktestResult(
            decisions=tuple(decisions),
            forecasts=tuple(forecasts),
            trades=tuple(trades),
            scoring=scoring,
            metrics=metrics,
        )

    def _simulate_trade(
        self,
        order: Order,
        snapshot: ResolvedMarketSnapshot,
    ) -> BacktestTrade:
        market = snapshot.market
        reference_price = market.mid_price
        spread = max(market.best_ask - market.best_bid, 0.0)
        is_buy = order.side.value == "buy"
        best_price = market.best_ask if is_buy else market.best_bid
        available_liquidity = market.ask_liquidity if is_buy else market.bid_liquidity
        available_liquidity = max(available_liquidity, 0.0)
        requested_size = order.size

        marketable = order.order_type.value == "market"
        if order.order_type.value == "limit" and order.limit_price is not None:
            if is_buy and order.limit_price >= market.best_ask:
                marketable = True
            if not is_buy and order.limit_price <= market.best_bid:
                marketable = True

        if marketable:
            filled_size = min(requested_size, available_liquidity)
            liquidity_ratio = filled_size / max(available_liquidity, 1.0)
            impact = spread * self.assumptions.market_impact_spread_fraction * liquidity_ratio
            raw_fill_price = best_price + impact if is_buy else best_price - impact
            fill_price = min(max(raw_fill_price, 0.0), 1.0)
            fee_bps = snapshot.venue.fee_bps
        else:
            limit_price = order.limit_price if order.limit_price is not None else reference_price
            if spread <= EPSILON:
                aggressiveness = 1.0
            elif is_buy:
                aggressiveness = (limit_price - market.best_bid) / spread
            else:
                aggressiveness = (market.best_ask - limit_price) / spread

            aggressiveness = min(max(aggressiveness, 0.0), 1.0)
            fill_ratio = aggressiveness * min(1.0, available_liquidity / max(requested_size, 1.0))
            filled_size = min(requested_size * fill_ratio, available_liquidity)
            fill_price = limit_price
            fee_bps = snapshot.venue.fee_bps * self.assumptions.maker_fee_fraction

        fee_paid = filled_size * fill_price * (fee_bps / BPS_MULTIPLIER)
        fill_rate = filled_size / requested_size if requested_size > 0 else 0.0
        if filled_size <= EPSILON or reference_price <= EPSILON:
            slippage_bps = 0.0
        elif is_buy:
            slippage_bps = max(fill_price - reference_price, 0.0) / reference_price * BPS_MULTIPLIER
        else:
            slippage_bps = max(reference_price - fill_price, 0.0) / reference_price * BPS_MULTIPLIER

        if is_buy:
            pnl = filled_size * (snapshot.outcome - fill_price) - fee_paid
        else:
            pnl = filled_size * (fill_price - snapshot.outcome) - fee_paid

        return BacktestTrade(
            market_id=order.market_id,
            venue=snapshot.venue.name.value,
            side=order.side.value,
            order_type=order.order_type.value,
            requested_size=requested_size,
            filled_size=filled_size,
            fill_price=fill_price,
            reference_price=reference_price,
            outcome=snapshot.outcome,
            pnl=pnl,
            fee_paid=fee_paid,
            slippage_bps=slippage_bps,
            fill_rate=fill_rate,
            metadata={
                **snapshot.merged_metadata(),
                **order.metadata,
                "marketable": marketable,
            },
        )

    def _apply_trade_to_portfolio(
        self,
        portfolio: Portfolio,
        trade: BacktestTrade,
        current_price: float,
    ) -> None:
        if trade.filled_size <= EPSILON:
            return

        signed_size = trade.filled_size if trade.side == "buy" else -trade.filled_size
        cash_delta = -trade.fee_paid
        if trade.side == "buy":
            cash_delta -= trade.filled_size * trade.fill_price
        else:
            cash_delta += trade.filled_size * trade.fill_price
        portfolio.update_cash(cash_delta)

        existing = portfolio.positions.get(trade.market_id)
        if existing is None:
            portfolio.add_position(
                Position(
                    market_id=trade.market_id,
                    size=signed_size,
                    entry_price=trade.fill_price,
                    current_price=current_price,
                )
            )
            return

        new_size = existing.size + signed_size
        if abs(new_size) <= EPSILON:
            portfolio.remove_position(trade.market_id)
            return

        total_abs_size = abs(existing.size) + abs(signed_size)
        if total_abs_size <= EPSILON:
            entry_price = trade.fill_price
        else:
            entry_price = (
                existing.entry_price * abs(existing.size) + trade.fill_price * abs(signed_size)
            ) / total_abs_size

        portfolio.add_position(
            Position(
                market_id=trade.market_id,
                size=new_size,
                entry_price=entry_price,
                current_price=current_price,
            )
        )

    @staticmethod
    def _aggregate_metrics(
        *,
        decisions: Sequence[AgentDecision],
        trades: Sequence[BacktestTrade],
        scoring: ScoringReport,
        num_markets: int,
        ending_cash: float,
    ) -> dict[str, Any]:
        filled_trades = [trade for trade in trades if trade.is_filled]
        pnls = [trade.pnl for trade in filled_trades]
        wins = [trade for trade in filled_trades if trade.pnl > 0]

        return {
            "num_markets": num_markets,
            "num_decisions": len(decisions),
            "num_forecasts": scoring.count,
            "num_trade_decisions": sum(1 for decision in decisions if decision.should_trade),
            "num_trades": len(trades),
            "num_filled_trades": len(filled_trades),
            "total_pnl": sum(pnls),
            "total_fees": sum(trade.fee_paid for trade in filled_trades),
            "ending_cash": ending_cash,
            "win_rate": len(wins) / len(filled_trades) if filled_trades else 0.0,
            "avg_fill_rate": (
                statistics.fmean(trade.fill_rate for trade in trades) if trades else 0.0
            ),
            "avg_slippage_bps": (
                statistics.fmean(trade.slippage_bps for trade in filled_trades)
                if filled_trades
                else 0.0
            ),
            "brier_score": scoring.brier_score,
            "log_score": scoring.log_score,
            "log_loss": scoring.log_loss,
            "spherical_score": scoring.spherical_score,
            "mean_absolute_calibration_gap": scoring.calibration.mean_absolute_gap,
        }
