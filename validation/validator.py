"""Comprehensive market data validation for AutoPredict."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationError:
    """Structured validation error with severity and context."""

    field: str
    message: str
    severity: str  # "error", "warning", "info"
    value: Any | None = None
    suggestion: str | None = None


class MarketDataValidator:
    """Validate market data structure, values, and consistency."""

    def __init__(self, strict: bool = False) -> None:
        """
        Initialize validator.

        Args:
            strict: If True, warnings are treated as errors
        """
        self.strict = strict

    def validate_market(self, market: dict[str, Any]) -> tuple[bool, list[ValidationError]]:
        """
        Validate a single market dictionary.

        Returns:
            (is_valid, errors) - is_valid is False if any error-level issues found
        """
        errors: list[ValidationError] = []

        # Schema validation
        errors.extend(self._validate_schema(market))

        # Value range validation
        errors.extend(self._validate_probabilities(market))
        errors.extend(self._validate_time_to_expiry(market))
        errors.extend(self._validate_outcome(market))

        # Order book validation
        if "order_book" in market:
            errors.extend(self._validate_order_book(market["order_book"]))

        # Cross-field consistency
        errors.extend(self._validate_consistency(market))

        # Check if valid
        has_errors = any(e.severity == "error" for e in errors)
        has_warnings = any(e.severity == "warning" for e in errors)

        is_valid = not has_errors and (not self.strict or not has_warnings)

        return is_valid, errors

    def validate_dataset(
        self,
        markets: list[dict[str, Any]],
        verbose: bool = True
    ) -> tuple[bool, dict[str, Any]]:
        """
        Validate entire dataset.

        Returns:
            (is_valid, summary) where summary contains error counts and details
        """
        all_errors: list[tuple[int, list[ValidationError]]] = []
        valid_count = 0
        error_count = 0
        warning_count = 0

        for i, market in enumerate(markets):
            is_valid, errors = self.validate_market(market)

            if errors:
                all_errors.append((i, errors))

            if is_valid:
                valid_count += 1

            # Count error types
            for error in errors:
                if error.severity == "error":
                    error_count += 1
                elif error.severity == "warning":
                    warning_count += 1

        dataset_valid = error_count == 0 and (not self.strict or warning_count == 0)

        summary = {
            "is_valid": dataset_valid,
            "total_markets": len(markets),
            "valid_markets": valid_count,
            "invalid_markets": len(markets) - valid_count,
            "total_errors": error_count,
            "total_warnings": warning_count,
            "errors_by_market": all_errors,
        }

        if verbose:
            self._print_validation_summary(summary)

        return dataset_valid, summary

    def _validate_schema(self, market: dict[str, Any]) -> list[ValidationError]:
        """Validate required fields are present."""
        errors = []

        required_fields = [
            "market_id",
            "category",
            "market_prob",
            "fair_prob",
            "outcome",
            "time_to_expiry_hours",
            "order_book",
        ]

        for field in required_fields:
            if field not in market:
                errors.append(ValidationError(
                    field=field,
                    message=f"Missing required field: {field}",
                    severity="error",
                    suggestion=f"Add '{field}' to market data"
                ))

        # Validate order book structure
        if "order_book" in market:
            order_book = market["order_book"]
            if not isinstance(order_book, dict):
                errors.append(ValidationError(
                    field="order_book",
                    message="order_book must be a dictionary",
                    severity="error",
                    value=type(order_book).__name__
                ))
            else:
                for side in ["bids", "asks"]:
                    if side not in order_book:
                        errors.append(ValidationError(
                            field=f"order_book.{side}",
                            message=f"order_book missing '{side}'",
                            severity="error",
                            suggestion=f"Add '{side}': [[price, size], ...] to order_book"
                        ))

        return errors

    def _validate_probabilities(self, market: dict[str, Any]) -> list[ValidationError]:
        """Validate probability values are in [0, 1]."""
        errors = []

        prob_fields = ["market_prob", "fair_prob"]
        if "next_mid_price" in market:
            prob_fields.append("next_mid_price")

        for field in prob_fields:
            if field not in market:
                continue

            value = market[field]

            # Type check
            if not isinstance(value, (int, float)):
                errors.append(ValidationError(
                    field=field,
                    message=f"{field} must be numeric",
                    severity="error",
                    value=value,
                    suggestion=f"Convert {field} to float"
                ))
                continue

            # Range check
            if value < 0.0 or value > 1.0:
                errors.append(ValidationError(
                    field=field,
                    message=f"{field} out of range [0, 1]: {value}",
                    severity="error",
                    value=value,
                    suggestion="Probabilities must be between 0.0 and 1.0"
                ))

            # Extreme value warning
            if field in ["market_prob", "fair_prob"]:
                if value < 0.01 or value > 0.99:
                    errors.append(ValidationError(
                        field=field,
                        message=f"Extreme probability: {value}",
                        severity="warning",
                        value=value,
                        suggestion="Very extreme probabilities (< 0.01 or > 0.99) are rare in practice"
                    ))

        return errors

    def _validate_time_to_expiry(self, market: dict[str, Any]) -> list[ValidationError]:
        """Validate time to expiry is positive."""
        errors = []

        if "time_to_expiry_hours" not in market:
            return errors

        value = market["time_to_expiry_hours"]

        if not isinstance(value, (int, float)):
            errors.append(ValidationError(
                field="time_to_expiry_hours",
                message="time_to_expiry_hours must be numeric",
                severity="error",
                value=value
            ))
            return errors

        if value <= 0:
            errors.append(ValidationError(
                field="time_to_expiry_hours",
                message=f"time_to_expiry_hours must be positive: {value}",
                severity="error",
                value=value
            ))

        if value > 8760:  # > 1 year
            errors.append(ValidationError(
                field="time_to_expiry_hours",
                message=f"time_to_expiry_hours very large: {value} hours ({value/24:.1f} days)",
                severity="warning",
                value=value,
                suggestion="Markets expiring > 1 year out may have prediction quality issues"
            ))

        return errors

    def _validate_outcome(self, market: dict[str, Any]) -> list[ValidationError]:
        """Validate outcome is binary (0 or 1)."""
        errors = []

        if "outcome" not in market:
            return errors

        value = market["outcome"]

        if value not in [0, 1]:
            errors.append(ValidationError(
                field="outcome",
                message=f"outcome must be 0 or 1, got: {value}",
                severity="error",
                value=value
            ))

        return errors

    def _validate_order_book(self, order_book: dict[str, Any]) -> list[ValidationError]:
        """Validate order book structure and consistency."""
        errors = []

        if not isinstance(order_book, dict):
            return errors  # Already caught in schema validation

        # Validate bids
        if "bids" in order_book:
            errors.extend(self._validate_book_side(order_book["bids"], "bids"))

        # Validate asks
        if "asks" in order_book:
            errors.extend(self._validate_book_side(order_book["asks"], "asks"))

        # Check for crossed book
        if "bids" in order_book and "asks" in order_book:
            bids = order_book["bids"]
            asks = order_book["asks"]

            if bids and asks:
                # Validate bids are lists
                if isinstance(bids, list) and len(bids) > 0 and isinstance(bids[0], (list, tuple)):
                    best_bid = bids[0][0]
                else:
                    return errors

                # Validate asks are lists
                if isinstance(asks, list) and len(asks) > 0 and isinstance(asks[0], (list, tuple)):
                    best_ask = asks[0][0]
                else:
                    return errors

                if best_bid >= best_ask:
                    errors.append(ValidationError(
                        field="order_book",
                        message=f"Crossed book: best_bid ({best_bid}) >= best_ask ({best_ask})",
                        severity="error",
                        value={"best_bid": best_bid, "best_ask": best_ask},
                        suggestion="Ensure best_bid < best_ask"
                    ))

        return errors

    def _validate_book_side(
        self,
        levels: list[Any],
        side: str
    ) -> list[ValidationError]:
        """Validate one side of the order book."""
        errors = []

        if not isinstance(levels, list):
            errors.append(ValidationError(
                field=f"order_book.{side}",
                message=f"{side} must be a list",
                severity="error",
                value=type(levels).__name__
            ))
            return errors

        if len(levels) == 0:
            errors.append(ValidationError(
                field=f"order_book.{side}",
                message=f"{side} is empty",
                severity="warning",
                suggestion=f"Add at least one level to {side}"
            ))
            return errors

        prev_price = None
        for i, level in enumerate(levels):
            # Validate level structure
            if not isinstance(level, (list, tuple)) or len(level) != 2:
                errors.append(ValidationError(
                    field=f"order_book.{side}[{i}]",
                    message=f"Level must be [price, size], got: {level}",
                    severity="error",
                    value=level
                ))
                continue

            price, size = level

            # Validate price
            if not isinstance(price, (int, float)):
                errors.append(ValidationError(
                    field=f"order_book.{side}[{i}].price",
                    message=f"Price must be numeric, got: {type(price).__name__}",
                    severity="error",
                    value=price
                ))
                continue

            if price <= 0 or price >= 1:
                errors.append(ValidationError(
                    field=f"order_book.{side}[{i}].price",
                    message=f"Price out of range (0, 1): {price}",
                    severity="error",
                    value=price
                ))

            # Validate size
            if not isinstance(size, (int, float)):
                errors.append(ValidationError(
                    field=f"order_book.{side}[{i}].size",
                    message=f"Size must be numeric, got: {type(size).__name__}",
                    severity="error",
                    value=size
                ))
                continue

            if size <= 0:
                errors.append(ValidationError(
                    field=f"order_book.{side}[{i}].size",
                    message=f"Size must be positive: {size}",
                    severity="error",
                    value=size
                ))

            # Validate price ordering
            if prev_price is not None:
                if side == "bids":
                    # Bids should be descending
                    if price >= prev_price:
                        errors.append(ValidationError(
                            field=f"order_book.{side}[{i}]",
                            message=f"Bids not in descending order: {price} >= {prev_price}",
                            severity="error",
                            value={"current": price, "previous": prev_price},
                            suggestion="Bids must be sorted in descending price order"
                        ))
                else:
                    # Asks should be ascending
                    if price <= prev_price:
                        errors.append(ValidationError(
                            field=f"order_book.{side}[{i}]",
                            message=f"Asks not in ascending order: {price} <= {prev_price}",
                            severity="error",
                            value={"current": price, "previous": prev_price},
                            suggestion="Asks must be sorted in ascending price order"
                        ))

            prev_price = price

        return errors

    def _validate_consistency(self, market: dict[str, Any]) -> list[ValidationError]:
        """Validate cross-field consistency."""
        errors = []

        # Check market_prob is consistent with order book mid
        if "market_prob" in market and "order_book" in market:
            order_book = market["order_book"]

            if "bids" in order_book and "asks" in order_book:
                bids = order_book["bids"]
                asks = order_book["asks"]

                if (bids and asks and
                    isinstance(bids, list) and len(bids) > 0 and
                    isinstance(asks, list) and len(asks) > 0 and
                    isinstance(bids[0], (list, tuple)) and
                    isinstance(asks[0], (list, tuple))):

                    best_bid = bids[0][0]
                    best_ask = asks[0][0]
                    book_mid = (best_bid + best_ask) / 2

                    market_prob = market["market_prob"]
                    diff = abs(book_mid - market_prob)

                    if diff > 0.05:  # > 5% difference
                        errors.append(ValidationError(
                            field="market_prob",
                            message=f"market_prob ({market_prob:.3f}) differs significantly from book mid ({book_mid:.3f})",
                            severity="warning",
                            value={"market_prob": market_prob, "book_mid": book_mid, "diff": diff},
                            suggestion="market_prob should be close to (best_bid + best_ask) / 2"
                        ))

        # Validate edge is reasonable
        if "market_prob" in market and "fair_prob" in market:
            market_prob = market["market_prob"]
            fair_prob = market["fair_prob"]
            edge = abs(fair_prob - market_prob)

            if edge > 0.30:
                errors.append(ValidationError(
                    field="fair_prob",
                    message=f"Very large edge: {edge:.3f}",
                    severity="warning",
                    value=edge,
                    suggestion="Edges > 30% are extremely rare - verify fair_prob estimate"
                ))

        # Check liquidity is reasonable
        if "order_book" in market:
            order_book = market["order_book"]
            total_depth = 0.0

            if "bids" in order_book and isinstance(order_book["bids"], list):
                for level in order_book["bids"]:
                    if isinstance(level, (list, tuple)) and len(level) == 2:
                        total_depth += level[1]

            if "asks" in order_book and isinstance(order_book["asks"], list):
                for level in order_book["asks"]:
                    if isinstance(level, (list, tuple)) and len(level) == 2:
                        total_depth += level[1]

            if total_depth < 10:
                errors.append(ValidationError(
                    field="order_book",
                    message=f"Very low liquidity: {total_depth:.1f}",
                    severity="warning",
                    value=total_depth,
                    suggestion="Total depth < 10 may cause execution issues"
                ))

        return errors

    def _print_validation_summary(self, summary: dict[str, Any]) -> None:
        """Print formatted validation summary."""
        print("\n" + "="*60)
        print("VALIDATION SUMMARY")
        print("="*60)

        status = "PASSED" if summary["is_valid"] else "FAILED"
        status_symbol = "✓" if summary["is_valid"] else "✗"

        print(f"\nStatus: {status_symbol} {status}")
        print(f"\nTotal Markets:   {summary['total_markets']}")
        print(f"Valid Markets:   {summary['valid_markets']}")
        print(f"Invalid Markets: {summary['invalid_markets']}")
        print(f"\nTotal Errors:    {summary['total_errors']}")
        print(f"Total Warnings:  {summary['total_warnings']}")

        # Print errors by market (first 5)
        if summary["errors_by_market"]:
            print(f"\n{'='*60}")
            print(f"ERROR DETAILS (showing first 5 markets with issues)")
            print("="*60)

            for idx, (market_idx, errors) in enumerate(summary["errors_by_market"][:5]):
                print(f"\nMarket #{market_idx}:")
                for error in errors:
                    symbol = "✗" if error.severity == "error" else "⚠" if error.severity == "warning" else "ℹ"
                    print(f"  {symbol} [{error.severity.upper()}] {error.field}: {error.message}")
                    if error.suggestion:
                        print(f"      → {error.suggestion}")

            if len(summary["errors_by_market"]) > 5:
                remaining = len(summary["errors_by_market"]) - 5
                print(f"\n... and {remaining} more markets with issues")

        print("\n" + "="*60)


def validate_file(file_path: str, strict: bool = False, verbose: bool = True) -> bool:
    """
    Validate a JSON dataset file.

    Args:
        file_path: Path to JSON file containing market data
        strict: If True, warnings are treated as errors
        verbose: If True, print detailed summary

    Returns:
        True if validation passes
    """
    import json
    from pathlib import Path

    path = Path(file_path)

    if not path.exists():
        print(f"Error: File not found: {file_path}")
        return False

    try:
        with open(path) as f:
            markets = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}")
        return False

    if not isinstance(markets, list):
        print(f"Error: Expected list of markets, got {type(markets).__name__}")
        return False

    validator = MarketDataValidator(strict=strict)
    is_valid, summary = validator.validate_dataset(markets, verbose=verbose)

    return is_valid


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python validator.py <path_to_dataset.json> [--strict]")
        sys.exit(1)

    file_path = sys.argv[1]
    strict = "--strict" in sys.argv

    is_valid = validate_file(file_path, strict=strict)

    sys.exit(0 if is_valid else 1)
