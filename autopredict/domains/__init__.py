"""Domain adapters that map evidence into reusable prediction-market features."""

from autopredict.domains.base import (
    REQUIRED_METADATA_KEYS,
    DomainAdapter,
    DomainFeatureBundle,
    SpecialistOrderPolicy,
)
from autopredict.domains.finance import (
    FinanceDomainAdapter,
    FinanceSpecialistStrategy,
    build_default_finance_model,
    finance_calibration_examples,
    finance_dataset,
    finance_evaluation_examples,
    finance_training_examples,
)
from autopredict.domains.modeling import (
    DatasetSplitSummary,
    DomainModelReportCard,
    ModelPrediction,
    QuestionConditionedDataset,
    QuestionConditionedExample,
    QuestionConditionedLinearModel,
    build_domain_report_card,
    load_question_conditioned_dataset,
)
from autopredict.domains.politics import (
    PoliticsDomainAdapter,
    PoliticsSpecialistStrategy,
    build_default_politics_model,
    politics_calibration_examples,
    politics_dataset,
    politics_evaluation_examples,
    politics_training_examples,
)
from autopredict.domains.registry import DomainRegistry, domain_registry
from autopredict.domains.weather import (
    WeatherDomainAdapter,
    WeatherSpecialistStrategy,
    build_default_weather_model,
    weather_calibration_examples,
    weather_dataset,
    weather_evaluation_examples,
    weather_training_examples,
)

__all__ = [
    "REQUIRED_METADATA_KEYS",
    "DomainAdapter",
    "DomainFeatureBundle",
    "DomainRegistry",
    "DomainModelReportCard",
    "DatasetSplitSummary",
    "FinanceDomainAdapter",
    "FinanceSpecialistStrategy",
    "ModelPrediction",
    "QuestionConditionedDataset",
    "PoliticsDomainAdapter",
    "PoliticsSpecialistStrategy",
    "QuestionConditionedExample",
    "QuestionConditionedLinearModel",
    "SpecialistOrderPolicy",
    "WeatherDomainAdapter",
    "WeatherSpecialistStrategy",
    "build_default_finance_model",
    "build_default_politics_model",
    "build_default_weather_model",
    "build_domain_report_card",
    "domain_registry",
    "finance_calibration_examples",
    "finance_dataset",
    "finance_evaluation_examples",
    "finance_training_examples",
    "load_question_conditioned_dataset",
    "politics_calibration_examples",
    "politics_dataset",
    "politics_evaluation_examples",
    "politics_training_examples",
    "weather_calibration_examples",
    "weather_dataset",
    "weather_evaluation_examples",
    "weather_training_examples",
]
