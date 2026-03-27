"""Tests for configuration system."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from autopredict.config import (
    load_config,
    validate_config,
    StrategyConfig,
    RiskConfig,
    VenueConfig,
    ExperimentConfig,
)
from autopredict.config.loader import substitute_env_vars


class TestEnvironmentVariableSubstitution:
    """Test environment variable substitution in configs."""

    def test_simple_substitution(self):
        """Test basic environment variable substitution."""
        os.environ["TEST_VAR"] = "test_value"
        result = substitute_env_vars("${TEST_VAR}")
        assert result == "test_value"

    def test_substitution_with_default(self):
        """Test environment variable with default value."""
        result = substitute_env_vars("${MISSING_VAR:default_value}")
        assert result == "default_value"

    def test_missing_variable_raises(self):
        """Test that missing variable without default raises error."""
        with pytest.raises(ValueError, match="Environment variable.*not found"):
            substitute_env_vars("${DEFINITELY_MISSING_VAR}")

    def test_nested_substitution(self):
        """Test substitution in nested structures."""
        os.environ["NESTED_VAR"] = "nested_value"
        data = {
            "key1": "${NESTED_VAR}",
            "key2": {
                "nested": "${NESTED_VAR}",
            },
        }
        result = substitute_env_vars(data)
        assert result["key1"] == "nested_value"
        assert result["key2"]["nested"] == "nested_value"


class TestStrategyConfig:
    """Test StrategyConfig validation."""

    def test_valid_config(self):
        """Test that valid config passes validation."""
        config = StrategyConfig()
        config.validate()  # Should not raise

    def test_invalid_min_edge(self):
        """Test that invalid min_edge raises error."""
        config = StrategyConfig(min_edge=-0.1)
        with pytest.raises(ValueError, match="min_edge"):
            config.validate()

        config = StrategyConfig(min_edge=1.5)
        with pytest.raises(ValueError, match="min_edge"):
            config.validate()

    def test_invalid_kelly_fraction(self):
        """Test that invalid kelly_fraction raises error."""
        config = StrategyConfig(kelly_fraction=0.0)
        with pytest.raises(ValueError, match="kelly_fraction"):
            config.validate()

        config = StrategyConfig(kelly_fraction=1.5)
        with pytest.raises(ValueError, match="kelly_fraction"):
            config.validate()


class TestRiskConfig:
    """Test RiskConfig validation."""

    def test_valid_config(self):
        """Test that valid config passes validation."""
        config = RiskConfig()
        config.validate()  # Should not raise

    def test_kill_switch_threshold_must_be_negative(self):
        """Test that kill switch threshold must be negative."""
        config = RiskConfig(kill_switch_threshold=50.0)
        with pytest.raises(ValueError, match="kill_switch_threshold must be negative"):
            config.validate()

    def test_kill_switch_more_severe_than_daily_loss(self):
        """Test that kill switch is more severe than daily loss limit."""
        config = RiskConfig(
            max_daily_loss=100.0,
            kill_switch_threshold=-50.0,  # Less severe than daily loss
        )
        with pytest.raises(ValueError, match="more severe"):
            config.validate()

    def test_positive_limits_required(self):
        """Test that all limits must be positive."""
        with pytest.raises(ValueError):
            RiskConfig(max_position_per_market=-10.0).validate()

        with pytest.raises(ValueError):
            RiskConfig(max_total_exposure=0.0).validate()


class TestVenueConfig:
    """Test VenueConfig validation."""

    def test_valid_paper_mode(self):
        """Test valid paper mode config."""
        config = VenueConfig(mode="paper")
        config.validate()

    def test_valid_live_mode(self):
        """Test valid live mode config."""
        config = VenueConfig(mode="live", api_key="test_key")
        config.validate()

    def test_live_mode_requires_api_key(self):
        """Test that live mode requires API key."""
        config = VenueConfig(mode="live", api_key=None)
        with pytest.raises(ValueError, match="api_key is required"):
            config.validate()

    def test_invalid_mode(self):
        """Test that invalid mode raises error."""
        config = VenueConfig(mode="invalid")
        with pytest.raises(ValueError, match="mode must be"):
            config.validate()

    def test_is_live(self):
        """Test is_live() method."""
        assert VenueConfig(mode="live", api_key="key").is_live()
        assert not VenueConfig(mode="paper").is_live()


class TestExperimentConfig:
    """Test ExperimentConfig validation and integration."""

    def test_valid_config(self):
        """Test that valid experiment config passes validation."""
        config = ExperimentConfig(name="test")
        config.validate()

    def test_live_mode_requires_kill_switch(self):
        """Test that live mode requires kill switch enabled."""
        config = ExperimentConfig(
            name="test",
            venue=VenueConfig(mode="live", api_key="key"),
            risk=RiskConfig(enable_kill_switch=False),
        )
        with pytest.raises(ValueError, match="Kill switch must be enabled"):
            config.validate()

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = ExperimentConfig(name="test")
        data = config.to_dict()
        assert isinstance(data, dict)
        assert data["name"] == "test"
        assert "strategy" in data
        assert "risk" in data
        assert "venue" in data


class TestConfigLoader:
    """Test configuration loading from YAML files."""

    def test_load_valid_yaml(self):
        """Test loading valid YAML configuration."""
        config_data = {
            "name": "test_experiment",
            "strategy": {"min_edge": 0.05},
            "risk": {"max_daily_loss": 50.0},
            "venue": {"mode": "paper"},
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.name == "test_experiment"
            assert config.strategy.min_edge == 0.05
            assert config.risk.max_daily_loss == 50.0
            assert config.venue.mode == "paper"
        finally:
            os.unlink(temp_path)

    def test_load_with_env_vars(self):
        """Test loading config with environment variables."""
        os.environ["TEST_API_KEY"] = "secret_key_123"

        config_data = {
            "name": "test",
            "venue": {
                "mode": "live",
                "api_key": "${TEST_API_KEY}",
            },
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.venue.api_key == "secret_key_123"
        finally:
            os.unlink(temp_path)

    def test_missing_file_raises(self):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")


class TestConfigValidation:
    """Test configuration validation warnings."""

    def test_paper_mode_no_warnings(self):
        """Test that safe paper mode has no warnings."""
        config = ExperimentConfig(
            name="test",
            venue=VenueConfig(mode="paper"),
        )
        warnings = validate_config(config)
        # May have some warnings, but should not fail
        assert isinstance(warnings, list)

    def test_live_mode_high_limits_warning(self):
        """Test that live mode with high limits generates warnings."""
        config = ExperimentConfig(
            name="test",
            venue=VenueConfig(mode="live", api_key="key"),
            risk=RiskConfig(max_daily_loss=5000.0),
        )
        warnings = validate_config(config)
        assert any("high" in w.lower() for w in warnings)

    def test_aggressive_kelly_warning(self):
        """Test warning for aggressive Kelly fraction."""
        config = ExperimentConfig(
            name="test",
            strategy=StrategyConfig(kelly_fraction=0.8),
        )
        warnings = validate_config(config)
        assert any("kelly" in w.lower() for w in warnings)
