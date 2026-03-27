"""Default question-conditioned finance model backed by offline datasets."""

from __future__ import annotations

from functools import lru_cache

from autopredict.domains.modeling import (
    QuestionConditionedDataset,
    QuestionConditionedExample,
    QuestionConditionedLinearModel,
    load_question_conditioned_dataset,
)

FINANCE_DATASET_FILE = "finance_domain_examples.json"


@lru_cache(maxsize=1)
def finance_dataset() -> QuestionConditionedDataset:
    """Return the cached offline finance dataset."""

    return load_question_conditioned_dataset(FINANCE_DATASET_FILE)


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
def build_default_finance_model() -> QuestionConditionedLinearModel:
    """Return the cached calibrated finance question-conditioned model."""

    dataset = finance_dataset()
    return QuestionConditionedLinearModel.fit_with_calibration(
        "finance_question_conditioned",
        finance_training_examples(),
        finance_calibration_examples(),
        evaluation_examples=finance_evaluation_examples(),
        dataset=dataset,
    )
