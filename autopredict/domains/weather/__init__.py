"""Weather domain adapters."""

from autopredict.domains.weather.adapter import WeatherDomainAdapter
from autopredict.domains.weather.model import (
    build_default_weather_model,
    weather_calibration_examples,
    weather_dataset,
    weather_evaluation_examples,
    weather_training_examples,
)
from autopredict.domains.weather.strategy import WeatherSpecialistStrategy

__all__ = [
    "WeatherDomainAdapter",
    "WeatherSpecialistStrategy",
    "build_default_weather_model",
    "weather_calibration_examples",
    "weather_dataset",
    "weather_evaluation_examples",
    "weather_training_examples",
]
