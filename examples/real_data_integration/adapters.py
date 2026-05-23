"""Minimal adapters for caller-provided data and live read-only scans."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from autopredict.agent import MarketState
from autopredict.live_scan import LivePolymarketScanner
from autopredict.market_env import BookLevel, OrderBook


class CSVDataAdapter:
    """Adapter for reading historical market data from an explicit CSV file."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

    def fetch_markets(self) -> list[MarketState]:
        """Load all markets from CSV."""

        return list(self.stream_markets())

    def stream_markets(self) -> Iterator[MarketState]:
        """Stream markets one at a time from CSV."""

        with self.csv_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield self._parse_row(row)

    def _parse_row(self, row: dict[str, str]) -> MarketState:
        market_id = row["market_id"]
        bids = _book_side(row, "bid")
        asks = _book_side(row, "ask")
        return MarketState(
            market_id=market_id,
            market_prob=float(row["market_prob"]),
            fair_prob=float(row["fair_prob"]),
            time_to_expiry_hours=float(row.get("time_to_expiry_hours") or 24.0),
            order_book=OrderBook(market_id=market_id, bids=bids, asks=asks),
            metadata={"category": row.get("category", "unknown")},
        )


def _book_side(row: dict[str, str], prefix: str) -> list[BookLevel]:
    levels: list[BookLevel] = []
    index = 1
    while f"{prefix}{index}_price" in row:
        price = float(row[f"{prefix}{index}_price"] or 0)
        size = float(row[f"{prefix}{index}_size"] or 0)
        if price > 0 and size > 0:
            levels.append(BookLevel(price, size))
        index += 1
    return levels


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect explicit CSV data or live public markets")
    parser.add_argument("--csv", help="Path to real historical market CSV")
    parser.add_argument("--live", action="store_true", help="Print live read-only Polymarket reports")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if args.csv:
        markets = CSVDataAdapter(args.csv).fetch_markets()
        print(f"Loaded {len(markets)} markets from {args.csv}")
        return 0

    if args.live:
        reports = LivePolymarketScanner().scan_markets(limit=args.limit, top=args.limit)
        for report in reports:
            print(f"{report.market_prob}: {report.question}")
        return 0

    parser.error("pass --csv or --live")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
