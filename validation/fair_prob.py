"""Validation helpers for fair probability estimates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationWarning:
    """Warning about potentially problematic fair_prob estimate."""

    severity: str
    message: str
    field: str
    value: float
    suggestion: str


class FairProbValidator:
    """Validate fair_prob estimates before they enter the system."""

    CATEGORY_QUALITY = {
        "geopolitics": {
            "min_confidence": 0.8,
            "max_edge": 0.15,
            "historical_brier": 0.116,
            "quality": "excellent",
        },
        "science": {
            "min_confidence": 0.8,
            "max_edge": 0.15,
            "historical_brier": 0.137,
            "quality": "excellent",
        },
        "politics": {
            "min_confidence": 0.7,
            "max_edge": 0.15,
            "historical_brier": 0.230,
            "quality": "good",
        },
        "crypto": {
            "min_confidence": 0.5,
            "max_edge": 0.20,
            "historical_brier": 0.292,
            "quality": "poor",
        },
        "macro": {
            "min_confidence": 0.5,
            "max_edge": 0.20,
            "historical_brier": 0.292,
            "quality": "poor",
        },
        "sports": {
            "min_confidence": 0.3,
            "max_edge": 0.25,
            "historical_brier": 0.462,
            "quality": "very_poor",
        },
    }

    def validate(
        self,
        fair_prob: float,
        market_prob: float,
        category: str = "unknown",
        metadata: dict[str, object] | None = None,
    ) -> list[ValidationWarning]:
        """Run validation checks and return warnings."""

        warnings: list[ValidationWarning] = []

        if fair_prob < 0.10 or fair_prob > 0.90:
            warnings.append(
                ValidationWarning(
                    severity="warning",
                    message=f"Extreme probability: {fair_prob:.2f}",
                    field="fair_prob",
                    value=fair_prob,
                    suggestion="Extreme probabilities should be rare. Consider using 0.10-0.90 range.",
                )
            )

        edge = abs(fair_prob - market_prob)
        max_edge = self.CATEGORY_QUALITY.get(category, {}).get("max_edge", 0.20)
        if edge > max_edge:
            category_info = self.CATEGORY_QUALITY.get(category, {})
            quality = category_info.get("quality", "unknown")
            warnings.append(
                ValidationWarning(
                    severity="warning",
                    message=f"Large edge ({edge:.2f}) in {category} category (quality: {quality})",
                    field="edge",
                    value=edge,
                    suggestion=(
                        f"Category '{category}' has {quality} historical calibration. "
                        "Consider reducing edge or improving estimation."
                    ),
                )
            )

        category_info = self.CATEGORY_QUALITY.get(category, {})
        quality = category_info.get("quality", "unknown")
        if quality in ["poor", "very_poor"]:
            min_confidence = category_info.get("min_confidence", 0.5)
            historical_brier = category_info.get("historical_brier", 0.25)
            warnings.append(
                ValidationWarning(
                    severity="info",
                    message=f"Category '{category}' has {quality} quality (historical Brier: {historical_brier:.3f})",
                    field="category",
                    value=min_confidence,
                    suggestion=f"Consider extra validation, reducing position size, or avoiding {category} markets.",
                )
            )

        mid = 0.5
        if (fair_prob - mid) * (market_prob - mid) < 0:
            warnings.append(
                ValidationWarning(
                    severity="info",
                    message=f"Fair prob ({fair_prob:.2f}) crosses 0.5 relative to market ({market_prob:.2f})",
                    field="fair_prob",
                    value=fair_prob,
                    suggestion="Reversing market direction is high conviction. Verify your reasoning.",
                )
            )

        if market_prob < 0.25 and fair_prob > market_prob + 0.15:
            warnings.append(
                ValidationWarning(
                    severity="info",
                    message=f"Fair prob ({fair_prob:.2f}) significantly higher than low market price ({market_prob:.2f})",
                    field="fair_prob",
                    value=fair_prob,
                    suggestion="Large upward adjustment from low market price. Ensure edge is well-justified.",
                )
            )

        if market_prob > 0.75 and fair_prob < market_prob - 0.15:
            warnings.append(
                ValidationWarning(
                    severity="info",
                    message=f"Fair prob ({fair_prob:.2f}) significantly lower than high market price ({market_prob:.2f})",
                    field="fair_prob",
                    value=fair_prob,
                    suggestion="Large downward adjustment from high market price. Ensure edge is well-justified.",
                )
            )

        return warnings

    def validate_and_log(
        self,
        fair_prob: float,
        market_prob: float,
        market_id: str,
        category: str = "unknown",
        metadata: dict[str, object] | None = None,
    ) -> tuple[bool, list[ValidationWarning]]:
        """Validate and return whether the estimate should be rejected."""

        warnings = self.validate(fair_prob, market_prob, category, metadata)
        should_reject = any(warning.severity == "error" for warning in warnings)

        if warnings:
            print(f"\n[VALIDATION] Market: {market_id}")
            for warning in warnings:
                icon = "❌" if warning.severity == "error" else "⚠️" if warning.severity == "warning" else "ℹ️"
                print(f"  {icon} [{warning.severity.upper()}] {warning.message}")
                print(f"     → {warning.suggestion}")

        return should_reject, warnings
