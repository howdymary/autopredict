"""Adapter interfaces and example implementations for real data integration."""

from __future__ import annotations

import csv
import json
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from autopredict.agent import MarketState
from autopredict.market_env import OrderBook, BookLevel


class MarketDataAdapter(ABC):
    """Interface for fetching market data from external sources."""

    @abstractmethod
    def fetch_markets(self) -> list[MarketState]:
        """
        Fetch current market snapshots.

        Returns:
            List of MarketState objects ready for agent evaluation
        """
        pass

    @abstractmethod
    def stream_markets(self) -> Iterator[MarketState]:
        """
        Stream market updates in real-time.

        Yields:
            MarketState objects as they update
        """
        pass


class OrderExecutionAdapter(ABC):
    """Interface for submitting orders to external markets."""

    @abstractmethod
    def submit_order(self, market_id: str, side: str, size: float, price: float | None) -> dict:
        """
        Submit an order to the market.

        Args:
            market_id: Market identifier
            side: "buy" or "sell"
            size: Order size
            price: Limit price (None for market order)

        Returns:
            Order confirmation with fill details
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.

        Args:
            order_id: Order identifier

        Returns:
            True if successful, False otherwise
        """
        pass


class CSVDataAdapter(MarketDataAdapter):
    """Adapter for reading historical market data from CSV files."""

    def __init__(self, csv_path: str | Path):
        """
        Initialize with path to CSV file.

        CSV format:
            market_id,timestamp,market_prob,fair_prob,outcome,category,
            bid1_price,bid1_size,ask1_price,ask1_size,...
        """
        self.csv_path = Path(csv_path)
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

    def fetch_markets(self) -> list[MarketState]:
        """Load all markets from CSV."""
        markets = []

        with open(self.csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                markets.append(self._parse_row(row))

        return markets

    def stream_markets(self) -> Iterator[MarketState]:
        """Stream markets one at a time from CSV."""
        with open(self.csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield self._parse_row(row)

    def _parse_row(self, row: dict) -> MarketState:
        """Parse CSV row into MarketState."""
        # Extract basic fields
        market_id = row["market_id"]
        market_prob = float(row["market_prob"])
        fair_prob = float(row["fair_prob"])
        time_to_expiry = float(row.get("time_to_expiry_hours", 24.0))

        # Parse order book
        bids = []
        asks = []

        # Assuming CSV has bid1_price, bid1_size, bid2_price, bid2_size, etc.
        i = 1
        while f"bid{i}_price" in row:
            price = float(row[f"bid{i}_price"])
            size = float(row[f"bid{i}_size"])
            if price > 0 and size > 0:
                bids.append(BookLevel(price, size))
            i += 1

        i = 1
        while f"ask{i}_price" in row:
            price = float(row[f"ask{i}_price"])
            size = float(row[f"ask{i}_size"])
            if price > 0 and size > 0:
                asks.append(BookLevel(price, size))
            i += 1

        order_book = OrderBook(
            market_id=market_id,
            bids=bids,
            asks=asks
        )

        return MarketState(
            market_id=market_id,
            market_prob=market_prob,
            fair_prob=fair_prob,
            time_to_expiry_hours=time_to_expiry,
            order_book=order_book,
            metadata={"category": row.get("category", "unknown")}
        )


class PolymarketAdapter(MarketDataAdapter, OrderExecutionAdapter):
    """
    Example adapter for Polymarket (simulated - not real API calls).

    In production, replace with actual Polymarket API calls.
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize with API credentials.

        Args:
            api_key: Polymarket API key (not used in simulation)
        """
        self.api_key = api_key

    def fetch_markets(self) -> list[MarketState]:
        """
        Simulated market fetch.

        In production: Call Polymarket API, transform response.
        """
        # Simulate API response
        simulated_response = [
            {
                "id": "polymarket-btc-100k",
                "question": "Will BTC reach $100k by end of year?",
                "current_price": 0.42,
                "time_remaining_hours": 720.0,
                "category": "crypto",
                "order_book": {
                    "bids": [[0.41, 500.0], [0.40, 750.0]],
                    "asks": [[0.43, 480.0], [0.44, 600.0]]
                }
            }
        ]

        markets = []
        for item in simulated_response:
            # Transform to AutoPredict format
            order_book = OrderBook(
                market_id=item["id"],
                bids=[BookLevel(p, s) for p, s in item["order_book"]["bids"]],
                asks=[BookLevel(p, s) for p, s in item["order_book"]["asks"]]
            )

            # You would need to calculate fair_prob externally
            # For demo, assume we have a forecasting model
            fair_prob = self._calculate_fair_prob(item)

            markets.append(
                MarketState(
                    market_id=item["id"],
                    market_prob=item["current_price"],
                    fair_prob=fair_prob,
                    time_to_expiry_hours=item["time_remaining_hours"],
                    order_book=order_book,
                    metadata={"category": item["category"]}
                )
            )

        return markets

    def stream_markets(self) -> Iterator[MarketState]:
        """
        Simulated market streaming.

        In production: WebSocket connection to Polymarket.
        """
        # For demo, just yield from fetch_markets
        markets = self.fetch_markets()
        for market in markets:
            yield market

    def submit_order(self, market_id: str, side: str, size: float, price: float | None) -> dict:
        """
        Simulated order submission.

        In production: POST to Polymarket order API.
        """
        print(f"[SIMULATED] Submitting order to Polymarket:")
        print(f"  Market: {market_id}")
        print(f"  Side: {side}")
        print(f"  Size: {size}")
        print(f"  Price: {price if price else 'MARKET'}")

        # Simulate response
        return {
            "order_id": f"poly-{market_id}-{hash(side + str(size)) % 100000}",
            "status": "submitted",
            "filled_size": 0.0,
            "remaining_size": size,
        }

    def cancel_order(self, order_id: str) -> bool:
        """
        Simulated order cancellation.

        In production: DELETE to Polymarket order API.
        """
        print(f"[SIMULATED] Canceling order {order_id}")
        return True

    def _calculate_fair_prob(self, market_data: dict) -> float:
        """
        Calculate fair probability for a market.

        In production: Use your forecasting model here.
        """
        # For demo, just add some edge to market price
        return market_data["current_price"] + 0.05


if __name__ == "__main__":
    # Demonstrate adapter usage
    print("="*80)
    print("CSV ADAPTER DEMO")
    print("="*80)

    # Create sample CSV
    sample_csv = Path(__file__).parent / "sample_historical.csv"
    with open(sample_csv, "w") as f:
        f.write("market_id,market_prob,fair_prob,time_to_expiry_hours,category,")
        f.write("bid1_price,bid1_size,ask1_price,ask1_size\n")
        f.write("test-market-1,0.50,0.55,24.0,politics,0.49,100.0,0.51,100.0\n")
        f.write("test-market-2,0.35,0.42,48.0,crypto,0.34,150.0,0.36,150.0\n")

    adapter = CSVDataAdapter(sample_csv)
    markets = adapter.fetch_markets()

    print(f"\nLoaded {len(markets)} markets from CSV")
    for market in markets:
        print(f"  {market.market_id}: market={market.market_prob}, fair={market.fair_prob}")

    print("\n" + "="*80)
    print("POLYMARKET ADAPTER DEMO")
    print("="*80)

    poly_adapter = PolymarketAdapter()
    poly_markets = poly_adapter.fetch_markets()

    print(f"\nFetched {len(poly_markets)} markets from Polymarket (simulated)")
    for market in poly_markets:
        print(f"  {market.market_id}: market={market.market_prob}, fair={market.fair_prob}")

    # Simulate order submission
    print("\n" + "="*80)
    print("ORDER SUBMISSION DEMO")
    print("="*80)

    order = poly_adapter.submit_order(
        market_id=poly_markets[0].market_id,
        side="buy",
        size=10.0,
        price=0.45
    )
    print(f"\nOrder submitted: {order}")

    # Clean up
    sample_csv.unlink()
