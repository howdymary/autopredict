"""Default question-conditioned politics model backed by offline datasets."""

from __future__ import annotations

from functools import lru_cache

from autopredict.domains.modeling import (
    QuestionConditionedDataset,
    QuestionConditionedExample,
    QuestionConditionedLinearModel,
    load_question_conditioned_dataset,
)

POLITICS_DATASET_FILE = "politics_domain_examples.json"


@lru_cache(maxsize=1)
def politics_dataset() -> QuestionConditionedDataset:
    """Return the cached offline politics dataset."""

    return load_question_conditioned_dataset(POLITICS_DATASET_FILE)


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
def build_default_politics_model() -> QuestionConditionedLinearModel:
    """Return the cached calibrated politics question-conditioned model."""

    dataset = politics_dataset()
    return QuestionConditionedLinearModel.fit_with_calibration(
        "politics_question_conditioned",
        politics_training_examples(),
        politics_calibration_examples(),
        evaluation_examples=politics_evaluation_examples(),
        dataset=dataset,
    )
