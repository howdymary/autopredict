"""Default politics model.

AutoPredict no longer bundles offline politics examples as product data. The
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
def politics_dataset() -> QuestionConditionedDataset:
    """Return the configured politics dataset metadata."""

    return QuestionConditionedDataset(
        name="no_verified_politics_dataset",
        version="none",
        domain="politics",
        examples_by_split={},
    )


def politics_training_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return offline training examples for politics."""

    return politics_dataset().split_examples("train")


def politics_calibration_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return held-out calibration examples for politics."""

    return politics_dataset().split_examples("calibration")


def politics_evaluation_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return held-out evaluation examples for politics."""

    return politics_dataset().split_examples("evaluation")


@lru_cache(maxsize=1)
def build_default_politics_model() -> MarketImpliedNoEdgeModel:
    """Return the production-safe neutral politics model."""

    return MarketImpliedNoEdgeModel("politics_market_implied_no_edge", "politics")
