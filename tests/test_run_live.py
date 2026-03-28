"""Tests for the live trading runner."""

from __future__ import annotations

from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import sys

from autopredict.config import (
    BacktestConfig,
    ExperimentConfig,
    LoggingConfig,
    RiskConfig,
    StrategyConfig,
    VenueConfig,
)
from autopredict.core.types import (
    ExecutionReport,
    MarketCategory,
    MarketState,
    Order,
    OrderSide,
    OrderType,
)
from autopredict.live import LiveTrader, Monitor, RiskManager
from autopredict.prediction_market.types import AgentDecision, DecisionStatus, MarketSignal


ROOT = Path(__file__).resolve().parent.parent
_RUN_LIVE_SPEC = importlib.util.spec_from_file_location(
    "autopredict_run_live_script",
    ROOT / "scripts" / "run_live.py",
)
assert _RUN_LIVE_SPEC is not None and _RUN_LIVE_SPEC.loader is not None
run_live = importlib.util.module_from_spec(_RUN_LIVE_SPEC)
sys.modules[_RUN_LIVE_SPEC.name] = run_live
_RUN_LIVE_SPEC.loader.exec_module(run_live)


def _config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        name="live-cycle-test",
        strategy=StrategyConfig(
            name="routed_specialist",
            min_edge=0.01,
            kelly_fraction=1.0,
            max_position_pct=0.10,
            aggressive_edge=0.05,
            min_book_liquidity=10.0,
            max_spread_pct=0.20,
        ),
        risk=RiskConfig(
            max_position_per_market=1000.0,
            max_total_exposure=1000.0,
            max_daily_loss=100.0,
            kill_switch_threshold=-200.0,
            max_positions=10,
        ),
        venue=VenueConfig(
            name="polymarket",
            mode="live",
            api_key="test-key",
            api_secret="test-secret",
            testnet=True,
        ),
        backtest=BacktestConfig(
            initial_bankroll=1000.0,
            commission_rate=0.01,
        ),
        logging=LoggingConfig(
            log_dir=str(tmp_path / "logs"),
            console_output=False,
            performance_interval_minutes=60.0,
        ),
        metadata={
            "sync_positions_from_venue": False,
            "market_limit": 5,
        },
    )


def _market() -> MarketState:
    return MarketState(
        market_id="live-market-1",
        question="Will Congress pass the bill this week?",
        market_prob=0.45,
        expiry=datetime.now() + timedelta(days=3),
        category=MarketCategory.POLITICS,
        best_bid=0.44,
        best_ask=0.46,
        bid_liquidity=500.0,
        ask_liquidity=500.0,
        volume_24h=10000.0,
        num_traders=250,
        metadata={"tick_size": 0.01, "min_order_size": 1.0},
    )


class StubAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def evaluate_market(
        self,
        market,
        *,
        venue,
        portfolio,
        position=None,
        context_metadata=None,
        snapshot_features=None,
    ):
        self.calls.append(
            {
                "market": market,
                "venue": venue,
                "portfolio": portfolio,
                "position": position,
                "context_metadata": dict(context_metadata or {}),
                "snapshot_features": dict(snapshot_features or {}),
            }
        )
        signal = MarketSignal(
            fair_prob=0.68,
            confidence=0.90,
            rationale="stub edge",
            metadata={"model": "stub_model"},
        )
        order = Order(
            market_id=market.market_id,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=10.0,
            metadata={"strategy": "stub_strategy"},
        )
        return AgentDecision(
            market_id=market.market_id,
            status=DecisionStatus.TRADE,
            signal=signal,
            orders=(order,),
            metadata=dict(context_metadata or {}),
        )


class FilledVenueAdapter:
    def __init__(self, markets: list[MarketState]) -> None:
        self.markets = markets
        self.submitted: list[Order] = []
        self.last_filters: dict | None = None

    def validate_credentials(self, *, require_trading: bool = True) -> bool:
        return True

    def get_markets(self, filters: dict | None = None) -> list[MarketState]:
        self.last_filters = dict(filters or {})
        return list(self.markets)

    def submit_order(self, order: Order) -> ExecutionReport:
        self.submitted.append(order)
        return ExecutionReport(
            order=order,
            filled_size=order.size,
            avg_fill_price=0.46,
            fee_total=0.10,
            execution_mode="live",
            metadata={"status": "filled", "order_id": "ord-filled"},
        )

    def get_position(self, market_id: str) -> float:
        return 0.0

    def get_balance(self) -> float:
        return 1000.0


class RestingVenueAdapter(FilledVenueAdapter):
    def submit_order(self, order: Order) -> ExecutionReport:
        self.submitted.append(order)
        return ExecutionReport(
            order=order,
            filled_size=0.0,
            avg_fill_price=None,
            fee_total=0.0,
            execution_mode="live",
            metadata={"status": "open", "order_id": "ord-resting"},
        )


def test_run_live_cycle_fetches_decides_checks_risk_executes_and_logs(tmp_path: Path) -> None:
    """One live cycle should exercise the whole runtime path."""

    config = _config(tmp_path)
    agent = StubAgent()
    adapter = FilledVenueAdapter([_market()])
    monitor = Monitor(config.logging)
    risk_manager = RiskManager(config.risk)
    trader = LiveTrader(adapter, safety_checks=True, require_confirmation=False)

    resting_orders: dict[str, dict[str, object]] = {}
    result = run_live.run_live_cycle(
        config=config,
        agent=agent,
        live_trader=trader,
        venue_adapter=adapter,
        risk_manager=risk_manager,
        monitor=monitor,
        resting_orders=resting_orders,
    )

    assert result.markets_seen == 1
    assert result.decisions_logged >= 1
    assert result.orders_submitted == 1
    assert result.trades_filled == 1
    assert not resting_orders
    assert adapter.last_filters == {"limit": 5, "active_only": True, "min_liquidity": 10.0}
    assert len(adapter.submitted) == 1
    assert risk_manager.positions["live-market-1"].size == 10.0
    assert monitor.trade_count == 1
    assert monitor.decision_count >= 1
    assert agent.calls[0]["context_metadata"]["domain"] == "politics"
    assert agent.calls[0]["snapshot_features"]["spread_bps"] > 0.0
    assert (Path(config.logging.log_dir) / "trades.jsonl").read_text().strip()
    assert (Path(config.logging.log_dir) / "decisions.jsonl").read_text().strip()


def test_run_live_cycle_tracks_resting_orders_without_fill(tmp_path: Path) -> None:
    """Unfilled live orders with venue ids should be tracked as resting orders."""

    config = _config(tmp_path)
    agent = StubAgent()
    adapter = RestingVenueAdapter([_market()])
    monitor = Monitor(config.logging)
    risk_manager = RiskManager(config.risk)
    trader = LiveTrader(adapter, safety_checks=True, require_confirmation=False)

    resting_orders: dict[str, dict[str, object]] = {}
    result = run_live.run_live_cycle(
        config=config,
        agent=agent,
        live_trader=trader,
        venue_adapter=adapter,
        risk_manager=risk_manager,
        monitor=monitor,
        resting_orders=resting_orders,
    )

    assert result.orders_submitted == 1
    assert result.trades_filled == 0
    assert result.resting_orders == 1
    assert resting_orders["live-market-1"]["order_id"] == "ord-resting"
