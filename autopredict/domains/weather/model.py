"""Default weather model.

AutoPredict no longer bundles offline weather examples as product data. The
default model is a neutral market-implied fallback until a verified model is
configured explicitly.
"""

from __future__ import annotations

from functools import lru_cache

from autopredict.domains.modeling import (
    MarketImpliedNoEdgeModel,
    QuestionConditionedDataset,
    QuestionConditionedExample,
)


@lru_cache(maxsize=1)
def weather_dataset() -> QuestionConditionedDataset:
    """Return the configured weather dataset metadata."""

    return QuestionConditionedDataset(
        name="no_verified_weather_dataset",
        version="none",
        domain="weather",
        examples_by_split={},
    )


def weather_training_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return offline training examples for weather."""

    return weather_dataset().split_examples("train")


def weather_calibration_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return held-out calibration examples for weather."""

    return weather_dataset().split_examples("calibration")


def weather_evaluation_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return held-out evaluation examples for weather."""

    return weather_dataset().split_examples("evaluation")


@lru_cache(maxsize=1)
def build_default_weather_model() -> MarketImpliedNoEdgeModel:
    """Return the production-safe neutral weather model."""

    return MarketImpliedNoEdgeModel("weather_market_implied_no_edge", "weather")
