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
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autopredict.config import load_config, validate_config
from autopredict.live import Monitor, RiskManager
from autopredict.live.monitor import PerformanceSnapshot


def _create_venue_adapter(config):
    """Resolve a real venue adapter or fail fast.

    The current repo contains venue scaffolding, but no production-ready live
    adapters. Refusing to start is safer than silently running an inert session.
    """
    venue_name = str(config.venue.name).lower()

    if venue_name == "polymarket":
        raise SystemExit(
            "Live trading for Polymarket is not implemented in this repository yet. "
            "The current adapter is a scaffold and cannot safely submit real orders."
        )
    if venue_name == "manifold":
        raise SystemExit(
            "Live trading for Manifold is not implemented in this repository yet. "
            "The current adapter is a scaffold and cannot safely submit real orders."
        )

    raise SystemExit(
        f"Live trading for venue '{config.venue.name}' is not available. "
        "Use paper mode or implement a real adapter first."
    )


def confirm_live_trading(config) -> bool:
    """Require explicit confirmation before live trading.

    Args:
        config: Experiment configuration

    Returns:
        True if user confirms, False otherwise
    """
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
        else:
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

    # Load configuration
    print(f"Loading configuration from: {args.config}")
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"ERROR: Failed to load configuration: {e}")
        sys.exit(1)

    # Validate it's live trading mode
    if not config.is_live():
        print("ERROR: Configuration is not in live mode!")
        print(f"Current mode: {config.venue.mode}")
        print("Live trading requires venue.mode = 'live'")
        print("\nIf you want to test safely, use paper mode:")
        print("  python scripts/run_paper.py --config configs/paper_trading.yaml")
        sys.exit(1)

    # Validate configuration and show warnings
    warnings = validate_config(config)
    if warnings:
        print("\nConfiguration Warnings:")
        for warning in warnings:
            print(f"  WARNING: {warning}")
        print()

    # Check for critical safety issues
    if not config.risk.enable_kill_switch:
        print("CRITICAL ERROR: Kill switch is disabled!")
        print("Live trading REQUIRES kill switch to be enabled.")
        print("Set risk.enable_kill_switch = true in your config.")
        sys.exit(1)

    # Override log level if verbose
    if args.verbose:
        config.logging.log_level = "DEBUG"

    # Dry run mode
    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN MODE")
        print("=" * 60)
        print("Configuration is valid and would be used for live trading.")
        print("No actual trades will be executed in dry run mode.")
        print("\nTo run live trading (DANGER), remove the --dry-run flag:")
        print(f"  python scripts/run_live.py --config {args.config}")
        print("=" * 60)
        return

    # Require user confirmation for live trading
    if not confirm_live_trading(config):
        print("\nLive trading not confirmed - exiting safely")
        sys.exit(0)

    # Final warning
    print("\n" + "!" * 70)
    print("LIVE TRADING STARTING IN 5 SECONDS")
    print("Press Ctrl+C NOW to abort")
    print("!" * 70)
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    print("STARTING LIVE TRADING NOW")
    print("!" * 70 + "\n")

    # Initialize components
    print("\nInitializing live trading system...")
    print("=" * 60)
    print(f"Experiment: {config.name}")
    print(f"Mode: LIVE TRADING *** REAL MONEY AT RISK ***")
    print(f"Venue: {config.venue.name} (testnet={config.venue.testnet})")
    print(f"Strategy: {config.strategy.name}")
    print(f"Logs: {config.logging.log_dir}")
    print("=" * 60)

    # Create components
    monitor = Monitor(config.logging)

    venue_adapter = _create_venue_adapter(config)

    risk_manager = RiskManager(config.risk)

    monitor.info("=" * 60)
    monitor.info("LIVE TRADING SESSION STARTED")
    monitor.info("=" * 60)
    monitor.info(f"Configuration: {args.config}")
    monitor.info(f"Venue: {config.venue.name}")
    monitor.info(f"Risk limits: pos={config.risk.max_position_per_market}, "
                 f"exposure={config.risk.max_total_exposure}, "
                 f"daily_loss={config.risk.max_daily_loss}")

    # Trading loop
    start_time = datetime.now()
    trade_count = 0

    print("\nLive trading loop running...")
    print("Press Ctrl+C to stop (positions will remain open)\n")

    try:
        while True:
            # Check kill switch
            if risk_manager.is_kill_switch_active():
                print("\nKILL SWITCH IS ACTIVE - trading halted")
                monitor.warning("Kill switch active - trading halted")
                break

            # Check duration limit
            if args.duration is not None:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= args.duration:
                    monitor.info(f"Duration limit reached ({args.duration}s)")
                    break

            # Production trading loop would:
            # 1. Fetch live market data from venue
            # 2. Run agent decision logic
            # 3. Check risk limits via risk_manager.check_order()
            # 4. Execute trades via venue_adapter
            # 5. Update risk_manager with fills
            # 6. Log all activity via monitor

            # For this template, just sleep and monitor
            time.sleep(60)

            # Log performance snapshot
            if monitor.should_log_performance():
                snapshot = PerformanceSnapshot(
                    timestamp=datetime.now().isoformat(),
                    total_pnl=risk_manager.total_pnl,
                    daily_pnl=risk_manager.get_daily_pnl(),
                    num_trades=trade_count,
                    num_positions=len(risk_manager.positions),
                    total_exposure=risk_manager.get_current_exposure(),
                )
                monitor.log_performance(snapshot)

            # Check position timeouts
            expired = risk_manager.check_position_timeouts()
            if expired:
                monitor.warning(f"Positions exceeded timeout: {expired}")

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
        # Shutdown
        print("\n" + "=" * 60)
        print("LIVE TRADING SESSION ENDED")
        print("=" * 60)

        # Final statistics
        duration = (datetime.now() - start_time).total_seconds()
        print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        print(f"Trades executed: {trade_count}")
        print(f"Total P&L: ${risk_manager.total_pnl:.2f}")
        print(f"Daily P&L: ${risk_manager.get_daily_pnl():.2f}")
        print(f"Open positions: {len(risk_manager.positions)}")
        print(f"Total exposure: ${risk_manager.get_current_exposure():.2f}")

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
        monitor.info("=" * 60)


if __name__ == "__main__":
    main()
