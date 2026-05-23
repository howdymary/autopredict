"""Default finance model.

AutoPredict no longer bundles offline finance examples as product data. The
default model is therefore a neutral market-implied fallback; users can wire a
verified dataset/model explicitly before enabling forecast-owned trading.
"""

from __future__ import annotations

from functools import lru_cache

from autopredict.domains.modeling import (
    MarketImpliedNoEdgeModel,
    QuestionConditionedDataset,
    QuestionConditionedExample,
)


@lru_cache(maxsize=1)
def finance_dataset() -> QuestionConditionedDataset:
    """Return the configured finance dataset metadata.

    The default package contains no bundled supervised examples.
    """

    return QuestionConditionedDataset(
        name="no_verified_finance_dataset",
        version="none",
        domain="finance",
        examples_by_split={},
    )


def finance_training_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return offline training examples for finance."""

    return finance_dataset().split_examples("train")


def finance_calibration_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return held-out calibration examples for finance."""

    return finance_dataset().split_examples("calibration")


def finance_evaluation_examples() -> tuple[QuestionConditionedExample, ...]:
    """Return held-out evaluation examples for finance."""

    return finance_dataset().split_examples("evaluation")


@lru_cache(maxsize=1)
def build_default_finance_model() -> MarketImpliedNoEdgeModel:
    """Return the production-safe neutral finance model."""

    return MarketImpliedNoEdgeModel("finance_market_implied_no_edge", "finance")
