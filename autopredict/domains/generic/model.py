"""Generic market-implied model for categories without a specialist model."""

from __future__ import annotations

from functools import lru_cache

from autopredict.domains.modeling import (
    MarketImpliedNoEdgeModel,
    QuestionConditionedDataset,
    QuestionConditionedExample,
)


@lru_cache(maxsize=1)
def generic_dataset() -> QuestionConditionedDataset:
    """Return configured generic dataset metadata.

    The default package contains no bundled supervised examples.
    """

    return QuestionConditionedDataset(
        name="no_verified_generic_dataset",
        version="none",
        domain="generic",
        examples_by_split={},
    )


def generic_training_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return combined offline training examples for the generic fallback."""

    return generic_dataset().split_examples("train")


def generic_calibration_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return held-out calibration examples for the generic fallback."""

    return generic_dataset().split_examples("calibration")


def generic_evaluation_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return held-out evaluation examples for the generic fallback."""

    return generic_dataset().split_examples("evaluation")


@lru_cache(maxsize=1)
def build_default_generic_model() -> MarketImpliedNoEdgeModel:
    """Return the production-safe neutral generic model."""

    return MarketImpliedNoEdgeModel("generic_market_implied_no_edge", "generic")
