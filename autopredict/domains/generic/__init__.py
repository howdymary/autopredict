"""Generic fallback domain strategies and models."""

from autopredict.domains.generic.model import (
    build_default_generic_model,
    generic_calibration_examples,
    generic_dataset,
    generic_evaluation_examples,
    generic_training_examples,
)
from autopredict.domains.generic.strategy import GenericSpecialistStrategy

__all__ = [
    "GenericSpecialistStrategy",
    "build_default_generic_model",
    "generic_calibration_examples",
    "generic_dataset",
    "generic_evaluation_examples",
    "generic_training_examples",
]
