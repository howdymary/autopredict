"""Fixture-backed finance ingestion helpers."""

from autopredict.ingestion.finance.features import build_finance_features
from autopredict.ingestion.finance.macro import (
    FixtureMacroIngestor,
    load_fixture_macro_batch,
    normalize_macro_releases,
    sample_macro_rows,
)
from autopredict.ingestion.finance.market_data import (
    FixtureFinanceMarketDataIngestor,
    load_fixture_market_data_batch,
    normalize_market_data,
    sample_market_data_rows,
)

__all__ = [
    "FixtureFinanceMarketDataIngestor",
    "FixtureMacroIngestor",
    "build_finance_features",
    "load_fixture_macro_batch",
    "load_fixture_market_data_batch",
    "normalize_macro_releases",
    "normalize_market_data",
    "sample_macro_rows",
    "sample_market_data_rows",
]
