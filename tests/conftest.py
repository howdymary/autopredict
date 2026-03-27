"""Pytest fixtures for AutoPredict test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autopredict.market_env import BookLevel, OrderBook, ExecutionEngine
from autopredict.agent import AgentConfig, AutoPredictAgent, MarketState


@pytest.fixture
def base_path() -> Path:
    """Return base path for autopredict project."""
    return Path(__file__).parent.parent


@pytest.fixture
def datasets_path(base_path: Path) -> Path:
    """Return path to datasets directory."""
    return base_path / "datasets"


@pytest.fixture
def sample_markets(datasets_path: Path) -> list[dict[str, Any]]:
    """Load sample markets from minimal test dataset."""
    with open(datasets_path / "test_markets_minimal.json") as f:
        return json.load(f)


@pytest.fixture
def simple_order_book() -> OrderBook:
    """Create a simple order book for testing."""
    return OrderBook(
        market_id="test-market",
        bids=[
            BookLevel(0.48, 100.0),
            BookLevel(0.47, 150.0),
            BookLevel(0.46, 200.0),
        ],
        asks=[
            BookLevel(0.52, 110.0),
            BookLevel(0.53, 160.0),
            BookLevel(0.54, 210.0),
        ],
    )


@pytest.fixture
def tight_spread_book() -> OrderBook:
    """Create an order book with tight spread."""
    return OrderBook(
        market_id="tight-spread",
        bids=[
            BookLevel(0.595, 200.0),
            BookLevel(0.590, 250.0),
            BookLevel(0.585, 300.0),
        ],
        asks=[
            BookLevel(0.605, 200.0),
            BookLevel(0.610, 250.0),
            BookLevel(0.615, 300.0),
        ],
    )


@pytest.fixture
def wide_spread_book() -> OrderBook:
    """Create an order book with wide spread."""
    return OrderBook(
        market_id="wide-spread",
        bids=[
            BookLevel(0.40, 50.0),
            BookLevel(0.38, 75.0),
            BookLevel(0.36, 100.0),
        ],
        asks=[
            BookLevel(0.50, 50.0),
            BookLevel(0.52, 75.0),
            BookLevel(0.54, 100.0),
        ],
    )


@pytest.fixture
def thin_book() -> OrderBook:
    """Create a thin order book with low liquidity."""
    return OrderBook(
        market_id="thin-book",
        bids=[
            BookLevel(0.48, 20.0),
            BookLevel(0.47, 25.0),
        ],
        asks=[
            BookLevel(0.52, 20.0),
            BookLevel(0.53, 25.0),
        ],
    )


@pytest.fixture
def deep_book() -> OrderBook:
    """Create a deep order book with high liquidity."""
    return OrderBook(
        market_id="deep-book",
        bids=[
            BookLevel(0.48, 500.0),
            BookLevel(0.47, 600.0),
            BookLevel(0.46, 700.0),
            BookLevel(0.45, 800.0),
        ],
        asks=[
            BookLevel(0.52, 500.0),
            BookLevel(0.53, 600.0),
            BookLevel(0.54, 700.0),
            BookLevel(0.55, 800.0),
        ],
    )


@pytest.fixture
def execution_engine() -> ExecutionEngine:
    """Create execution engine with no fees."""
    return ExecutionEngine(maker_fee_bps=0.0, taker_fee_bps=0.0)


@pytest.fixture
def execution_engine_with_fees() -> ExecutionEngine:
    """Create execution engine with realistic fees."""
    return ExecutionEngine(maker_fee_bps=5.0, taker_fee_bps=10.0)


@pytest.fixture
def baseline_agent() -> AutoPredictAgent:
    """Create agent with baseline configuration."""
    return AutoPredictAgent()


@pytest.fixture
def conservative_agent() -> AutoPredictAgent:
    """Create agent with conservative configuration."""
    config = AgentConfig(
        min_edge=0.08,
        aggressive_edge=0.15,
        max_risk_fraction=0.01,
        max_position_notional=15.0,
        min_book_liquidity=100.0,
        max_spread_pct=0.03,
    )
    return AutoPredictAgent(config)


@pytest.fixture
def aggressive_agent() -> AutoPredictAgent:
    """Create agent with aggressive configuration."""
    config = AgentConfig(
        min_edge=0.03,
        aggressive_edge=0.08,
        max_risk_fraction=0.05,
        max_position_notional=50.0,
        min_book_liquidity=30.0,
        max_spread_pct=0.08,
    )
    return AutoPredictAgent(config)


@pytest.fixture
def sample_market_state(simple_order_book: OrderBook) -> MarketState:
    """Create a sample market state for testing."""
    return MarketState(
        market_id="test-market",
        market_prob=0.50,
        fair_prob=0.58,
        time_to_expiry_hours=48.0,
        order_book=simple_order_book,
        metadata={"category": "test"},
    )


@pytest.fixture
def edge_case_markets() -> list[dict[str, Any]]:
    """Create edge case market scenarios."""
    return [
        {
            "market_id": "extreme-low-prob",
            "category": "test",
            "market_prob": 0.02,
            "fair_prob": 0.05,
            "outcome": 0,
            "time_to_expiry_hours": 24.0,
            "next_mid_price": 0.03,
            "order_book": {
                "bids": [[0.01, 50.0], [0.005, 75.0]],
                "asks": [[0.03, 50.0], [0.04, 75.0]],
            },
        },
        {
            "market_id": "extreme-high-prob",
            "category": "test",
            "market_prob": 0.98,
            "fair_prob": 0.95,
            "outcome": 1,
            "time_to_expiry_hours": 24.0,
            "next_mid_price": 0.97,
            "order_book": {
                "bids": [[0.97, 50.0], [0.96, 75.0]],
                "asks": [[0.99, 50.0], [0.995, 75.0]],
            },
        },
        {
            "market_id": "near-expiry",
            "category": "test",
            "market_prob": 0.60,
            "fair_prob": 0.72,
            "outcome": 1,
            "time_to_expiry_hours": 1.0,
            "next_mid_price": 0.68,
            "order_book": {
                "bids": [[0.59, 100.0], [0.58, 120.0]],
                "asks": [[0.61, 100.0], [0.62, 120.0]],
            },
        },
    ]
