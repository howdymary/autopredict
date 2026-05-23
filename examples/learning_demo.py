#!/usr/bin/env python3
"""Analyze real AutoPredict trade logs from a local log directory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autopredict.learning.analyzer import PerformanceAnalyzer
from autopredict.learning.logger import TradeLogger


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze persisted AutoPredict trade logs")
    parser.add_argument("--log-dir", required=True, help="Directory containing trade JSONL logs")
    args = parser.parse_args()

    logger = TradeLogger(Path(args.log_dir))
    logs = logger.load_all()
    if not logs:
        print("No trade logs found.")
        return 1

    report = PerformanceAnalyzer(logs).generate_report()
    print(f"Total trades: {report.total_trades}")
    print(f"Total PnL: ${report.total_pnl:.2f}")
    print(f"Win rate: {report.win_rate:.2%}")
    print(f"Calibration error: {report.calibration_error:.3f}")
    print(f"Edge capture rate: {report.edge_capture_rate:.2%}")
    if report.failure_regimes:
        print("Failure regimes:")
        for regime in report.failure_regimes:
            print(f"  - {regime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
