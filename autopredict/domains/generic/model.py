"""Generic question-conditioned model for categories without a specialist model."""

from __future__ import annotations

from functools import lru_cache

from autopredict.domains.finance import finance_dataset
from autopredict.domains.modeling import (
    QuestionConditionedDataset,
    QuestionConditionedExample,
    QuestionConditionedLinearModel,
)
from autopredict.domains.politics import politics_dataset
from autopredict.domains.weather import weather_dataset


@lru_cache(maxsize=1)
def generic_dataset() -> QuestionConditionedDataset:
    """Return a combined offline dataset spanning all bundled domains."""

    datasets = (finance_dataset(), politics_dataset(), weather_dataset())
    examples_by_split: dict[str, list[QuestionConditionedExample]] = {}
    for dataset in datasets:
        for split, examples in dataset.examples_by_split.items():
            bucket = examples_by_split.setdefault(split, [])
            bucket.extend(examples)
    return QuestionConditionedDataset(
        name="generic_domain_examples",
        version="1.0.0",
        domain="generic",
        examples_by_split={
            split: tuple(examples)
            for split, examples in examples_by_split.items()
        },
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
def build_default_generic_model() -> QuestionConditionedLinearModel:
    """Return the cached calibrated generic question-conditioned model."""

    dataset = generic_dataset()
    return QuestionConditionedLinearModel.fit_with_calibration(
        "generic_question_conditioned",
        generic_training_examples(),
        generic_calibration_examples(),
        evaluation_examples=generic_evaluation_examples(),
        dataset=dataset,
    )
