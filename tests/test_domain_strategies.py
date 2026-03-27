"""Integration tests for Phase 2 domain-specialist strategies."""

from __future__ import annotations

from datetime import datetime, timedelta

from autopredict.core.types import MarketCategory, MarketState
from autopredict.domains import (
    FinanceDomainAdapter,
    FinanceSpecialistStrategy,
    PoliticsDomainAdapter,
    PoliticsSpecialistStrategy,
    WeatherDomainAdapter,
    WeatherSpecialistStrategy,
)
from autopredict.evaluation import PredictionMarketBacktester, ResolvedMarketSnapshot
from autopredict.prediction_market import (
    DecisionStatus,
    PredictionMarketAgent,
    VenueConfig,
    VenueName,
    create_default_registry,
)


def _market(market_id: str, category: MarketCategory, market_prob: float) -> MarketState:
    return MarketState(
        market_id=market_id,
        question=f"Will {market_id} resolve YES?",
        market_prob=market_prob,
        expiry=datetime.now() + timedelta(days=5),
        category=category,
        best_bid=max(market_prob - 0.02, 0.01),
        best_ask=min(market_prob + 0.02, 0.99),
        bid_liquidity=200.0,
        ask_liquidity=200.0,
    )


def test_default_strategy_registry_includes_domain_specialists() -> None:
    """The default scaffold registry should expose Phase 2 domain specialists."""

    registry = create_default_registry()

    assert "finance_specialist" in registry.names()
    assert "weather_specialist" in registry.names()
    assert "politics_specialist" in registry.names()


def test_domain_specialists_trade_from_domain_bundles_in_backtests() -> None:
    """Backtests should thread domain bundles through to specialist strategies and results."""

    cases = (
        (
            "finance-market",
            MarketCategory.ECONOMICS,
            0.40,
            FinanceDomainAdapter.from_fixtures().build_bundle(),
            FinanceSpecialistStrategy(),
        ),
        (
            "weather-market",
            MarketCategory.SCIENCE,
            0.38,
            WeatherDomainAdapter.from_fixtures().build_bundle(),
            WeatherSpecialistStrategy(),
        ),
        (
            "politics-market",
            MarketCategory.POLITICS,
            0.35,
            PoliticsDomainAdapter.from_fixtures().build_bundle(),
            PoliticsSpecialistStrategy(),
        ),
    )

    venue = VenueConfig(name=VenueName.POLYMARKET, fee_bps=10.0)
    backtester = PredictionMarketBacktester()

    for market_id, category, market_prob, bundle, strategy in cases:
        result = backtester.run(
            PredictionMarketAgent(strategy=strategy),
            (
                ResolvedMarketSnapshot(
                    market=_market(market_id, category, market_prob),
                    venue=venue,
                    outcome=1,
                    metadata={"source": "fixture"},
                    domain_bundle=bundle,
                ),
            ),
        )

        assert result.decisions[0].status == DecisionStatus.TRADE
        assert result.decisions[0].metadata["domain"] == bundle.domain
        assert result.forecasts[0].metadata["domain"] == bundle.metadata["domain"]
        assert result.forecasts[0].metadata["market_family"] == bundle.metadata["market_family"]
        assert result.forecasts[0].metadata["model"].endswith("_question_conditioned")
        assert result.trades[0].metadata["regime"] == bundle.metadata["regime"]
        assert result.trades[0].metadata["strategy"] == strategy.name
        assert result.trades[0].metadata["model"].endswith("_question_conditioned")
