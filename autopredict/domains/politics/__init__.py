"""Politics domain adapters."""

from autopredict.domains.politics.adapter import PoliticsDomainAdapter
from autopredict.domains.politics.model import (
    build_default_politics_model,
    politics_calibration_examples,
    politics_dataset,
    politics_evaluation_examples,
    politics_training_examples,
)
from autopredict.domains.politics.strategy import PoliticsSpecialistStrategy

__all__ = [
    "PoliticsDomainAdapter",
    "PoliticsSpecialistStrategy",
    "build_default_politics_model",
    "politics_calibration_examples",
    "politics_dataset",
    "politics_evaluation_examples",
    "politics_training_examples",
]
