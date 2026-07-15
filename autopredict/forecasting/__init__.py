"""Typed forecast-provider boundary."""

from autopredict.forecasting.contracts import (
    ForecastAbstention,
    ForecastOutput,
    ForecastOrderBook,
    ForecastPriceLevel,
    ForecastProvider,
    ForecastProviderFailure,
    ForecastRequest,
    ForecastResult,
    ForecastValidationError,
    ObservationProvenance,
    ProviderProvenance,
    canonical_config_copy,
    canonical_config_hash,
    invoke_provider,
)
from autopredict.forecasting.providers import (
    CallableForecastProvider,
    MarketBaselineProvider,
    RecalibrationProvider,
)

__all__ = [
    "CallableForecastProvider",
    "ForecastAbstention",
    "ForecastOutput",
    "ForecastOrderBook",
    "ForecastPriceLevel",
    "ForecastProvider",
    "ForecastProviderFailure",
    "ForecastRequest",
    "ForecastResult",
    "ForecastValidationError",
    "MarketBaselineProvider",
    "ObservationProvenance",
    "ProviderProvenance",
    "RecalibrationProvider",
    "canonical_config_copy",
    "canonical_config_hash",
    "invoke_provider",
]
