"""Tests for the learning module."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from autopredict.learning.logger import TradeLog, TradeLogger
from autopredict.learning.analyzer import PerformanceAnalyzer
from autopredict.learning.tuner import (
    ParameterGrid,
    GridSearchTuner,
    BacktestResult,
    create_param_grid_from_current,
)


@pytest.fixture
def sample_log():
    """Create a sample trade log."""
    return TradeLog(
        timestamp=datetime.now(timezone.utc),
        market_id="test-market-1",
        market_prob=0.45,
        model_prob=0.65,
        edge=0.20,
        decision="buy",
        size=20.0,
        execution_price=0.46,
        outcome=1,
        pnl=10.8,  # 20 * (1 - 0.46)
        rationale={
            "order_type": "limit",
            "spread_pct": 0.02,
            "liquidity_depth": 200.0,
            "category": "politics",
        }
    )


@pytest.fixture
def sample_logs():
    """Create multiple sample trade logs."""
    base_time = datetime.now(timezone.utc) - timedelta(days=7)
    logs = []

    # Create 20 trades with varying outcomes
    for i in range(20):
        decision = "buy" if i % 3 != 0 else "sell" if i % 3 == 1 else "pass"
        size = 15.0 if decision != "pass" else 0.0
        execution_price = 0.45 if decision != "pass" else None
        outcome = 1 if i % 2 == 0 else 0 if decision != "pass" else None

        pnl = None
        if decision == "buy" and outcome is not None:
            pnl = size * (outcome - execution_price)
        elif decision == "sell" and outcome is not None:
            pnl = size * (execution_price - outcome)

        log = TradeLog(
            timestamp=base_time + timedelta(hours=i * 6),
            market_id=f"market-{i % 5}",
            market_prob=0.45,
            model_prob=0.65 if decision == "buy" else 0.25,
            edge=0.20,
            decision=decision,
            size=size,
            execution_price=execution_price,
            outcome=outcome,
            pnl=pnl,
            rationale={
                "category": "politics" if i % 2 == 0 else "sports",
                "spread_pct": 0.02,
                "liquidity_depth": 100.0,
            }
        )
        logs.append(log)

    return logs


class TestTradeLog:
    """Tests for TradeLog."""

    def test_to_dict(self, sample_log):
        """Test conversion to dictionary."""
        data = sample_log.to_dict()
        assert isinstance(data, dict)
        assert data["market_id"] == "test-market-1"
        assert data["decision"] == "buy"
        assert isinstance(data["timestamp"], str)

    def test_from_dict(self, sample_log):
        """Test reconstruction from dictionary."""
        data = sample_log.to_dict()
        reconstructed = TradeLog.from_dict(data)
        assert reconstructed.market_id == sample_log.market_id
        assert reconstructed.decision == sample_log.decision
        assert reconstructed.pnl == sample_log.pnl

    def test_jsonl_roundtrip(self, sample_log):
        """Test JSONL serialization roundtrip."""
        jsonl = sample_log.to_jsonl()
        assert isinstance(jsonl, str)
        assert "\n" not in jsonl  # Single line

        reconstructed = TradeLog.from_jsonl(jsonl)
        assert reconstructed.market_id == sample_log.market_id
        assert reconstructed.pnl == sample_log.pnl


class TestTradeLogger:
    """Tests for TradeLogger."""

    def test_append_and_load(self, sample_log):
        """Test appending and loading logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TradeLogger(Path(tmpdir))

            # Append log
            logger.append(sample_log)

            # Load back
            logs = logger.load_all()
            assert len(logs) == 1
            assert logs[0].market_id == sample_log.market_id

    def test_append_batch(self, sample_logs):
        """Test batch appending."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TradeLogger(Path(tmpdir))

            # Append batch
            logger.append_batch(sample_logs)

            # Load back
            logs = logger.load_all()
            assert len(logs) == len(sample_logs)

    def test_load_recent(self, sample_logs):
        """Test loading recent logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TradeLogger(Path(tmpdir))
            logger.append_batch(sample_logs)

            # Load last 3 days
            recent = logger.load_recent(days=3)
            # Should get some but not all logs
            assert 0 < len(recent) <= len(sample_logs)

    def test_load_by_market(self, sample_logs):
        """Test loading logs by market."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TradeLogger(Path(tmpdir))
            logger.append_batch(sample_logs)

            # Load specific market
            market_logs = logger.load_by_market("market-0")
            assert all(log.market_id == "market-0" for log in market_logs)

    def test_update_outcomes(self, sample_logs):
        """Test updating outcomes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TradeLogger(Path(tmpdir))

            # Create logs without outcomes (only keep non-pass decisions for clearer test)
            logs = [log for log in sample_logs[:5] if log.decision != "pass"]
            for log in logs:
                log.outcome = None
                log.pnl = None

            logger.append_batch(logs)

            # Update outcomes
            market_outcomes = {log.market_id: 1 for log in logs}
            updated = logger.update_outcomes(market_outcomes)
            assert updated >= len(logs)  # May update multiple logs per market

            # Verify outcomes updated
            loaded = logger.load_all()
            for log in loaded:
                if log.decision != "pass":
                    assert log.outcome == 1
                    assert log.pnl is not None


class TestPerformanceAnalyzer:
    """Tests for PerformanceAnalyzer."""

    def test_basic_analysis(self, sample_logs):
        """Test basic performance metrics."""
        analyzer = PerformanceAnalyzer(sample_logs)
        report = analyzer.generate_report()

        assert report.total_trades > 0
        assert isinstance(report.total_pnl, float)
        assert 0 <= report.win_rate <= 1
        assert report.by_decision["buy"] > 0

    def test_analyze_by_market(self, sample_logs):
        """Test market-level analysis."""
        analyzer = PerformanceAnalyzer(sample_logs)
        market_stats = analyzer.analyze_by_market()

        assert len(market_stats) > 0
        for market_id, stats in market_stats.items():
            assert "trades" in stats
            assert "pnl" in stats
            assert "win_rate" in stats

    def test_analyze_by_category(self, sample_logs):
        """Test category-level analysis."""
        analyzer = PerformanceAnalyzer(sample_logs)
        category_stats = analyzer.analyze_by_category("category")

        assert "politics" in category_stats
        assert "sports" in category_stats

    def test_calibration_error(self, sample_logs):
        """Test calibration error calculation."""
        analyzer = PerformanceAnalyzer(sample_logs)
        cal_error = analyzer.calculate_calibration_error()

        assert 0 <= cal_error <= 1

    def test_edge_capture_rate(self, sample_logs):
        """Test edge capture rate calculation."""
        analyzer = PerformanceAnalyzer(sample_logs)
        edge_capture = analyzer.calculate_edge_capture_rate()

        assert isinstance(edge_capture, float)


class TestParameterGrid:
    """Tests for ParameterGrid."""

    def test_grid_creation(self):
        """Test creating parameter grid."""
        grid = ParameterGrid({
            "min_edge": [0.03, 0.05, 0.08],
            "max_risk": [0.01, 0.02],
        })

        # Should have 3 × 2 = 6 combinations
        combinations = list(grid)
        assert len(combinations) == 6

        # Check first combination
        assert combinations[0]["min_edge"] == 0.03
        assert combinations[0]["max_risk"] == 0.01

    def test_grid_len(self):
        """Test grid length calculation."""
        grid = ParameterGrid({
            "a": [1, 2, 3],
            "b": [10, 20],
            "c": [100],
        })

        assert len(grid) == 6  # 3 × 2 × 1

    def test_create_param_grid_from_current(self):
        """Test auto-generating grid from current params."""
        current = {"min_edge": 0.05, "aggressive_edge": 0.12}

        grid = create_param_grid_from_current(
            current,
            perturbation_factor=0.2,
            n_steps=2,
        )

        combinations = list(grid)
        assert len(combinations) > 0

        # Should include current value
        center_combos = [
            c for c in combinations
            if abs(c["min_edge"] - 0.05) < 0.001
        ]
        assert len(center_combos) > 0


class TestGridSearchTuner:
    """Tests for GridSearchTuner."""

    def test_basic_tuning(self):
        """Test basic grid search."""
        param_grid = ParameterGrid({
            "min_edge": [0.03, 0.05, 0.08],
            "aggressive_edge": [0.10, 0.12],
        })

        # Mock backtest function
        def mock_backtest(params: dict) -> BacktestResult:
            # Better score for min_edge=0.05
            score = 1.0 - abs(params["min_edge"] - 0.05)
            return BacktestResult(
                params=params,
                total_pnl=score * 100,
                sharpe_ratio=score,
                win_rate=0.55,
                total_trades=20,
                calibration_error=0.1,
                edge_capture_rate=0.6,
            )

        tuner = GridSearchTuner(
            param_grid=param_grid,
            backtest_fn=mock_backtest,
            verbose=False,
        )

        best_params, best_result = tuner.tune()

        # Should find min_edge=0.05
        assert best_params["min_edge"] == 0.05
        assert best_result.sharpe_ratio is not None

    def test_get_top_n(self):
        """Test getting top N results."""
        param_grid = ParameterGrid({
            "min_edge": [0.03, 0.05, 0.08],
        })

        def mock_backtest(params: dict) -> BacktestResult:
            return BacktestResult(
                params=params,
                total_pnl=params["min_edge"] * 100,
                sharpe_ratio=params["min_edge"],
                win_rate=0.5,
                total_trades=20,
                calibration_error=0.1,
                edge_capture_rate=0.6,
            )

        tuner = GridSearchTuner(param_grid, mock_backtest, verbose=False)
        tuner.tune()

        top_3 = tuner.get_top_n(3)
        assert len(top_3) == 3

        # Should be sorted by score
        scores = [r.score() for _, r in top_3]
        assert scores == sorted(scores, reverse=True)

    def test_save_results(self):
        """Test saving tuning results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            param_grid = ParameterGrid({"min_edge": [0.05, 0.08]})

            def mock_backtest(params: dict) -> BacktestResult:
                return BacktestResult(
                    params=params,
                    total_pnl=10.0,
                    sharpe_ratio=0.5,
                    win_rate=0.55,
                    total_trades=20,
                    calibration_error=0.1,
                    edge_capture_rate=0.6,
                )

            tuner = GridSearchTuner(param_grid, mock_backtest, verbose=False)
            tuner.tune()

            # Save results
            output_path = Path(tmpdir) / "results.json"
            tuner.save_results(output_path)

            # Verify saved
            assert output_path.exists()
            with output_path.open() as f:
                data = json.load(f)
                assert "results" in data
                assert len(data["results"]) == 2
