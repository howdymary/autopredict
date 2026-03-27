"""Tests for monitoring and logging system."""

import json
import tempfile
from pathlib import Path

import pytest

from autopredict.config import LoggingConfig
from autopredict.live.monitor import (
    Monitor,
    TradeLog,
    DecisionLog,
    PerformanceSnapshot,
    create_trade_log,
    create_decision_log,
)


class TestTradeLog:
    """Test TradeLog data structure."""

    def test_creation(self):
        """Test trade log creation."""
        log = TradeLog(
            timestamp="2026-03-26T12:00:00",
            market_id="test_market",
            side="buy",
            order_type="market",
            size=100.0,
            price=0.55,
            commission=1.0,
            slippage_bps=5.0,
            execution_mode="paper",
            success=True,
        )

        assert log.market_id == "test_market"
        assert log.side == "buy"
        assert log.success

    def test_to_json(self):
        """Test JSON serialization."""
        log = TradeLog(
            timestamp="2026-03-26T12:00:00",
            market_id="test",
            side="buy",
            order_type="market",
            size=100.0,
            price=0.55,
            commission=1.0,
            slippage_bps=5.0,
            execution_mode="paper",
            success=True,
        )

        json_str = log.to_json()
        data = json.loads(json_str)

        assert data["market_id"] == "test"
        assert data["size"] == 100.0
        assert data["success"] is True


class TestDecisionLog:
    """Test DecisionLog data structure."""

    def test_creation(self):
        """Test decision log creation."""
        log = DecisionLog(
            timestamp="2026-03-26T12:00:00",
            market_id="test",
            decision="trade",
            reason="Strong edge detected",
            edge=0.15,
            market_price=0.50,
            fair_price=0.65,
            proposed_size=100.0,
            proposed_side="buy",
        )

        assert log.decision == "trade"
        assert log.edge == 0.15

    def test_to_json(self):
        """Test JSON serialization."""
        log = DecisionLog(
            timestamp="2026-03-26T12:00:00",
            market_id="test",
            decision="skip",
            reason="Edge too small",
            edge=0.02,
            market_price=0.50,
            fair_price=0.52,
        )

        json_str = log.to_json()
        data = json.loads(json_str)

        assert data["decision"] == "skip"
        assert data["edge"] == 0.02


class TestPerformanceSnapshot:
    """Test PerformanceSnapshot data structure."""

    def test_creation(self):
        """Test performance snapshot creation."""
        snapshot = PerformanceSnapshot(
            timestamp="2026-03-26T12:00:00",
            total_pnl=150.0,
            daily_pnl=25.0,
            num_trades=10,
            num_positions=3,
            total_exposure=500.0,
            win_rate=0.6,
        )

        assert snapshot.total_pnl == 150.0
        assert snapshot.win_rate == 0.6

    def test_to_json(self):
        """Test JSON serialization."""
        snapshot = PerformanceSnapshot(
            timestamp="2026-03-26T12:00:00",
            total_pnl=150.0,
            daily_pnl=25.0,
            num_trades=10,
            num_positions=3,
            total_exposure=500.0,
        )

        json_str = snapshot.to_json()
        data = json.loads(json_str)

        assert data["total_pnl"] == 150.0
        assert data["num_trades"] == 10


class TestMonitor:
    """Test Monitor logging system."""

    def test_initialization(self):
        """Test monitor initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(log_dir=tmpdir)
            monitor = Monitor(config)

            # Check log directory created
            assert Path(tmpdir).exists()

            # Check log files
            log_files = monitor.get_log_files()
            assert "trades" in log_files
            assert "decisions" in log_files
            assert "errors" in log_files
            assert "performance" in log_files

    def test_log_trade(self):
        """Test trade logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(log_dir=tmpdir, console_output=False)
            monitor = Monitor(config)

            trade_log = create_trade_log(
                market_id="test",
                side="buy",
                order_type="market",
                size=100.0,
                price=0.55,
                commission=1.0,
                slippage_bps=5.0,
                execution_mode="paper",
                success=True,
            )

            monitor.log_trade(trade_log)

            # Check that log file was written
            trades_file = Path(tmpdir) / "trades.jsonl"
            assert trades_file.exists()

            # Read and verify content
            with open(trades_file) as f:
                lines = f.readlines()
                assert len(lines) == 1
                data = json.loads(lines[0])
                assert data["market_id"] == "test"
                assert data["size"] == 100.0

    def test_log_decision(self):
        """Test decision logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(log_dir=tmpdir, console_output=False)
            monitor = Monitor(config)

            decision_log = create_decision_log(
                market_id="test",
                decision="skip",
                reason="Edge too small",
                edge=0.02,
                market_price=0.50,
                fair_price=0.52,
            )

            monitor.log_decision(decision_log)

            # Check that log file was written
            decisions_file = Path(tmpdir) / "decisions.jsonl"
            assert decisions_file.exists()

            with open(decisions_file) as f:
                lines = f.readlines()
                assert len(lines) == 1
                data = json.loads(lines[0])
                assert data["decision"] == "skip"

    def test_log_error(self):
        """Test error logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(log_dir=tmpdir, console_output=False)
            monitor = Monitor(config)

            error = ValueError("Test error")
            monitor.log_error(error, {"context": "test_context"})

            # Check that error file was written
            errors_file = Path(tmpdir) / "errors.log"
            assert errors_file.exists()

    def test_log_performance(self):
        """Test performance logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(log_dir=tmpdir, console_output=False)
            monitor = Monitor(config)

            snapshot = PerformanceSnapshot(
                timestamp="2026-03-26T12:00:00",
                total_pnl=100.0,
                daily_pnl=20.0,
                num_trades=5,
                num_positions=2,
                total_exposure=300.0,
            )

            monitor.log_performance(snapshot)

            # Check that performance file was written
            perf_file = Path(tmpdir) / "performance.jsonl"
            assert perf_file.exists()

            with open(perf_file) as f:
                lines = f.readlines()
                assert len(lines) == 1
                data = json.loads(lines[0])
                assert data["total_pnl"] == 100.0

    def test_logging_disabled(self):
        """Test that logging can be disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(
                log_dir=tmpdir,
                log_trades=False,
                log_decisions=False,
                console_output=False,
            )
            monitor = Monitor(config)

            # Log trade (should be ignored)
            trade_log = create_trade_log(
                market_id="test",
                side="buy",
                order_type="market",
                size=100.0,
                price=0.55,
                commission=1.0,
                slippage_bps=5.0,
                execution_mode="paper",
                success=True,
            )
            monitor.log_trade(trade_log)

            # File should not have trade entry (only created, possibly empty)
            trades_file = Path(tmpdir) / "trades.jsonl"
            if trades_file.exists():
                with open(trades_file) as f:
                    content = f.read()
                    assert len(content.strip()) == 0

    def test_get_live_metrics(self):
        """Test live metrics retrieval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(log_dir=tmpdir, console_output=False)
            monitor = Monitor(config)

            metrics = monitor.get_live_metrics()

            assert "timestamp" in metrics
            assert "trade_count" in metrics
            assert "decision_count" in metrics
            assert "error_count" in metrics

    def test_should_log_performance(self):
        """Test performance logging interval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(
                log_dir=tmpdir,
                performance_interval_minutes=60.0,
                console_output=False,
            )
            monitor = Monitor(config)

            # Should not log immediately (just initialized)
            assert not monitor.should_log_performance()

    def test_helper_functions(self):
        """Test helper logging functions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(log_dir=tmpdir, console_output=False)
            monitor = Monitor(config)

            monitor.info("Test info message")
            monitor.warning("Test warning")
            monitor.error("Test error")
            monitor.debug("Test debug")

            # Check that monitor.log exists
            monitor_log = Path(tmpdir) / "monitor.log"
            assert monitor_log.exists()


class TestLogHelpers:
    """Test log creation helper functions."""

    def test_create_trade_log(self):
        """Test create_trade_log helper."""
        log = create_trade_log(
            market_id="test",
            side="buy",
            order_type="limit",
            size=50.0,
            price=0.60,
            commission=0.5,
            slippage_bps=0.0,
            execution_mode="paper",
            success=True,
            metadata={"note": "test"},
        )

        assert isinstance(log, TradeLog)
        assert log.market_id == "test"
        assert log.metadata == {"note": "test"}

    def test_create_decision_log(self):
        """Test create_decision_log helper."""
        log = create_decision_log(
            market_id="test",
            decision="trade",
            reason="Strong edge",
            edge=0.10,
            market_price=0.50,
            fair_price=0.60,
            proposed_size=100.0,
            proposed_side="buy",
        )

        assert isinstance(log, DecisionLog)
        assert log.decision == "trade"
        assert log.edge == 0.10
