#!/usr/bin/env python3
"""Live trading runner for AutoPredict.

DANGER: This script executes REAL trades with REAL money.

Multiple safety checks are in place:
1. Configuration must explicitly set mode='live'
2. User must confirm live trading at startup
3. All risk limits are enforced
4. Kill switch activates on severe losses
5. All activity is logged

Usage:
    # Dry run (no actual trades)
    python scripts/run_live.py --config configs/live_trading.yaml --dry-run

    # Live run (requires confirmation)
    python scripts/run_live.py --config configs/live_trading.yaml
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
import time
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autopredict.config import load_config, validate_config
from autopredict.config.loader import collect_missing_env_vars
from autopredict.core.types import MarketCategory, OrderSide, Portfolio, Position as CorePosition
from autopredict.domains import RoutedSpecialistStrategy, SpecialistOrderPolicy
from autopredict.live import LiveTrader, Monitor, RiskManager
from autopredict.live.monitor import PerformanceSnapshot, create_decision_log, create_trade_log
from autopredict.live.risk import Position as RiskPosition
from autopredict.markets import PolymarketAdapter
from autopredict.prediction_market import AgentRunConfig, PredictionMarketAgent
from autopredict.prediction_market.types import DecisionStatus, VenueConfig as ScaffoldVenueConfig, VenueName


_WEATHER_KEYWORDS = (
    "weather",
    "temperature",
    "rain",
    "snow",
    "storm",
    "hurricane",
    "tornado",
    "precipitation",
    "wind",
    "flood",
    "heat",
    "cold",
    "landfall",
)
_FINANCE_CRYPTO_KEYWORDS = ("bitcoin", "btc", "ethereum", "eth", "solana", "crypto")
_FINANCE_RATES_KEYWORDS = (
    "fed",
    "rates",
    "yield",
    "treasury",
    "bond",
    "fomc",
    "cut",
    "hike",
)
_FINANCE_MACRO_KEYWORDS = (
    "cpi",
    "inflation",
    "payroll",
    "gdp",
    "recession",
    "macro",
    "economy",
    "tariff",
    "earnings",
)
_POLITICS_APPROVAL_KEYWORDS = ("approval", "approve", "disapprove", "poll")
_POLITICS_ELECTION_KEYWORDS = (
    "election",
    "president",
    "senate",
    "house",
    "governor",
    "vote",
    "campaign",
    "debate",
    "primary",
)
_POLITICS_LEGISLATION_KEYWORDS = ("bill", "law", "legislation", "budget", "congress")
_POLITICS_GEOPOLITICS_KEYWORDS = (
    "ceasefire",
    "war",
    "ukraine",
    "russia",
    "china",
    "taiwan",
    "israel",
    "gaza",
    "nato",
    "treaty",
)
_BREAKING_NEWS_KEYWORDS = ("breaking", "urgent", "indicted", "resign", "ceasefire", "tariff")


@dataclass
class LiveCycleResult:
    """Summary of one live fetch-decide-risk-check-execute cycle."""

    markets_seen: int = 0
    decisions_logged: int = 0
    orders_submitted: int = 0
    trades_filled: int = 0
    blocked_orders: int = 0
    resting_orders: int = 0
    errors: int = 0
    available_cash: float = 0.0


def _create_venue_adapter(config, *, dry_run: bool = False):
    """Resolve a venue adapter for live or dry-run execution."""
    venue_name = str(config.venue.name).lower()

    if venue_name == "polymarket":
        adapter = PolymarketAdapter.from_env(
            api_key=config.venue.api_key,
            api_secret=config.venue.api_secret,
            base_url=config.venue.base_url,
            timeout_seconds=config.venue.timeout_seconds,
            testnet=config.venue.testnet,
        )
        adapter.validate_credentials(require_trading=not dry_run)
        return adapter
    if venue_name == "manifold":
        raise SystemExit(
            "Live trading for Manifold is not implemented in this repository yet. "
            "The current adapter is a scaffold and cannot safely submit real orders."
        )

    raise SystemExit(
        f"Live trading for venue '{config.venue.name}' is not available. "
        "Use paper mode or implement a real adapter first."
    )


def _venue_name(name: str) -> VenueName:
    try:
        return VenueName(str(name).lower())
    except ValueError:
        return VenueName.CUSTOM


def _scaffold_venue_config(config, market) -> ScaffoldVenueConfig:
    tick_size = float(market.metadata.get("tick_size", 0.01) or 0.01)
    min_order_size = float(market.metadata.get("min_order_size", 1.0) or 1.0)
    return ScaffoldVenueConfig(
        name=_venue_name(config.venue.name),
        fee_bps=float(config.backtest.commission_rate) * 10_000.0,
        tick_size=max(tick_size, 1e-6),
        min_order_size=max(min_order_size, 1e-6),
        metadata={
            "mode": config.venue.mode,
            "testnet": config.venue.testnet,
            "max_requests_per_minute": config.venue.max_requests_per_minute,
        },
    )


def _build_live_agent(config) -> PredictionMarketAgent:
    max_bankroll_fraction = max(
        0.001,
        min(config.strategy.max_position_pct * config.strategy.kelly_fraction, 1.0),
    )
    policy = SpecialistOrderPolicy(
        min_abs_edge=config.strategy.min_edge,
        max_bankroll_fraction=max_bankroll_fraction,
        aggressive_edge=max(config.strategy.aggressive_edge, config.strategy.min_edge),
    )
    min_signal_confidence = float(config.metadata.get("min_signal_confidence", 0.5))
    return PredictionMarketAgent(
        strategy=RoutedSpecialistStrategy(policy=policy),
        config=AgentRunConfig(min_signal_confidence=min_signal_confidence),
    )


def _available_cash_fallback(config, risk_manager: RiskManager) -> float:
    return max(
        config.backtest.initial_bankroll
        + risk_manager.total_pnl
        - risk_manager.get_current_exposure(),
        0.0,
    )


def _resolve_available_cash(config, venue_adapter, risk_manager: RiskManager, monitor: Monitor) -> float:
    if hasattr(venue_adapter, "get_balance"):
        try:
            return max(float(venue_adapter.get_balance()), 0.0)
        except Exception as exc:
            monitor.warning(
                f"Falling back to local cash estimate after venue balance lookup failed: {exc}"
            )
    return _available_cash_fallback(config, risk_manager)


def _portfolio_from_risk(risk_manager: RiskManager, *, cash: float, starting_capital: float) -> Portfolio:
    positions = {
        market_id: CorePosition(
            market_id=market_id,
            size=position.size,
            entry_price=position.entry_price,
            current_price=position.current_price,
            timestamp=position.entry_time,
            metadata=dict(position.metadata),
        )
        for market_id, position in risk_manager.positions.items()
    }
    return Portfolio(
        cash=max(cash, 0.0),
        positions=positions,
        starting_capital=starting_capital,
        metadata={"source": "live_risk_manager"},
    )


def _infer_domain(market) -> str:
    question = market.question.lower()
    if any(keyword in question for keyword in _WEATHER_KEYWORDS):
        return "weather"
    if market.category in {MarketCategory.ECONOMICS, MarketCategory.CRYPTO}:
        return "finance"
    if market.category == MarketCategory.POLITICS:
        return "politics"
    if any(keyword in question for keyword in _FINANCE_CRYPTO_KEYWORDS + _FINANCE_RATES_KEYWORDS + _FINANCE_MACRO_KEYWORDS):
        return "finance"
    if any(
        keyword in question
        for keyword in (
            _POLITICS_APPROVAL_KEYWORDS
            + _POLITICS_ELECTION_KEYWORDS
            + _POLITICS_LEGISLATION_KEYWORDS
            + _POLITICS_GEOPOLITICS_KEYWORDS
        )
    ):
        return "politics"
    return "generic"


def _infer_market_family(market, domain: str) -> str:
    question = market.question.lower()
    if domain == "finance":
        if any(keyword in question for keyword in _FINANCE_CRYPTO_KEYWORDS):
            return "crypto"
        if any(keyword in question for keyword in _FINANCE_RATES_KEYWORDS):
            return "rates"
        if any(keyword in question for keyword in _FINANCE_MACRO_KEYWORDS):
            return "macro"
        return "equities"
    if domain == "weather":
        if any(keyword in question for keyword in ("hurricane", "storm", "tornado", "wind", "landfall")):
            return "storm"
        if any(keyword in question for keyword in ("rain", "snow", "precipitation", "flood")):
            return "precipitation"
        return "temperature"
    if domain == "politics":
        if any(keyword in question for keyword in _POLITICS_APPROVAL_KEYWORDS):
            return "approval"
        if any(keyword in question for keyword in _POLITICS_GEOPOLITICS_KEYWORDS):
            return "geopolitics"
        if any(keyword in question for keyword in _POLITICS_LEGISLATION_KEYWORDS):
            return "legislation"
        return "elections"
    return market.category.value


def _infer_regime(market, config, domain: str) -> str:
    question = market.question.lower()
    spread_bps = market.spread_bps
    hours = market.time_to_expiry_hours

    if any(keyword in question for keyword in _BREAKING_NEWS_KEYWORDS):
        return "breaking_news"
    if domain == "weather":
        if "warning" in question:
            return "warning"
        if "watch" in question:
            return "watch"
        if hours <= 24:
            return "short"
        return "calm"
    if domain == "finance":
        if spread_bps >= max(config.strategy.max_spread_pct * 10_000.0, 400.0):
            return "high_vol"
        if hours <= 72 and any(keyword in question for keyword in _FINANCE_MACRO_KEYWORDS + _FINANCE_RATES_KEYWORDS):
            return "post_release"
        if hours <= 24:
            return "short"
        return "steady"
    if domain == "politics":
        if "debate" in question:
            return "debate_week"
        if hours <= 168 and any(keyword in question for keyword in _POLITICS_ELECTION_KEYWORDS):
            return "election_week"
        if hours <= 24:
            return "short"
        return "quiet"
    if spread_bps >= max(config.strategy.max_spread_pct * 10_000.0, 400.0):
        return "wide_spread"
    if market.total_liquidity < config.strategy.min_book_liquidity:
        return "thin_book"
    if hours <= 24:
        return "short"
    return "steady"


def _build_live_snapshot_inputs(market, config) -> tuple[dict[str, Any], dict[str, Any]]:
    domain = _infer_domain(market)
    market_family = _infer_market_family(market, domain)
    regime = _infer_regime(market, config, domain)
    total_liquidity = max(market.total_liquidity, 0.0)
    imbalance = 0.0
    if total_liquidity > 0:
        imbalance = (market.bid_liquidity - market.ask_liquidity) / total_liquidity
    spread_pct = 0.0
    if market.mid_price > 0:
        spread_pct = market.spread / market.mid_price

    features = {
        "market_prob": market.market_prob,
        "mid_price": market.mid_price,
        "spread_bps": market.spread_bps,
        "spread_pct": spread_pct,
        "total_liquidity": total_liquidity,
        "bid_liquidity": market.bid_liquidity,
        "ask_liquidity": market.ask_liquidity,
        "liquidity_imbalance": imbalance,
        "volume_24h": market.volume_24h,
        "time_to_expiry_hours": market.time_to_expiry_hours,
        "num_traders": market.num_traders,
        "category": market.category.value,
    }
    metadata = {
        "domain": domain,
        "market_family": market_family,
        "regime": regime,
        "feature_version": "live_v1",
        "category": market.category.value,
        "venue": str(config.venue.name).lower(),
    }
    return features, metadata


def _sync_position_from_venue(venue_adapter, risk_manager: RiskManager, market, monitor: Monitor) -> None:
    if not hasattr(venue_adapter, "get_position"):
        return
    if market.market_id in risk_manager.positions:
        return
    try:
        size = float(venue_adapter.get_position(market.market_id))
    except Exception as exc:
        monitor.warning(f"Position sync failed for {market.market_id}: {exc}")
        return
    if abs(size) < 1e-9:
        return

    risk_manager.positions[market.market_id] = RiskPosition(
        market_id=market.market_id,
        size=size,
        entry_price=market.mid_price,
        current_price=market.mid_price,
        metadata={"source": "venue_sync"},
    )
    risk_manager.current_exposure += abs(size * market.mid_price)
    monitor.info(
        f"Synchronized existing venue position for {market.market_id}: size={size:.4f}"
    )


def _estimate_realized_pnl(
    risk_manager: RiskManager,
    *,
    market_id: str,
    size_delta: float,
    fill_price: float,
    fee_total: float,
) -> float:
    realized = -abs(fee_total)
    existing = risk_manager.positions.get(market_id)
    if existing is None or abs(existing.size) < 1e-9:
        return realized
    if existing.size > 0 and size_delta < 0:
        close_size = min(abs(existing.size), abs(size_delta))
        realized += close_size * (fill_price - existing.entry_price)
    elif existing.size < 0 and size_delta > 0:
        close_size = min(abs(existing.size), abs(size_delta))
        realized += close_size * (existing.entry_price - fill_price)
    return realized


def _resting_order_active(resting_orders: dict[str, dict[str, Any]], market_id: str, ttl_seconds: float) -> bool:
    payload = resting_orders.get(market_id)
    if not payload:
        return False
    created_at = payload.get("created_at")
    if not isinstance(created_at, datetime):
        resting_orders.pop(market_id, None)
        return False
    age_seconds = (datetime.now() - created_at).total_seconds()
    if age_seconds > ttl_seconds:
        resting_orders.pop(market_id, None)
        return False
    return True


def _is_resting_execution(report) -> bool:
    status = str(report.metadata.get("status", "")).lower()
    return (
        not report.filled
        and report.error_message is None
        and bool(report.metadata.get("order_id"))
        and status in {"live", "open", "pending", "resting", "unmatched"}
    )


def run_live_cycle(
    *,
    config,
    agent,
    live_trader: LiveTrader,
    venue_adapter,
    risk_manager: RiskManager,
    monitor: Monitor,
    resting_orders: dict[str, dict[str, Any]] | None = None,
    available_cash: float | None = None,
) -> LiveCycleResult:
    """Execute one live fetch-decide-risk-check-execute cycle."""

    resting_orders = resting_orders if resting_orders is not None else {}
    result = LiveCycleResult()
    result.available_cash = (
        max(float(available_cash), 0.0)
        if available_cash is not None
        else _resolve_available_cash(config, venue_adapter, risk_manager, monitor)
    )
    resting_ttl_seconds = float(config.metadata.get("resting_order_ttl_seconds", 300.0))
    market_limit = int(config.metadata.get("market_limit", 10))

    filters: dict[str, Any] = {
        "limit": max(market_limit, 1),
        "active_only": True,
        "min_liquidity": float(config.strategy.min_book_liquidity),
    }
    category_filter = config.metadata.get("category")
    if category_filter:
        filters["category"] = str(category_filter)

    markets = list(venue_adapter.get_markets(filters))
    result.markets_seen = len(markets)
    if not markets:
        monitor.warning("Venue returned no eligible live markets for this cycle")
        result.resting_orders = len(resting_orders)
        return result

    risk_manager.update_market_prices({market.market_id: market.mid_price for market in markets})
    if bool(config.metadata.get("sync_positions_from_venue", True)):
        for market in markets:
            _sync_position_from_venue(venue_adapter, risk_manager, market, monitor)

    current_cash = result.available_cash

    for market in markets:
        if _resting_order_active(resting_orders, market.market_id, resting_ttl_seconds):
            monitor.log_decision(
                create_decision_log(
                    market_id=market.market_id,
                    decision="skip",
                    reason="resting_order_pending",
                    edge=0.0,
                    market_price=market.market_prob,
                    fair_price=market.market_prob,
                    metadata={"resting_order": dict(resting_orders[market.market_id])},
                )
            )
            result.decisions_logged += 1
            continue

        features, metadata = _build_live_snapshot_inputs(market, config)
        portfolio = _portfolio_from_risk(
            risk_manager,
            cash=current_cash,
            starting_capital=config.backtest.initial_bankroll,
        )
        decision = agent.evaluate_market(
            market,
            venue=_scaffold_venue_config(config, market),
            portfolio=portfolio,
            position=portfolio.positions.get(market.market_id),
            context_metadata=metadata,
            snapshot_features=features,
        )

        signal = decision.signal
        edge = signal.edge_against(market.market_prob) if signal is not None else 0.0

        if decision.status != DecisionStatus.TRADE or not decision.orders:
            reason = ", ".join(decision.reasons) if decision.reasons else decision.status.value
            if signal is not None and signal.rationale:
                reason = signal.rationale if not reason else f"{reason}; {signal.rationale}"
            monitor.log_decision(
                create_decision_log(
                    market_id=market.market_id,
                    decision="skip",
                    reason=reason or "no_trade",
                    edge=edge,
                    market_price=market.market_prob,
                    fair_price=signal.fair_prob if signal is not None else market.market_prob,
                    metadata={**metadata, **decision.metadata},
                )
            )
            result.decisions_logged += 1
            continue

        first_order = decision.orders[0]
        reason = signal.rationale or ", ".join(decision.reasons) or "trade_signal"
        monitor.log_decision(
            create_decision_log(
                market_id=market.market_id,
                decision="trade",
                reason=reason,
                edge=edge,
                market_price=market.market_prob,
                fair_price=signal.fair_prob,
                proposed_size=first_order.size,
                proposed_side=first_order.side.value,
                metadata={
                    **metadata,
                    **decision.metadata,
                    "signal_confidence": signal.confidence,
                    "num_orders": len(decision.orders),
                },
            )
        )
        result.decisions_logged += 1

        for order in decision.orders:
            risk_check = risk_manager.check_order(order, current_price=market.mid_price)
            if risk_check.is_blocked():
                monitor.log_decision(
                    create_decision_log(
                        market_id=market.market_id,
                        decision="skip",
                        reason=f"risk_blocked: {risk_check.reason}",
                        edge=edge,
                        market_price=market.market_prob,
                        fair_price=signal.fair_prob,
                        proposed_size=order.size,
                        proposed_side=order.side.value,
                        metadata={
                            **metadata,
                            "risk_check": risk_check.metadata,
                            "warnings": risk_check.warnings,
                        },
                    )
                )
                result.decisions_logged += 1
                result.blocked_orders += 1
                continue

            for warning in risk_check.warnings:
                monitor.warning(f"Risk warning for {market.market_id}: {warning}")

            try:
                report = live_trader.place_order(order)
            except Exception as exc:
                monitor.log_trade(
                    create_trade_log(
                        market_id=order.market_id,
                        side=order.side.value,
                        order_type=order.order_type.value,
                        size=order.size,
                        price=None,
                        commission=0.0,
                        slippage_bps=0.0,
                        execution_mode="live",
                        success=False,
                        error=str(exc),
                        metadata={**metadata, **order.metadata},
                    )
                )
                monitor.log_error(
                    exc,
                    {
                        "context": "order_execution",
                        "market_id": order.market_id,
                        "side": order.side.value,
                        "order_type": order.order_type.value,
                    },
                )
                result.errors += 1
                continue

            result.orders_submitted += 1
            monitor.log_trade(
                create_trade_log(
                    market_id=order.market_id,
                    side=order.side.value,
                    order_type=order.order_type.value,
                    size=order.size,
                    price=report.avg_fill_price,
                    commission=report.fee_total,
                    slippage_bps=report.slippage_bps,
                    execution_mode=report.execution_mode,
                    success=report.is_success(),
                    error=report.error_message,
                    metadata={**metadata, **order.metadata, **report.metadata},
                )
            )

            if report.filled and report.avg_fill_price is not None:
                signed_size = report.filled_size if order.side == OrderSide.BUY else -report.filled_size
                pnl_delta = _estimate_realized_pnl(
                    risk_manager,
                    market_id=order.market_id,
                    size_delta=signed_size,
                    fill_price=report.avg_fill_price,
                    fee_total=report.fee_total,
                )
                risk_manager.update_position(
                    order.market_id,
                    signed_size,
                    report.avg_fill_price,
                    pnl_delta=pnl_delta,
                )
                if order.side == OrderSide.BUY:
                    current_cash = max(
                        current_cash - (report.filled_size * report.avg_fill_price) - report.fee_total,
                        0.0,
                    )
                else:
                    current_cash += (report.filled_size * report.avg_fill_price) - report.fee_total
                resting_orders.pop(order.market_id, None)
                result.trades_filled += 1
                continue

            if _is_resting_execution(report):
                resting_orders[order.market_id] = {
                    "order_id": report.metadata.get("order_id"),
                    "status": report.metadata.get("status"),
                    "created_at": datetime.now(),
                }
                monitor.info(
                    f"Recorded resting order for {order.market_id}: "
                    f"{report.metadata.get('order_id')}"
                )

    result.available_cash = current_cash
    result.resting_orders = len(resting_orders)
    return result


def confirm_live_trading(config) -> bool:
    """Require explicit confirmation before live trading."""
    print("\n" + "=" * 70)
    print("DANGER: LIVE TRADING MODE")
    print("=" * 70)
    print("This will execute REAL trades using REAL money on REAL markets.")
    print("")
    print("Configuration Summary:")
    print(f"  Experiment: {config.name}")
    print(f"  Venue: {config.venue.name}")
    print(f"  Testnet: {config.venue.testnet}")
    print("")
    print("Risk Limits:")
    print(f"  Max position per market: ${config.risk.max_position_per_market:.2f}")
    print(f"  Max total exposure: ${config.risk.max_total_exposure:.2f}")
    print(f"  Max daily loss: ${config.risk.max_daily_loss:.2f}")
    print(f"  Kill switch threshold: ${config.risk.kill_switch_threshold:.2f}")
    print(f"  Kill switch enabled: {config.risk.enable_kill_switch}")
    print("")
    print("Before proceeding:")
    print("  1. Verify all risk limits are appropriate")
    print("  2. Ensure you have tested in paper mode")
    print("  3. Confirm API credentials are correct")
    print("  4. Have a plan to monitor and intervene")
    print("")
    print("=" * 70)
    print("")
    print("Type 'CONFIRM LIVE TRADING' (exact case) to proceed:")
    print("Type anything else to abort.")
    print("")

    try:
        response = input("> ").strip()
        if response == "CONFIRM LIVE TRADING":
            print("\nLive trading CONFIRMED by user")
            return True
        print("\nLive trading ABORTED")
        return False
    except (EOFError, KeyboardInterrupt):
        print("\n\nLive trading ABORTED (interrupted)")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run live trading (DANGER: real money at risk)"
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to configuration file (YAML)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - validate config but don't trade",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Run duration in seconds (default: run indefinitely)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
    )

    args = parser.parse_args()

    print(f"Loading configuration from: {args.config}")
    try:
        config = load_config(args.config, allow_missing_env=args.dry_run)
    except Exception as e:
        print(f"ERROR: Failed to load configuration: {e}")
        sys.exit(1)

    if not config.is_live():
        print("ERROR: Configuration is not in live mode!")
        print(f"Current mode: {config.venue.mode}")
        print("Live trading requires venue.mode = 'live'")
        print("\nIf you want to test safely, use paper mode:")
        print("  python scripts/run_paper.py --config configs/paper_trading.yaml")
        sys.exit(1)

    warnings = validate_config(config)
    if warnings:
        print("\nConfiguration Warnings:")
        for warning in warnings:
            print(f"  WARNING: {warning}")
        print()

    if not config.risk.enable_kill_switch:
        print("CRITICAL ERROR: Kill switch is disabled!")
        print("Live trading REQUIRES kill switch to be enabled.")
        print("Set risk.enable_kill_switch = true in your config.")
        sys.exit(1)

    if args.verbose:
        config.logging.log_level = "DEBUG"

    if args.dry_run:
        missing_envs = sorted(set(collect_missing_env_vars(config.to_dict())))
        print("\n" + "=" * 60)
        print("DRY RUN MODE")
        print("=" * 60)
        print("Configuration is valid and would be used for live trading.")
        print("No actual trades will be executed in dry run mode.")
        if missing_envs:
            print("")
            print("Credential env vars were intentionally left unresolved for dry run:")
            for env_name in missing_envs:
                print(f"  - {env_name}")
        print("")
        print("Dry run skips authenticated venue checks but preserves live-mode risk validation.")
        print("\nTo run live trading (DANGER), remove the --dry-run flag:")
        print(f"  python scripts/run_live.py --config {args.config}")
        print("=" * 60)
        return

    if not confirm_live_trading(config):
        print("\nLive trading not confirmed - exiting safely")
        sys.exit(0)

    print("\n" + "!" * 70)
    print("LIVE TRADING STARTING IN 5 SECONDS")
    print("Press Ctrl+C NOW to abort")
    print("!" * 70)
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    print("STARTING LIVE TRADING NOW")
    print("!" * 70 + "\n")

    print("\nInitializing live trading system...")
    print("=" * 60)
    print(f"Experiment: {config.name}")
    print(f"Mode: LIVE TRADING *** REAL MONEY AT RISK ***")
    print(f"Venue: {config.venue.name} (testnet={config.venue.testnet})")
    print(f"Strategy: {config.strategy.name}")
    print(f"Logs: {config.logging.log_dir}")
    print("=" * 60)

    monitor = Monitor(config.logging)
    venue_adapter = _create_venue_adapter(config, dry_run=False)
    if hasattr(venue_adapter, "check_connectivity"):
        connectivity = venue_adapter.check_connectivity()
        monitor.info(f"Venue connectivity check: {connectivity}")

    live_trader = LiveTrader(
        venue_adapter,
        safety_checks=True,
        require_confirmation=False,
    )
    risk_manager = RiskManager(config.risk)
    live_agent = _build_live_agent(config)
    poll_interval_seconds = float(config.metadata.get("poll_interval_seconds", 60.0))
    resting_orders: dict[str, dict[str, Any]] = {}

    monitor.info("=" * 60)
    monitor.info("LIVE TRADING SESSION STARTED")
    monitor.info("=" * 60)
    monitor.info(f"Configuration: {args.config}")
    monitor.info(f"Venue: {config.venue.name}")
    monitor.info(
        f"Risk limits: pos={config.risk.max_position_per_market}, "
        f"exposure={config.risk.max_total_exposure}, "
        f"daily_loss={config.risk.max_daily_loss}"
    )
    monitor.info(f"Live loop poll interval: {poll_interval_seconds:.1f}s")

    start_time = datetime.now()
    trade_count = 0
    orders_submitted = 0
    decision_count = 0

    print("\nLive trading loop running...")
    print("Press Ctrl+C to stop (positions will remain open)\n")

    try:
        while True:
            if risk_manager.is_kill_switch_active():
                print("\nKILL SWITCH IS ACTIVE - trading halted")
                monitor.warning("Kill switch active - trading halted")
                break

            if args.duration is not None:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= args.duration:
                    monitor.info(f"Duration limit reached ({args.duration}s)")
                    break

            try:
                cycle = run_live_cycle(
                    config=config,
                    agent=live_agent,
                    live_trader=live_trader,
                    venue_adapter=venue_adapter,
                    risk_manager=risk_manager,
                    monitor=monitor,
                    resting_orders=resting_orders,
                )
            except Exception as exc:
                monitor.log_error(exc, {"context": "live_cycle"})
                if bool(config.metadata.get("halt_on_cycle_error", False)):
                    raise
                monitor.warning(
                    "Live cycle failed; continuing after backoff because "
                    "halt_on_cycle_error is disabled"
                )
                time.sleep(min(poll_interval_seconds, 5.0))
                continue

            trade_count += cycle.trades_filled
            orders_submitted += cycle.orders_submitted
            decision_count += cycle.decisions_logged

            if monitor.should_log_performance():
                snapshot = PerformanceSnapshot(
                    timestamp=datetime.now().isoformat(),
                    total_pnl=risk_manager.total_pnl,
                    daily_pnl=risk_manager.get_daily_pnl(),
                    num_trades=trade_count,
                    num_positions=len(risk_manager.positions),
                    total_exposure=risk_manager.get_current_exposure(),
                    metadata={
                        "orders_submitted": orders_submitted,
                        "decisions_logged": decision_count,
                        "resting_orders": len(resting_orders),
                        "available_cash": cycle.available_cash,
                        "markets_seen_last_cycle": cycle.markets_seen,
                    },
                )
                monitor.log_performance(snapshot)

            expired = risk_manager.check_position_timeouts()
            if expired:
                monitor.warning(f"Positions exceeded timeout: {expired}")

            time.sleep(poll_interval_seconds)

    except KeyboardInterrupt:
        print("\n\nShutdown requested by user (Ctrl+C)")
        monitor.warning("Shutdown requested by user via Ctrl+C")

    except Exception as e:
        print(f"\n\nCRITICAL ERROR: {e}")
        monitor.log_error(e, {"context": "main_loop"})
        print("Kill switch activated due to exception")
        risk_manager.manual_kill_switch("Exception in main loop")
        raise

    finally:
        print("\n" + "=" * 60)
        print("LIVE TRADING SESSION ENDED")
        print("=" * 60)

        duration = (datetime.now() - start_time).total_seconds()
        print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        print(f"Orders submitted: {orders_submitted}")
        print(f"Trades filled: {trade_count}")
        print(f"Total P&L: ${risk_manager.total_pnl:.2f}")
        print(f"Daily P&L: ${risk_manager.get_daily_pnl():.2f}")
        print(f"Open positions: {len(risk_manager.positions)}")
        print(f"Total exposure: ${risk_manager.get_current_exposure():.2f}")
        print(f"Resting orders tracked: {len(resting_orders)}")

        if risk_manager.positions:
            print("\nWARNING: You still have OPEN POSITIONS:")
            for market_id, pos in risk_manager.positions.items():
                print(f"  - {market_id}: size={pos.size:.2f} P&L={pos.unrealized_pnl:.2f}")
            print("\nYou may want to close these positions manually.")

        print(f"\nLogs saved to: {config.logging.log_dir}")
        log_files = monitor.get_log_files()
        for log_type, path in log_files.items():
            if path.exists():
                print(f"  - {log_type}: {path}")

        print("\n" + "=" * 60)

        monitor.info("=" * 60)
        monitor.info("LIVE TRADING SESSION ENDED")
        monitor.info(f"Final P&L: {risk_manager.total_pnl:.2f}")
        monitor.info(f"Open positions: {len(risk_manager.positions)}")
        monitor.info(f"Resting orders: {len(resting_orders)}")
        monitor.info("=" * 60)


if __name__ == "__main__":
    main()
