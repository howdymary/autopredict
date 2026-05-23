"""Tests for AutoPredict agent decision logic."""

from __future__ import annotations

import pytest

from autopredict.agent import (
    AgentConfig,
    AutoPredictAgent,
    ExecutionStrategy,
    MarketState,
)
from autopredict.market_env import OrderBook, BookLevel


class TestAgentConfig:
    """Test agent configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AgentConfig()

        assert config.min_edge == 0.05
        assert config.aggressive_edge == 0.12
        assert config.max_risk_fraction == 0.02
        assert config.max_position_notional == 25.0

    def test_custom_config(self):
        """Test custom configuration."""
        config = AgentConfig(
            min_edge=0.08,
            aggressive_edge=0.15,
            max_risk_fraction=0.03,
        )

        assert config.min_edge == 0.08
        assert config.aggressive_edge == 0.15
        assert config.max_risk_fraction == 0.03


class TestExecutionStrategy:
    """Test execution strategy decisions."""

    def test_decide_order_type_aggressive(self):
        """Test order type decision for aggressive edges."""
        strategy = ExecutionStrategy()

        order_type = strategy.decide_order_type(
            edge=0.15,
            spread_pct=0.02,
            liquidity_depth=500.0,
            time_to_expiry_hours=48.0,
            aggressive_edge=0.12,
            mid_price=0.50,
        )

        assert order_type == "market"

    def test_decide_order_type_passive(self):
        """Test order type decision for smaller edges."""
        strategy = ExecutionStrategy()

        order_type = strategy.decide_order_type(
            edge=0.06,
            spread_pct=0.02,
            liquidity_depth=500.0,
            time_to_expiry_hours=48.0,
            aggressive_edge=0.12,
            mid_price=0.50,
        )

        assert order_type == "limit"

    def test_decide_order_type_urgent(self):
        """Test order type decision for urgent markets."""
        strategy = ExecutionStrategy()

        # Moderate edge but urgent expiry
        order_type = strategy.decide_order_type(
            edge=0.10,
            spread_pct=0.02,
            liquidity_depth=500.0,
            time_to_expiry_hours=6.0,  # Urgent
            aggressive_edge=0.12,
            mid_price=0.50,
        )

        assert order_type == "market"

    def test_calculate_trade_size(self):
        """Test trade size calculation."""
        strategy = ExecutionStrategy()
        config = AgentConfig()

        liquidity_depth = 500.0
        size = strategy.calculate_trade_size(
            edge=0.08,
            bankroll=1000.0,
            liquidity_depth=liquidity_depth,
            config=config,
        )

        # Should be capped by multiple factors
        assert size > 0
        assert size <= config.max_position_notional
        assert size <= liquidity_depth * config.max_depth_fraction

    def test_calculate_trade_size_scales_with_edge(self):
        """Test that trade size scales with edge."""
        strategy = ExecutionStrategy()
        config = AgentConfig()

        small_edge_size = strategy.calculate_trade_size(
            edge=0.05,
            bankroll=1000.0,
            liquidity_depth=500.0,
            config=config,
        )

        large_edge_size = strategy.calculate_trade_size(
            edge=0.15,
            bankroll=1000.0,
            liquidity_depth=500.0,
            config=config,
        )

        assert large_edge_size > small_edge_size

    def test_should_split_order(self):
        """Test order splitting decision."""
        strategy = ExecutionStrategy()
        config = AgentConfig()

        book = OrderBook(
            market_id="test",
            bids=[BookLevel(0.48, 100.0), BookLevel(0.47, 100.0)],
            asks=[BookLevel(0.52, 100.0), BookLevel(0.53, 100.0)],
        )

        # Large size should trigger split
        should_split = strategy.should_split_order(
            desired_size=100.0, order_book=book, config=config
        )
        assert should_split is True

        # Small size should not split
        should_split = strategy.should_split_order(
            desired_size=20.0, order_book=book, config=config
        )
        assert should_split is False

    def test_split_order(self):
        """Test order splitting."""
        strategy = ExecutionStrategy()

        splits = strategy.split_order(desired_size=300.0, slices=3)

        assert len(splits) == 3
        assert sum(splits) == 300.0
        assert all(s > 0 for s in splits)


class TestAutoPredictAgent:
    """Test AutoPredict agent."""

    def test_agent_creation(self):
        """Test agent creation with default config."""
        agent = AutoPredictAgent()

        assert agent.config is not None
        assert agent.execution is not None

    def test_agent_from_mapping(self):
        """Test agent creation from config mapping."""
        config_data = {
            "min_edge": 0.08,
            "aggressive_edge": 0.15,
            "max_risk_fraction": 0.03,
        }

        agent = AutoPredictAgent.from_mapping(config_data)

        assert agent.config.min_edge == 0.08
        assert agent.config.aggressive_edge == 0.15
        assert agent.config.max_risk_fraction == 0.03

    def test_evaluate_market_no_edge(self, baseline_agent: AutoPredictAgent):
        """Test that agent rejects markets with no edge."""
        book = OrderBook(
            market_id="no-edge",
            bids=[BookLevel(0.48, 100.0)],
            asks=[BookLevel(0.52, 100.0)],
        )

        market = MarketState(
            market_id="no-edge",
            market_prob=0.50,
            fair_prob=0.51,  # Only 1% edge (below min_edge)
            time_to_expiry_hours=48.0,
            order_book=book,
        )

        proposal = baseline_agent.evaluate_market(market, bankroll=1000.0)
        assert proposal is None

    def test_evaluate_market_insufficient_liquidity(
        self, baseline_agent: AutoPredictAgent
    ):
        """Test that agent rejects markets with low liquidity."""
        book = OrderBook(
            market_id="thin",
            bids=[BookLevel(0.40, 10.0)],
            asks=[BookLevel(0.50, 10.0)],
        )

        market = MarketState(
            market_id="thin",
            market_prob=0.45,
            fair_prob=0.60,  # Good edge
            time_to_expiry_hours=48.0,
            order_book=book,
        )

        proposal = baseline_agent.evaluate_market(market, bankroll=1000.0)
        assert proposal is None  # Rejected due to low liquidity

    def test_evaluate_market_wide_spread(self, baseline_agent: AutoPredictAgent):
        """Test that agent rejects markets with wide spreads (unless aggressive edge)."""
        book = OrderBook(
            market_id="wide",
            bids=[BookLevel(0.40, 200.0)],
            asks=[BookLevel(0.50, 200.0)],
        )

        market = MarketState(
            market_id="wide",
            market_prob=0.45,
            fair_prob=0.52,  # Moderate edge
            time_to_expiry_hours=48.0,
            order_book=book,
        )

        proposal = baseline_agent.evaluate_market(market, bankroll=1000.0)
        assert proposal is None  # Rejected due to wide spread

    def test_evaluate_market_accept_buy(self, baseline_agent: AutoPredictAgent):
        """Test agent accepts good buy opportunity."""
        book = OrderBook(
            market_id="good-buy",
            bids=[BookLevel(0.48, 200.0), BookLevel(0.47, 250.0)],
            asks=[BookLevel(0.52, 200.0), BookLevel(0.53, 250.0)],
        )

        market = MarketState(
            market_id="good-buy",
            market_prob=0.50,
            fair_prob=0.62,  # 12% edge (positive = buy)
            time_to_expiry_hours=48.0,
            order_book=book,
        )

        proposal = baseline_agent.evaluate_market(market, bankroll=1000.0)

        assert proposal is not None
        assert proposal.side == "buy"
        assert proposal.size > 0
        assert proposal.market_id == "good-buy"

    def test_evaluate_market_accept_sell(self, baseline_agent: AutoPredictAgent):
        """Test agent accepts good sell opportunity."""
        book = OrderBook(
            market_id="good-sell",
            bids=[BookLevel(0.58, 200.0), BookLevel(0.57, 250.0)],
            asks=[BookLevel(0.62, 200.0), BookLevel(0.63, 250.0)],
        )

        market = MarketState(
            market_id="good-sell",
            market_prob=0.60,
            fair_prob=0.48,  # -12% edge (negative = sell)
            time_to_expiry_hours=48.0,
            order_book=book,
        )

        proposal = baseline_agent.evaluate_market(market, bankroll=1000.0)

        assert proposal is not None
        assert proposal.side == "sell"
        assert proposal.size > 0

    def test_evaluate_market_limit_price(self, baseline_agent: AutoPredictAgent):
        """Test that limit orders get proper limit price."""
        book = OrderBook(
            market_id="limit-test",
            bids=[BookLevel(0.48, 200.0)],
            asks=[BookLevel(0.52, 200.0)],
        )

        market = MarketState(
            market_id="limit-test",
            market_prob=0.50,
            fair_prob=0.58,  # Moderate edge -> likely limit order
            time_to_expiry_hours=48.0,
            order_book=book,
        )

        proposal = baseline_agent.evaluate_market(market, bankroll=1000.0)

        if proposal and proposal.order_type == "limit":
            assert proposal.limit_price is not None
            if proposal.side == "buy":
                assert proposal.limit_price == 0.48  # Best bid
            else:
                assert proposal.limit_price == 0.52  # Best ask

    def test_evaluate_market_aggressive_execution(
        self, baseline_agent: AutoPredictAgent
    ):
        """Test that large edges trigger aggressive execution."""
        book = OrderBook(
            market_id="aggressive",
            bids=[BookLevel(0.40, 200.0)],
            asks=[BookLevel(0.44, 200.0)],
        )

        market = MarketState(
            market_id="aggressive",
            market_prob=0.42,
            fair_prob=0.65,  # 23% edge -> very aggressive
            time_to_expiry_hours=48.0,
            order_book=book,
        )

        proposal = baseline_agent.evaluate_market(market, bankroll=1000.0)

        assert proposal is not None
        assert proposal.order_type == "market"  # Should use market order

    def test_conservative_agent(self, conservative_agent: AutoPredictAgent):
        """Test conservative agent rejects more markets."""
        book = OrderBook(
            market_id="test",
            bids=[BookLevel(0.48, 200.0)],
            asks=[BookLevel(0.52, 200.0)],
        )

        # Moderate edge that baseline would take
        market = MarketState(
            market_id="test",
            market_prob=0.50,
            fair_prob=0.56,  # 6% edge
            time_to_expiry_hours=48.0,
            order_book=book,
        )

        proposal = conservative_agent.evaluate_market(market, bankroll=1000.0)
        assert proposal is None  # Conservative agent requires min_edge=0.08

    def test_aggressive_agent(self, aggressive_agent: AutoPredictAgent):
        """Test aggressive agent accepts more markets."""
        book = OrderBook(
            market_id="test",
            bids=[BookLevel(0.495, 100.0)],  # Tighter spread
            asks=[BookLevel(0.505, 100.0)],  # Spread = 2% (under max_spread_pct=0.08)
        )

        # Small edge that aggressive agent accepts
        market = MarketState(
            market_id="test",
            market_prob=0.50,
            fair_prob=0.54,  # 4% edge (above aggressive min_edge of 0.03)
            time_to_expiry_hours=48.0,
            order_book=book,
        )

        proposal = aggressive_agent.evaluate_market(market, bankroll=1000.0)
        # Aggressive agent requires min_book_liquidity=30 and min_edge=0.03, so should accept
        assert proposal is not None

    def test_analyze_performance(self, baseline_agent: AutoPredictAgent):
        """Test performance analysis."""
        metrics = {
            "avg_slippage_bps": 20.0,
            "fill_rate": 0.65,
            "brier_score": 0.18,
            "max_drawdown": 50.0,
        }

        analysis = baseline_agent.analyze_performance(metrics, guidance="")

        assert "weakness" in analysis
        assert "hypothesis" in analysis

    def test_analyze_performance_high_slippage(
        self, baseline_agent: AutoPredictAgent
    ):
        """Test that high slippage is detected."""
        metrics = {
            "avg_slippage_bps": 25.0,
            "fill_rate": 0.65,
            "brier_score": 0.18,
            "max_drawdown": 50.0,
        }

        analysis = baseline_agent.analyze_performance(metrics, guidance="")

        assert analysis["weakness"] == "execution_quality"

    def test_analyze_performance_low_fill_rate(
        self, baseline_agent: AutoPredictAgent
    ):
        """Test that low fill rate is detected."""
        metrics = {
            "avg_slippage_bps": 10.0,
            "fill_rate": 0.25,
            "brier_score": 0.18,
            "max_drawdown": 50.0,
        }

        analysis = baseline_agent.analyze_performance(metrics, guidance="")

        assert analysis["weakness"] == "limit_fill_quality"

    def test_analyze_performance_external_forecast_quality(
        self, baseline_agent: AutoPredictAgent
    ):
        """External forecast metrics should not be attributed to agent calibration."""
        metrics = {
            "avg_slippage_bps": 10.0,
            "fill_rate": 0.65,
            "brier_score": 0.25,
            "max_drawdown": 50.0,
            "forecast_source": "dataset_fair_prob",
        }

        analysis = baseline_agent.analyze_performance(metrics, guidance="")

        assert analysis["weakness"] == "forecast_input_quality"
