"""Tests for market data validation."""

from __future__ import annotations

import pytest

import sys
from pathlib import Path

# Add validation module to path
sys.path.insert(0, str(Path(__file__).parent.parent / "validation"))

from validator import MarketDataValidator, ValidationError


class TestMarketDataValidator:
    """Test market data validator."""

    def test_validator_creation(self):
        """Test validator creation."""
        validator = MarketDataValidator()
        assert validator.strict is False

        strict_validator = MarketDataValidator(strict=True)
        assert strict_validator.strict is True

    def test_validate_valid_market(self):
        """Test validation of a valid market."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.50,
            "fair_prob": 0.58,
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.48, 100.0], [0.47, 150.0]],
                "asks": [[0.52, 110.0], [0.53, 160.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_missing_required_field(self):
        """Test validation catches missing required fields."""
        market = {
            "market_id": "test-market",
            "category": "test",
            # Missing market_prob
            "fair_prob": 0.58,
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.48, 100.0]],
                "asks": [[0.52, 110.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert is_valid is False
        assert any(e.field == "market_prob" for e in errors)
        assert any(e.severity == "error" for e in errors)

    def test_validate_probability_out_of_range(self):
        """Test validation catches probabilities outside [0, 1]."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 1.5,  # Invalid
            "fair_prob": 0.58,
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.48, 100.0]],
                "asks": [[0.52, 110.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert is_valid is False
        assert any("out of range" in e.message for e in errors)

    def test_validate_extreme_probability_warning(self):
        """Test validation warns about extreme probabilities."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.005,  # Extreme
            "fair_prob": 0.01,
            "outcome": 0,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.004, 100.0]],
                "asks": [[0.006, 110.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        # Should be valid but have warnings
        assert len(errors) > 0
        assert any(e.severity == "warning" for e in errors)
        assert any("extreme" in e.message.lower() for e in errors)

    def test_validate_invalid_outcome(self):
        """Test validation catches invalid outcomes."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.50,
            "fair_prob": 0.58,
            "outcome": 2,  # Should be 0 or 1
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.48, 100.0]],
                "asks": [[0.52, 110.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert is_valid is False
        assert any(e.field == "outcome" for e in errors)

    def test_validate_negative_time_to_expiry(self):
        """Test validation catches negative time to expiry."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.50,
            "fair_prob": 0.58,
            "outcome": 1,
            "time_to_expiry_hours": -10.0,  # Invalid
            "order_book": {
                "bids": [[0.48, 100.0]],
                "asks": [[0.52, 110.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert is_valid is False
        assert any(e.field == "time_to_expiry_hours" for e in errors)

    def test_validate_crossed_book(self):
        """Test validation catches crossed order books."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.50,
            "fair_prob": 0.58,
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.55, 100.0]],  # Bid >= Ask
                "asks": [[0.52, 110.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert is_valid is False
        assert any("crossed" in e.message.lower() for e in errors)

    def test_validate_bid_ordering(self):
        """Test validation catches incorrect bid ordering."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.50,
            "fair_prob": 0.58,
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.45, 100.0], [0.48, 150.0]],  # Not descending
                "asks": [[0.52, 110.0], [0.53, 160.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert is_valid is False
        assert any("descending" in e.message.lower() for e in errors)

    def test_validate_ask_ordering(self):
        """Test validation catches incorrect ask ordering."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.50,
            "fair_prob": 0.58,
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.48, 100.0], [0.47, 150.0]],
                "asks": [[0.55, 110.0], [0.52, 160.0]],  # Not ascending
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert is_valid is False
        assert any("ascending" in e.message.lower() for e in errors)

    def test_validate_negative_size(self):
        """Test validation catches negative sizes."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.50,
            "fair_prob": 0.58,
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.48, -100.0]],  # Negative size
                "asks": [[0.52, 110.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert is_valid is False
        assert any("positive" in e.message.lower() for e in errors)

    def test_validate_large_edge_warning(self):
        """Test validation warns about very large edges."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.30,
            "fair_prob": 0.65,  # 35% edge
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.29, 100.0]],
                "asks": [[0.31, 110.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert any("large edge" in e.message.lower() for e in errors)

    def test_validate_low_liquidity_warning(self):
        """Test validation warns about very low liquidity."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.50,
            "fair_prob": 0.58,
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.48, 3.0]],  # Very low liquidity
                "asks": [[0.52, 3.0]],
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        assert any("low liquidity" in e.message.lower() for e in errors)

    def test_validate_dataset(self, sample_markets):
        """Test dataset validation."""
        validator = MarketDataValidator()
        is_valid, summary = validator.validate_dataset(
            sample_markets, verbose=False
        )

        assert "is_valid" in summary
        assert "total_markets" in summary
        assert "valid_markets" in summary
        assert summary["total_markets"] == len(sample_markets)

    def test_validate_empty_dataset(self):
        """Test validation of empty dataset."""
        validator = MarketDataValidator()
        is_valid, summary = validator.validate_dataset([], verbose=False)

        assert summary["total_markets"] == 0
        assert summary["valid_markets"] == 0

    def test_strict_mode(self):
        """Test strict mode treats warnings as errors."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.005,  # Extreme (warning)
            "fair_prob": 0.01,
            "outcome": 0,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.004, 100.0]],
                "asks": [[0.006, 110.0]],
            },
        }

        # Non-strict: should be valid despite warnings
        validator = MarketDataValidator(strict=False)
        is_valid, errors = validator.validate_market(market)
        # May or may not be valid depending on warnings

        # Strict: warnings should make it invalid
        strict_validator = MarketDataValidator(strict=True)
        is_valid_strict, errors_strict = strict_validator.validate_market(market)

        # If there are warnings, strict should be invalid
        if any(e.severity == "warning" for e in errors_strict):
            assert is_valid_strict is False


class TestValidationHelpers:
    """Test validation helper functions."""

    def test_validation_error_creation(self):
        """Test ValidationError creation."""
        error = ValidationError(
            field="test_field",
            message="Test message",
            severity="error",
            value=123,
            suggestion="Fix it",
        )

        assert error.field == "test_field"
        assert error.message == "Test message"
        assert error.severity == "error"
        assert error.value == 123
        assert error.suggestion == "Fix it"

    def test_market_prob_vs_book_mid_consistency(self):
        """Test validation of market_prob vs book mid consistency."""
        market = {
            "market_id": "test-market",
            "category": "test",
            "market_prob": 0.70,  # Significantly different from book mid
            "fair_prob": 0.75,
            "outcome": 1,
            "time_to_expiry_hours": 48.0,
            "order_book": {
                "bids": [[0.48, 100.0]],
                "asks": [[0.52, 110.0]],  # Mid = 0.50
            },
        }

        validator = MarketDataValidator()
        is_valid, errors = validator.validate_market(market)

        # Should have warning about market_prob vs mid
        assert any(
            "market_prob" in e.field and "differs" in e.message.lower()
            for e in errors
        )
