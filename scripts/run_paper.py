#!/usr/bin/env python3
"""Paper trading runner for AutoPredict.

Runs trading strategies in paper mode (simulation only, no real money).
Safe for experimentation and strategy development.

Usage:
    python scripts/run_paper.py --config configs/paper_trading.yaml
    python scripts/run_paper.py --config configs/paper_trading.yaml --duration 3600
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
from autopredict.live import PaperTrader, Monitor, RiskManager
from autopredict.live.monitor import create_trade_log, create_decision_log, PerformanceSnapshot


def main():
    parser = argparse.ArgumentParser(
        description="Run paper trading (safe simulation mode)"
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to configuration file (YAML)",
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

    # Validate it's paper trading mode
    if not config.is_paper():
        print("ERROR: Configuration is not in paper mode!")
        print(f"Current mode: {config.venue.mode}")
        print("Paper trading requires venue.mode = 'paper'")
        sys.exit(1)

    # Validate configuration and show warnings
    warnings = validate_config(config)
    if warnings:
        print("\nConfiguration Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        print()

    # Override log level if verbose
    if args.verbose:
        config.logging.log_level = "DEBUG"

    # Initialize components
    print("\nInitializing paper trading system...")
    print("=" * 60)
    print(f"Experiment: {config.name}")
    print(f"Mode: PAPER TRADING (simulation only)")
    print(f"Strategy: {config.strategy.name}")
    print(f"Initial bankroll: ${config.backtest.initial_bankroll:.2f}")
    print(f"Risk limits:")
    print(f"  - Max position per market: ${config.risk.max_position_per_market:.2f}")
    print(f"  - Max total exposure: ${config.risk.max_total_exposure:.2f}")
    print(f"  - Max daily loss: ${config.risk.max_daily_loss:.2f}")
    print(f"  - Kill switch: ${config.risk.kill_switch_threshold:.2f}")
    print(f"Logs: {config.logging.log_dir}")
    print("=" * 60)

    # Create components
    monitor = Monitor(config.logging)
    trader = PaperTrader(
        commission_rate=config.backtest.commission_rate,
        slippage_bps=config.backtest.slippage_bps,
    )
    risk_manager = RiskManager(config.risk)

    monitor.info("Paper trading system initialized")
    monitor.info(f"Configuration: {args.config}")

    # Run trading loop
    start_time = datetime.now()
    bankroll = config.backtest.initial_bankroll
    trade_count = 0

    print("\nStarting paper trading loop...")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            # Check duration limit
            if args.duration is not None:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= args.duration:
                    monitor.info(f"Duration limit reached ({args.duration}s)")
                    break

            # Simulate trading loop iteration
            # In a real implementation, this would:
            # 1. Fetch market data
            # 2. Run agent decision logic
            # 3. Check risk limits
            # 4. Execute trades via PaperTrader
            # 5. Update risk manager
            # 6. Log everything

            # For demonstration, just sleep and log periodic metrics
            time.sleep(60)  # Check every minute

            # Log performance snapshot if needed
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

            # Check for position timeouts
            expired = risk_manager.check_position_timeouts()
            if expired:
                monitor.warning(f"Positions exceeded timeout: {expired}")

    except KeyboardInterrupt:
        print("\n\nShutdown requested by user (Ctrl+C)")
        monitor.info("Shutdown requested by user")

    except Exception as e:
        print(f"\n\nERROR: Unexpected exception: {e}")
        monitor.log_error(e, {"context": "main_loop"})
        raise

    finally:
        # Shutdown
        print("\n" + "=" * 60)
        print("PAPER TRADING SESSION ENDED")
        print("=" * 60)

        # Final statistics
        duration = (datetime.now() - start_time).total_seconds()
        print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        print(f"Trades executed: {trade_count}")
        print(f"Total P&L: ${risk_manager.total_pnl:.2f}")
        print(f"Daily P&L: ${risk_manager.get_daily_pnl():.2f}")
        print(f"Final bankroll: ${bankroll + risk_manager.total_pnl:.2f}")
        print(f"Return: {(risk_manager.total_pnl / bankroll * 100):.2f}%")

        print(f"\nLogs saved to: {config.logging.log_dir}")
        log_files = monitor.get_log_files()
        for log_type, path in log_files.items():
            if path.exists():
                print(f"  - {log_type}: {path}")

        print("\n" + "=" * 60)

        monitor.info("Paper trading session ended")
        monitor.info(f"Final P&L: {risk_manager.total_pnl:.2f}")


if __name__ == "__main__":
    main()
