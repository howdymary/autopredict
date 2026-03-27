"""Default question-conditioned weather model backed by offline datasets."""

from __future__ import annotations

from functools import lru_cache

from autopredict.domains.modeling import (
    QuestionConditionedDataset,
    QuestionConditionedExample,
    QuestionConditionedLinearModel,
    load_question_conditioned_dataset,
)

WEATHER_DATASET_FILE = "weather_domain_examples.json"


@lru_cache(maxsize=1)
def weather_dataset() -> QuestionConditionedDataset:
    """Return the cached offline weather dataset."""

    return load_question_conditioned_dataset(WEATHER_DATASET_FILE)


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
def build_default_weather_model() -> QuestionConditionedLinearModel:
    """Return the cached calibrated weather question-conditioned model."""

    dataset = weather_dataset()
    return QuestionConditionedLinearModel.fit_with_calibration(
        "weather_question_conditioned",
        weather_training_examples(),
        weather_calibration_examples(),
        evaluation_examples=weather_evaluation_examples(),
        dataset=dataset,
    )
