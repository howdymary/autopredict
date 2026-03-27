"""Tests for market environment, order book, and execution engine."""

from __future__ import annotations

import pytest

from autopredict.market_env import (
    BookLevel,
    OrderBook,
    ExecutionEngine,
    ForecastRecord,
    TradeRecord,
    ExecutionMetrics,
    _brier_score,
    evaluate_all,
)


class TestOrderBook:
    """Test OrderBook functionality."""

    def test_order_book_creation(self, simple_order_book: OrderBook):
        """Test basic order book creation."""
        assert simple_order_book.market_id == "test-market"
        assert len(simple_order_book.bids) == 3
        assert len(simple_order_book.asks) == 3

    def test_order_book_sorting(self):
        """Test that order book sorts levels correctly."""
        book = OrderBook(
            market_id="test",
            bids=[
                BookLevel(0.45, 100.0),
                BookLevel(0.48, 150.0),  # Should be first
                BookLevel(0.46, 120.0),
            ],
            asks=[
                BookLevel(0.55, 100.0),
                BookLevel(0.52, 150.0),  # Should be first
                BookLevel(0.54, 120.0),
            ],
        )

        assert book.bids[0].price == 0.48  # Highest bid first
        assert book.asks[0].price == 0.52  # Lowest ask first

    def test_get_mid_price(self, simple_order_book: OrderBook):
        """Test mid price calculation."""
        mid = simple_order_book.get_mid_price()
        assert mid == 0.50  # (0.48 + 0.52) / 2

    def test_get_spread(self, simple_order_book: OrderBook, tight_spread_book: OrderBook):
        """Test spread calculation."""
        spread = simple_order_book.get_spread()
        assert abs(spread - 0.04) < 1e-9  # 0.52 - 0.48 (with floating point tolerance)

        tight_spread = tight_spread_book.get_spread()
        assert abs(tight_spread - 0.01) < 1e-9  # 0.605 - 0.595 (with floating point tolerance)

    def test_get_total_depth(self, simple_order_book: OrderBook):
        """Test total depth calculation."""
        bid_depth = simple_order_book.get_total_depth("sell")
        ask_depth = simple_order_book.get_total_depth("buy")
        total_depth = simple_order_book.get_total_depth()

        assert bid_depth == 450.0  # 100 + 150 + 200
        assert ask_depth == 480.0  # 110 + 160 + 210
        assert total_depth == 930.0  # 450 + 480

    def test_get_liquidity_at_price(self, simple_order_book: OrderBook):
        """Test getting liquidity at specific price level."""
        liquidity = simple_order_book.get_liquidity_at_price(0.48, "sell")
        assert liquidity == 100.0

        liquidity = simple_order_book.get_liquidity_at_price(0.52, "buy")
        assert liquidity == 110.0

    def test_clone(self, simple_order_book: OrderBook):
        """Test order book cloning."""
        clone = simple_order_book.clone()

        assert clone.market_id == simple_order_book.market_id
        assert len(clone.bids) == len(simple_order_book.bids)
        assert len(clone.asks) == len(simple_order_book.asks)

        # Modify clone shouldn't affect original
        clone.bids.clear()
        assert len(simple_order_book.bids) == 3


class TestWalkBook:
    """Test order book walking (execution simulation)."""

    def test_walk_book_buy_partial(self, simple_order_book: OrderBook):
        """Test walking book to buy a small amount."""
        filled, avg_price, fills = simple_order_book.walk_book(
            size=50.0, side="buy", mutate=False
        )

        assert filled == 50.0
        assert avg_price == 0.52  # All filled at best ask
        assert len(fills) == 1
        assert fills[0] == (0.52, 50.0)

    def test_walk_book_buy_full(self, simple_order_book: OrderBook):
        """Test walking book to buy larger amount."""
        filled, avg_price, fills = simple_order_book.walk_book(
            size=250.0, side="buy", mutate=False
        )

        assert filled == 250.0
        # (110 * 0.52 + 140 * 0.53) / 250 = 0.5256
        assert 0.525 < avg_price < 0.527
        assert len(fills) == 2

    def test_walk_book_sell_with_limit(self, simple_order_book: OrderBook):
        """Test walking book with limit price."""
        filled, avg_price, fills = simple_order_book.walk_book(
            size=200.0, side="sell", limit_price=0.48, mutate=False
        )

        assert filled == 100.0  # Only fills at 0.48
        assert avg_price == 0.48
        assert len(fills) == 1

    def test_walk_book_mutate(self, simple_order_book: OrderBook):
        """Test that mutate flag removes liquidity."""
        initial_depth = simple_order_book.get_total_depth()

        filled, avg_price, _ = simple_order_book.walk_book(
            size=100.0, side="buy", mutate=True
        )

        after_depth = simple_order_book.get_total_depth()

        assert filled == 100.0
        assert after_depth < initial_depth
        assert simple_order_book.asks[0].size == 10.0  # 110 - 100

    def test_walk_book_insufficient_liquidity(self, thin_book: OrderBook):
        """Test walking book with insufficient liquidity."""
        filled, avg_price, fills = thin_book.walk_book(
            size=1000.0, side="buy", mutate=False
        )

        assert filled < 1000.0  # Can't fill entire order
        assert filled == 45.0  # 20 + 25
        assert len(fills) == 2


class TestExecutionEngine:
    """Test execution engine."""

    def test_market_order_execution(
        self, simple_order_book: OrderBook, execution_engine: ExecutionEngine
    ):
        """Test market order execution."""
        report = execution_engine.execute_market_order(
            size=100.0, side="buy", order_book=simple_order_book
        )

        assert report.market_id == "test-market"
        assert report.order_type == "market"
        assert report.side == "buy"
        assert report.filled_size == 100.0
        assert report.fill_rate == 1.0
        assert report.average_fill_price == 0.52

    def test_market_order_partial_fill(
        self, thin_book: OrderBook, execution_engine: ExecutionEngine
    ):
        """Test market order with partial fill."""
        report = execution_engine.execute_market_order(
            size=100.0, side="buy", order_book=thin_book
        )

        assert report.filled_size < 100.0
        assert report.fill_rate < 1.0
        assert report.queued_size > 0

    def test_limit_order_marketable(
        self, simple_order_book: OrderBook, execution_engine: ExecutionEngine
    ):
        """Test marketable limit order (crosses spread)."""
        report = execution_engine.execute_limit_order(
            price=0.55, size=100.0, side="buy", order_book=simple_order_book
        )

        assert report.filled_size == 100.0
        assert report.order_type == "limit"

    def test_limit_order_passive(
        self, simple_order_book: OrderBook, execution_engine: ExecutionEngine
    ):
        """Test passive limit order (joins book)."""
        report = execution_engine.execute_limit_order(
            price=0.47, size=100.0, side="buy", order_book=simple_order_book
        )

        assert report.order_type == "limit"
        assert report.filled_size < 100.0  # Partial passive fill
        assert "queue" in report.notes[0].lower()

    def test_limit_order_ioc(
        self, simple_order_book: OrderBook, execution_engine: ExecutionEngine
    ):
        """Test IOC (immediate or cancel) limit order."""
        report = execution_engine.execute_limit_order(
            price=0.47,
            size=100.0,
            side="buy",
            order_book=simple_order_book,
            time_in_force="IOC",
        )

        assert report.filled_size == 0.0  # Not marketable, so cancelled
        assert "ioc" in report.notes[0].lower()

    def test_execution_with_fees(
        self, simple_order_book: OrderBook, execution_engine_with_fees: ExecutionEngine
    ):
        """Test execution quality calculation with fees."""
        report = execution_engine_with_fees.execute_market_order(
            size=100.0, side="buy", order_book=simple_order_book
        )

        # Should have positive slippage (bought above mid)
        assert report.slippage_bps > 0

        # Implementation shortfall includes fees
        assert report.implementation_shortfall_bps > report.slippage_bps


class TestCalibrationMetrics:
    """Test calibration and forecast metrics."""

    def test_brier_score_perfect(self):
        """Test Brier score with perfect forecasts."""
        forecasts = [
            ForecastRecord("m1", 1.0, 1),
            ForecastRecord("m2", 0.0, 0),
            ForecastRecord("m3", 1.0, 1),
        ]

        brier = _brier_score(forecasts)
        assert brier == 0.0

    def test_brier_score_worst(self):
        """Test Brier score with worst forecasts."""
        forecasts = [
            ForecastRecord("m1", 0.0, 1),
            ForecastRecord("m2", 1.0, 0),
            ForecastRecord("m3", 0.0, 1),
        ]

        brier = _brier_score(forecasts)
        assert brier == 1.0

    def test_brier_score_neutral(self):
        """Test Brier score with 50/50 forecasts."""
        forecasts = [
            ForecastRecord("m1", 0.5, 1),
            ForecastRecord("m2", 0.5, 0),
            ForecastRecord("m3", 0.5, 1),
        ]

        brier = _brier_score(forecasts)
        assert brier == 0.25  # (0.5-1)^2 + (0.5-0)^2 + (0.5-1)^2 / 3


class TestExecutionMetrics:
    """Test execution quality metrics."""

    def test_calculate_slippage(self):
        """Test slippage calculation."""
        trades = [
            TradeRecord(
                "m1", "buy", "market", 100, 100, 0.52, 0.50, 0.51, 1,
                pnl=0, slippage_bps=400, market_impact_bps=200,
                implementation_shortfall_bps=410, fill_rate=1.0
            ),
            TradeRecord(
                "m2", "sell", "market", 100, 100, 0.48, 0.50, 0.49, 0,
                pnl=0, slippage_bps=400, market_impact_bps=200,
                implementation_shortfall_bps=410, fill_rate=1.0
            ),
        ]

        slippage = ExecutionMetrics.calculate_slippage(trades)
        assert slippage == 400.0

    def test_calculate_fill_rate(self):
        """Test fill rate calculation."""
        trades = [
            TradeRecord(
                "m1", "buy", "limit", 100, 75, 0.48, 0.50, 0.51, 1,
                pnl=0, slippage_bps=0, market_impact_bps=0,
                implementation_shortfall_bps=0, fill_rate=0.75
            ),
            TradeRecord(
                "m2", "buy", "limit", 100, 50, 0.48, 0.50, 0.49, 1,
                pnl=0, slippage_bps=0, market_impact_bps=0,
                implementation_shortfall_bps=0, fill_rate=0.50
            ),
        ]

        fill_rate = ExecutionMetrics.calculate_fill_rate(trades)
        assert fill_rate == 0.625  # (0.75 + 0.50) / 2


class TestEvaluateAll:
    """Test comprehensive evaluation function."""

    def test_evaluate_all(self):
        """Test comprehensive evaluation with forecasts and trades."""
        forecasts = [
            ForecastRecord("m1", 0.6, 1),
            ForecastRecord("m2", 0.4, 0),
        ]

        trades = [
            TradeRecord(
                "m1", "buy", "market", 100, 100, 0.52, 0.50, 0.51, 1,
                pnl=10.0, slippage_bps=400, market_impact_bps=200,
                implementation_shortfall_bps=410, fill_rate=1.0
            ),
            TradeRecord(
                "m2", "sell", "market", 100, 100, 0.48, 0.50, 0.49, 0,
                pnl=15.0, slippage_bps=400, market_impact_bps=200,
                implementation_shortfall_bps=410, fill_rate=1.0
            ),
        ]

        metrics = evaluate_all(forecasts, trades)

        assert "brier_score" in metrics
        assert "total_pnl" in metrics
        assert "sharpe" in metrics
        assert "avg_slippage_bps" in metrics
        assert "fill_rate" in metrics

        assert metrics["total_pnl"] == 25.0
        assert metrics["num_trades"] == 2.0
        assert metrics["fill_rate"] == 1.0
