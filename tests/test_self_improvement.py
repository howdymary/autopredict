"""Contract tests for the Step 3 self-improvement layer."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from typing import Any

import pytest

from autopredict.core.types import MarketCategory, MarketState
from autopredict.evaluation import (
    BacktestResult,
    BinaryForecast,
    CalibrationBucket,
    CalibrationSummary,
    ScoringReport,
)
from autopredict.evaluation.backtest import ResolvedMarketSnapshot
from autopredict.prediction_market import VenueConfig, VenueName
from autopredict.self_improvement import (
    CandidateEvaluation,
    ImprovementLoopConfig,
    MutationConfig,
    SelectionConfig,
    SelfImprovementLoop,
    StrategyGenome,
    StrategyMutator,
    StrategySelector,
    WalkForwardConfig,
    WalkForwardReport,
    WalkForwardSplit,
)


def _load_module(module_name: str):
    """Import a Step 3 module and fail with a clear message if it is missing."""

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised if the package regresses
        pytest.fail(f"missing expected self-improvement module: {module_name} ({exc})")


@pytest.fixture
def baseline_genome() -> StrategyGenome:
    """Return the baseline mispriced-probability genome used by the scaffold."""

    return StrategyGenome(name="baseline")


@pytest.fixture
def resolved_snapshot() -> ResolvedMarketSnapshot:
    """Create a deterministic snapshot for the orchestration loop test."""

    return _make_resolved_snapshot(0, market_id="loop-market")


def _make_resolved_snapshot(
    index: int,
    *,
    market_id: str | None = None,
    category: MarketCategory = MarketCategory.OTHER,
    venue_name: VenueName = VenueName.POLYMARKET,
    best_bid: float = 0.49,
    best_ask: float = 0.51,
    bid_liquidity: float = 100.0,
    ask_liquidity: float = 100.0,
    market_metadata: dict[str, object] | None = None,
    snapshot_metadata: dict[str, object] | None = None,
) -> ResolvedMarketSnapshot:
    """Create a deterministic resolved market snapshot for Step 3 tests."""

    metadata = {"fair_prob": 0.62, "confidence": 0.91}
    if market_metadata is not None:
        metadata.update(market_metadata)

    market = MarketState(
        market_id=market_id or f"loop-market-{index}",
        question="Will the test market resolve YES?",
        market_prob=0.50,
        expiry=datetime(2026, 1, 3) + timedelta(days=index),
        category=category,
        best_bid=best_bid,
        best_ask=best_ask,
        bid_liquidity=bid_liquidity,
        ask_liquidity=ask_liquidity,
        metadata=metadata,
    )
    resolved_metadata = {"next_mid_price": 0.63}
    if snapshot_metadata is not None:
        resolved_metadata.update(snapshot_metadata)
    return ResolvedMarketSnapshot(
        market=market,
        venue=VenueConfig(name=venue_name, fee_bps=10.0),
        outcome=1,
        observed_at=datetime(2026, 1, 1) + timedelta(days=index),
        context_metadata={"probability_model": object()},
        snapshot_features={"fair_prob": 0.62, "confidence": 0.91},
        metadata=resolved_metadata,
    )


def _make_result(
    *,
    log_score: float,
    brier_score: float,
    calibration_gap: float,
    total_pnl: float,
    slippage_bps: float,
    num_filled_trades: int = 2,
    forecast_report_card: dict[str, Any] | None = None,
) -> BacktestResult:
    """Build a deterministic Step 2 result for selection tests."""

    calibration = CalibrationSummary(
        buckets=(
            CalibrationBucket(
                lower=0.0,
                upper=1.0,
                count=num_filled_trades,
                avg_probability=0.50,
                realized_rate=0.50 + calibration_gap,
            ),
        ),
        mean_absolute_gap=calibration_gap,
        max_absolute_gap=calibration_gap,
        base_rate=0.50,
    )
    scoring = ScoringReport(
        count=num_filled_trades,
        brier_score=brier_score,
        log_score=log_score,
        log_loss=-log_score,
        spherical_score=0.80,
        calibration=calibration,
    )
    forecasts = ()
    if forecast_report_card is not None:
        forecasts = (
            BinaryForecast(
                market_id="selection-metadata-market",
                probability=0.55,
                outcome=1,
                metadata={"report_card": forecast_report_card},
            ),
        )
    return BacktestResult(
        decisions=(),
        forecasts=forecasts,
        trades=(),
        scoring=scoring,
        metrics={
            "num_filled_trades": num_filled_trades,
            "total_pnl": total_pnl,
            "avg_slippage_bps": slippage_bps,
        },
    )


def test_self_improvement_modules_export_expected_contract() -> None:
    """The package should expose mutation, selection, and loop entrypoints."""

    package = _load_module("autopredict.self_improvement")
    mutation = _load_module("autopredict.self_improvement.mutation")
    selection = _load_module("autopredict.self_improvement.selection")
    loop = _load_module("autopredict.self_improvement.loop")

    for name in (
        "StrategyGenome",
        "MutationConfig",
        "StrategyMutator",
        "CandidateEvaluation",
        "SelectionConfig",
        "SelectionOutcome",
        "StrategySelector",
        "ImprovementLoopConfig",
        "ImprovementCycleReport",
        "SelfImprovementLoop",
        "WalkForwardConfig",
        "WalkForwardFoldReport",
        "WalkForwardReport",
        "WalkForwardSplit",
    ):
        assert hasattr(package, name), f"missing package export: {name}"

    for module, names in (
        (mutation, ("StrategyGenome", "MutationConfig", "StrategyMutator")),
        (selection, ("CandidateEvaluation", "SelectionConfig", "SelectionOutcome", "StrategySelector")),
        (
            loop,
            (
                "ImprovementLoopConfig",
                "ImprovementCycleReport",
                "SelfImprovementLoop",
                "WalkForwardConfig",
                "WalkForwardFoldReport",
                "WalkForwardReport",
                "WalkForwardSplit",
            ),
        ),
    ):
        for name in names:
            assert hasattr(module, name), f"missing module export: {name}"


def test_strategy_mutator_is_seeded_and_clamps_variants(baseline_genome: StrategyGenome) -> None:
    """Mutations should be deterministic for a fixed seed and stay within bounds."""

    config = MutationConfig(seed=7, population_size=5, relative_step=0.25)
    mutator = StrategyMutator(config)

    first_population = mutator.generate_population(baseline_genome)
    second_population = StrategyMutator(config).generate_population(baseline_genome)

    assert first_population == second_population
    assert len(first_population) == 5
    assert first_population[0] == baseline_genome
    assert first_population[1].name == "baseline_aggressive"
    assert first_population[2].name == "baseline_conservative"
    assert first_population[1].metadata == {"parent": "baseline", "mutation": "aggressive"}
    assert first_population[2].metadata == {"parent": "baseline", "mutation": "conservative"}

    aggressive = first_population[1]
    conservative = first_population[2]
    stochastic = first_population[3]

    assert aggressive.kelly_fraction == pytest.approx(0.3125)
    assert aggressive.aggressive_edge_threshold == pytest.approx(0.13125)
    assert aggressive.min_spread_capture == pytest.approx(7.5)
    assert aggressive.min_confidence == pytest.approx(0.65625)

    assert conservative.kelly_fraction == pytest.approx(0.1875)
    assert conservative.aggressive_edge_threshold == pytest.approx(0.16875)
    assert conservative.min_spread_capture == pytest.approx(12.5)
    assert conservative.min_confidence == pytest.approx(0.74375)

    assert 0.05 <= stochastic.kelly_fraction <= 1.0
    assert 0.02 <= stochastic.aggressive_edge_threshold <= 0.50
    assert 0.0 <= stochastic.min_spread_capture <= 100.0
    assert 0.50 <= stochastic.min_confidence <= 0.99

    built_strategy = baseline_genome.build_strategy()._strategy
    assert built_strategy.kelly_fraction == pytest.approx(baseline_genome.kelly_fraction)
    assert built_strategy.aggressive_edge_threshold == pytest.approx(
        baseline_genome.aggressive_edge_threshold
    )
    assert built_strategy.min_spread_capture == pytest.approx(baseline_genome.min_spread_capture)
    assert built_strategy.risk_limits.min_edge_threshold == pytest.approx(
        baseline_genome.min_edge_threshold
    )


def test_selection_policy_prefers_guardrailed_candidate_over_raw_score_outlier(
    baseline_genome: StrategyGenome,
) -> None:
    """A higher raw score should not override a calibration regression."""

    mutator = StrategyMutator(MutationConfig(seed=7, population_size=3, relative_step=0.25))
    baseline, aggressive, conservative = mutator.generate_population(baseline_genome)

    baseline_eval = CandidateEvaluation(
        genome=baseline,
        result=_make_result(
            log_score=0.20,
            brier_score=0.20,
            calibration_gap=0.01,
            total_pnl=1.0,
            slippage_bps=5.0,
        ),
    )
    aggressive_eval = CandidateEvaluation(
        genome=aggressive,
        result=_make_result(
            log_score=0.35,
            brier_score=0.10,
            calibration_gap=0.10,
            total_pnl=5.0,
            slippage_bps=1.0,
        ),
    )
    conservative_eval = CandidateEvaluation(
        genome=conservative,
        result=_make_result(
            log_score=0.30,
            brier_score=0.15,
            calibration_gap=0.01,
            total_pnl=3.0,
            slippage_bps=2.0,
        ),
    )

    selector = StrategySelector(
        SelectionConfig(
            min_filled_trades=1,
            max_brier_regression=0.20,
            max_calibration_gap_regression=0.05,
        )
    )
    outcome = selector.select([baseline_eval, aggressive_eval, conservative_eval])

    assert outcome.winner.genome.name == "baseline_conservative"
    assert [candidate.genome.name for candidate in outcome.accepted] == [
        "baseline",
        "baseline_conservative",
    ]
    assert [candidate.genome.name for candidate in outcome.rejected] == ["baseline_aggressive"]
    assert outcome.rejection_reasons["baseline_aggressive"] == ("calibration_regression",)
    assert outcome.to_dict()["winner"]["name"] == "baseline_conservative"


def test_self_improvement_loop_evaluates_population_and_picks_winner(
    monkeypatch: pytest.MonkeyPatch,
    baseline_genome: StrategyGenome,
    resolved_snapshot: ResolvedMarketSnapshot,
) -> None:
    """The outer loop should mutate, evaluate, and promote the best candidate."""

    loop = SelfImprovementLoop(
        ImprovementLoopConfig(
            mutation=MutationConfig(seed=7, population_size=4, relative_step=0.25),
            selection=SelectionConfig(
                min_filled_trades=1,
                max_brier_regression=0.20,
                max_calibration_gap_regression=0.05,
            ),
            starting_cash=1_000.0,
        )
    )

    def fake_run(agent, snapshots, starting_cash=1000.0):
        del snapshots, starting_cash
        strategy = agent.strategy._strategy
        if strategy.kelly_fraction == pytest.approx(0.3125):
            return _make_result(
                log_score=0.36,
                brier_score=0.10,
                calibration_gap=0.10,
                total_pnl=6.0,
                slippage_bps=1.0,
            )
        if strategy.kelly_fraction == pytest.approx(0.1875):
            return _make_result(
                log_score=0.32,
                brier_score=0.14,
                calibration_gap=0.01,
                total_pnl=4.0,
                slippage_bps=2.0,
            )
        if strategy.kelly_fraction != pytest.approx(0.25):
            return _make_result(
                log_score=0.24,
                brier_score=0.18,
                calibration_gap=0.02,
                total_pnl=2.0,
                slippage_bps=3.0,
            )
        return _make_result(
            log_score=0.20,
            brier_score=0.20,
            calibration_gap=0.01,
            total_pnl=1.0,
            slippage_bps=5.0,
        )

    monkeypatch.setattr(loop.backtester, "run", fake_run)

    report = loop.run(baseline_genome, [resolved_snapshot])

    assert [candidate.genome.name for candidate in report.population] == [
        "baseline",
        "baseline_aggressive",
        "baseline_conservative",
        "baseline_mutant_03",
    ]
    assert report.winner.genome.name == "baseline_conservative"
    assert report.selection.winner.genome.name == "baseline_conservative"
    assert report.selection.rejection_reasons["baseline_aggressive"] == ("calibration_regression",)
    assert report.winner.result.metrics["total_pnl"] == 4.0
    assert report.selection.to_dict()["winner"]["name"] == "baseline_conservative"


def test_selection_uses_model_report_cards_as_tiebreakers(
    baseline_genome: StrategyGenome,
) -> None:
    """When score surfaces tie, report-card coverage and stability should break ties."""

    mutator = StrategyMutator(MutationConfig(seed=7, population_size=3, relative_step=0.25))
    baseline, aggressive, _ = mutator.generate_population(baseline_genome)

    baseline_eval = CandidateEvaluation(
        genome=baseline,
        result=_make_result(
            log_score=0.25,
            brier_score=0.17,
            calibration_gap=0.01,
            total_pnl=2.0,
            slippage_bps=3.0,
            forecast_report_card={
                "coverage_score": 0.40,
                "held_out_calibration_stability": 0.08,
            },
        ),
    )
    aggressive_eval = CandidateEvaluation(
        genome=aggressive,
        result=_make_result(
            log_score=0.25,
            brier_score=0.17,
            calibration_gap=0.01,
            total_pnl=2.0,
            slippage_bps=3.0,
            forecast_report_card={
                "coverage_score": 0.82,
                "held_out_calibration_stability": 0.03,
            },
        ),
    )

    selector = StrategySelector()
    outcome = selector.select([baseline_eval, aggressive_eval])

    assert outcome.winner.genome.name == "baseline_aggressive"


def test_selection_rejects_candidates_with_worse_held_out_calibration_stability(
    baseline_genome: StrategyGenome,
) -> None:
    """Phase 5 should block candidates whose model cards show worse held-out stability."""

    mutator = StrategyMutator(MutationConfig(seed=7, population_size=3, relative_step=0.25))
    baseline, aggressive, _ = mutator.generate_population(baseline_genome)

    baseline_eval = CandidateEvaluation(
        genome=baseline,
        result=_make_result(
            log_score=0.20,
            brier_score=0.20,
            calibration_gap=0.01,
            total_pnl=1.0,
            slippage_bps=5.0,
            forecast_report_card={
                "coverage_score": 0.60,
                "held_out_calibration_stability": 0.03,
            },
        ),
    )
    aggressive_eval = CandidateEvaluation(
        genome=aggressive,
        result=_make_result(
            log_score=0.32,
            brier_score=0.12,
            calibration_gap=0.01,
            total_pnl=4.0,
            slippage_bps=1.0,
            forecast_report_card={
                "coverage_score": 0.90,
                "held_out_calibration_stability": 0.20,
            },
        ),
    )

    selector = StrategySelector(
        SelectionConfig(
            min_filled_trades=1,
            max_brier_regression=0.20,
            max_calibration_gap_regression=0.05,
            max_held_out_calibration_stability_regression=0.05,
        )
    )
    outcome = selector.select([baseline_eval, aggressive_eval])

    assert outcome.winner.genome.name == "baseline"
    assert outcome.rejection_reasons["baseline_aggressive"] == (
        "held_out_calibration_stability_regression",
    )


def test_walk_forward_promotes_candidate_only_after_validation(
    monkeypatch: pytest.MonkeyPatch,
    baseline_genome: StrategyGenome,
) -> None:
    """Walk-forward promotion should depend on held-out validation, not train only."""

    loop = SelfImprovementLoop(
        ImprovementLoopConfig(
            mutation=MutationConfig(seed=7, population_size=3, relative_step=0.25),
            selection=SelectionConfig(
                min_filled_trades=1,
                max_brier_regression=0.20,
                max_calibration_gap_regression=0.05,
            ),
            walk_forward=WalkForwardConfig(train_size=2, validation_size=1, step_size=1),
            starting_cash=1_000.0,
        )
    )
    snapshots = [_make_resolved_snapshot(index) for index in range(3)]

    def fake_run(agent, fold_snapshots, starting_cash=1000.0):
        del starting_cash
        strategy = agent.strategy._strategy
        market_ids = tuple(snapshot.market.market_id for snapshot in fold_snapshots)

        if market_ids == ("loop-market-0", "loop-market-1"):
            if abs(strategy.kelly_fraction - 0.3125) <= 1e-9:
                return _make_result(
                    log_score=0.36,
                    brier_score=0.10,
                    calibration_gap=0.10,
                    total_pnl=6.0,
                    slippage_bps=1.0,
                )
            if abs(strategy.kelly_fraction - 0.1875) <= 1e-9:
                return _make_result(
                    log_score=0.32,
                    brier_score=0.14,
                    calibration_gap=0.01,
                    total_pnl=4.0,
                    slippage_bps=2.0,
                )
            return _make_result(
                log_score=0.20,
                brier_score=0.20,
                calibration_gap=0.01,
                total_pnl=1.0,
                slippage_bps=5.0,
            )

        if market_ids == ("loop-market-2",):
            if abs(strategy.kelly_fraction - 0.1875) <= 1e-9:
                return _make_result(
                    log_score=0.28,
                    brier_score=0.15,
                    calibration_gap=0.01,
                    total_pnl=3.0,
                    slippage_bps=2.0,
                )
            return _make_result(
                log_score=0.18,
                brier_score=0.21,
                calibration_gap=0.02,
                total_pnl=1.0,
                slippage_bps=5.0,
            )

        raise AssertionError(f"unexpected fold request: {market_ids}")

    monkeypatch.setattr(loop.backtester, "run", fake_run)

    report = loop.run_walk_forward(baseline_genome, snapshots)

    assert isinstance(report, WalkForwardReport)
    assert report.initial_genome.name == "baseline"
    assert report.final_genome.name == "baseline_conservative"
    assert report.promotions == 1
    assert len(report.folds) == 1
    fold = report.folds[0]
    assert fold.baseline_genome.name == "baseline"
    assert fold.candidate_genome.name == "baseline_conservative"
    assert fold.validation_candidate is not None
    assert fold.promoted is True
    assert fold.validation_selection.winner.genome.name == "baseline_conservative"
    assert fold.train_split_labels == ()
    assert fold.validation_split_labels == ()


def test_walk_forward_rejects_candidate_that_fails_validation_guardrails(
    monkeypatch: pytest.MonkeyPatch,
    baseline_genome: StrategyGenome,
) -> None:
    """Held-out validation should block train-fold winners that regress calibration."""

    loop = SelfImprovementLoop(
        ImprovementLoopConfig(
            mutation=MutationConfig(seed=7, population_size=3, relative_step=0.25),
            selection=SelectionConfig(
                min_filled_trades=1,
                max_brier_regression=0.20,
                max_calibration_gap_regression=0.05,
            ),
            walk_forward=WalkForwardConfig(train_size=2, validation_size=1, step_size=1),
            starting_cash=1_000.0,
        )
    )
    snapshots = [_make_resolved_snapshot(index) for index in range(3)]

    def fake_run(agent, fold_snapshots, starting_cash=1000.0):
        del starting_cash
        strategy = agent.strategy._strategy
        market_ids = tuple(snapshot.market.market_id for snapshot in fold_snapshots)

        if market_ids == ("loop-market-0", "loop-market-1"):
            if abs(strategy.kelly_fraction - 0.1875) <= 1e-9:
                return _make_result(
                    log_score=0.32,
                    brier_score=0.14,
                    calibration_gap=0.01,
                    total_pnl=4.0,
                    slippage_bps=2.0,
                )
            return _make_result(
                log_score=0.20,
                brier_score=0.20,
                calibration_gap=0.01,
                total_pnl=1.0,
                slippage_bps=5.0,
            )

        if market_ids == ("loop-market-2",):
            if abs(strategy.kelly_fraction - 0.1875) <= 1e-9:
                return _make_result(
                    log_score=0.30,
                    brier_score=0.13,
                    calibration_gap=0.09,
                    total_pnl=3.0,
                    slippage_bps=2.0,
                )
            return _make_result(
                log_score=0.18,
                brier_score=0.21,
                calibration_gap=0.02,
                total_pnl=1.0,
                slippage_bps=5.0,
            )

        raise AssertionError(f"unexpected fold request: {market_ids}")

    monkeypatch.setattr(loop.backtester, "run", fake_run)

    report = loop.run_walk_forward(baseline_genome, snapshots)

    assert report.final_genome.name == "baseline"
    assert report.promotions == 0
    assert len(report.folds) == 1
    fold = report.folds[0]
    assert fold.promoted is False
    assert fold.validation_candidate is not None
    assert fold.validation_selection.winner.genome.name == "baseline"
    assert fold.validation_selection.rejection_reasons["baseline_conservative"] == (
        "calibration_regression",
    )


def test_regime_walk_forward_uses_regime_blocks_for_holdouts(
    monkeypatch: pytest.MonkeyPatch,
    baseline_genome: StrategyGenome,
) -> None:
    """Regime mode should validate on contiguous regime blocks instead of raw time slices."""

    loop = SelfImprovementLoop(
        ImprovementLoopConfig(
            mutation=MutationConfig(seed=7, population_size=3, relative_step=0.25),
            selection=SelectionConfig(
                min_filled_trades=1,
                max_brier_regression=0.20,
                max_calibration_gap_regression=0.05,
            ),
            walk_forward=WalkForwardConfig(
                train_size=1,
                validation_size=1,
                step_size=1,
                split_mode=WalkForwardSplit.REGIME,
                regime_key="metadata.regime",
            ),
            starting_cash=1_000.0,
        )
    )
    snapshots = [
        _make_resolved_snapshot(0, snapshot_metadata={"regime": "calm"}),
        _make_resolved_snapshot(1, snapshot_metadata={"regime": "calm"}),
        _make_resolved_snapshot(2, snapshot_metadata={"regime": "volatile"}),
        _make_resolved_snapshot(3, snapshot_metadata={"regime": "volatile"}),
    ]

    def fake_run(agent, fold_snapshots, starting_cash=1000.0):
        del starting_cash
        strategy = agent.strategy._strategy
        market_ids = tuple(snapshot.market.market_id for snapshot in fold_snapshots)

        if market_ids == ("loop-market-0", "loop-market-1"):
            if abs(strategy.kelly_fraction - 0.1875) <= 1e-9:
                return _make_result(
                    log_score=0.31,
                    brier_score=0.14,
                    calibration_gap=0.01,
                    total_pnl=4.0,
                    slippage_bps=2.0,
                )
            return _make_result(
                log_score=0.20,
                brier_score=0.20,
                calibration_gap=0.01,
                total_pnl=1.0,
                slippage_bps=5.0,
            )

        if market_ids == ("loop-market-2", "loop-market-3"):
            if abs(strategy.kelly_fraction - 0.1875) <= 1e-9:
                return _make_result(
                    log_score=0.29,
                    brier_score=0.13,
                    calibration_gap=0.01,
                    total_pnl=3.0,
                    slippage_bps=2.0,
                )
            return _make_result(
                log_score=0.18,
                brier_score=0.21,
                calibration_gap=0.02,
                total_pnl=1.0,
                slippage_bps=5.0,
            )

        raise AssertionError(f"unexpected fold request: {market_ids}")

    monkeypatch.setattr(loop.backtester, "run", fake_run)

    report = loop.run_walk_forward(baseline_genome, snapshots)

    assert report.final_genome.name == "baseline_conservative"
    assert report.promotions == 1
    assert len(report.folds) == 1
    fold = report.folds[0]
    assert fold.train_split_labels == ("calm",)
    assert fold.validation_split_labels == ("volatile",)
    assert fold.validation_market_ids == ("loop-market-2", "loop-market-3")


def test_market_family_holdouts_keep_validation_isolated_by_category(
    monkeypatch: pytest.MonkeyPatch,
    baseline_genome: StrategyGenome,
) -> None:
    """Market-family mode should hold out complete categories instead of time windows."""

    loop = SelfImprovementLoop(
        ImprovementLoopConfig(
            mutation=MutationConfig(seed=7, population_size=3, relative_step=0.25),
            selection=SelectionConfig(
                min_filled_trades=1,
                max_brier_regression=0.20,
                max_calibration_gap_regression=0.05,
            ),
            walk_forward=WalkForwardConfig(
                train_size=2,
                validation_size=1,
                step_size=1,
                split_mode=WalkForwardSplit.MARKET_FAMILY,
                family_key="category",
            ),
            starting_cash=1_000.0,
        )
    )
    snapshots = [
        _make_resolved_snapshot(0, category=MarketCategory.POLITICS, market_id="politics-0"),
        _make_resolved_snapshot(1, category=MarketCategory.POLITICS, market_id="politics-1"),
        _make_resolved_snapshot(2, category=MarketCategory.CRYPTO, market_id="crypto-0"),
        _make_resolved_snapshot(3, category=MarketCategory.CRYPTO, market_id="crypto-1"),
        _make_resolved_snapshot(4, category=MarketCategory.SCIENCE, market_id="science-0"),
        _make_resolved_snapshot(5, category=MarketCategory.SCIENCE, market_id="science-1"),
    ]

    def fake_run(agent, fold_snapshots, starting_cash=1000.0):
        del starting_cash
        strategy = agent.strategy._strategy
        categories = {snapshot.market.category.value for snapshot in fold_snapshots}

        if len(categories) > 1:
            if abs(strategy.kelly_fraction - 0.1875) <= 1e-9:
                return _make_result(
                    log_score=0.31,
                    brier_score=0.14,
                    calibration_gap=0.01,
                    total_pnl=4.0,
                    slippage_bps=2.0,
                )
            return _make_result(
                log_score=0.20,
                brier_score=0.20,
                calibration_gap=0.01,
                total_pnl=1.0,
                slippage_bps=5.0,
            )

        if categories == {"politics"} or categories == {"crypto"} or categories == {"science"}:
            if abs(strategy.kelly_fraction - 0.1875) <= 1e-9:
                return _make_result(
                    log_score=0.18,
                    brier_score=0.22,
                    calibration_gap=0.02,
                    total_pnl=1.0,
                    slippage_bps=3.0,
                )
            return _make_result(
                log_score=0.22,
                brier_score=0.18,
                calibration_gap=0.01,
                total_pnl=2.0,
                slippage_bps=4.0,
            )

        raise AssertionError(f"unexpected category mix: {categories}")

    monkeypatch.setattr(loop.backtester, "run", fake_run)

    report = loop.run_walk_forward(baseline_genome, snapshots)

    assert report.final_genome.name == "baseline"
    assert report.promotions == 0
    assert [fold.validation_split_labels for fold in report.folds] == [
        ("politics",),
        ("crypto",),
        ("science",),
    ]
    assert report.folds[0].validation_market_ids == ("politics-0", "politics-1")
    assert report.folds[1].validation_market_ids == ("crypto-0", "crypto-1")
    assert report.folds[2].validation_market_ids == ("science-0", "science-1")


def test_market_family_holdouts_prefer_raw_category_metadata_over_enum_buckets(
    monkeypatch: pytest.MonkeyPatch,
    baseline_genome: StrategyGenome,
) -> None:
    """Default category holdouts should preserve raw dataset categories when available."""

    loop = SelfImprovementLoop(
        ImprovementLoopConfig(
            mutation=MutationConfig(seed=7, population_size=3, relative_step=0.25),
            selection=SelectionConfig(
                min_filled_trades=1,
                max_brier_regression=0.20,
                max_calibration_gap_regression=0.05,
            ),
            walk_forward=WalkForwardConfig(
                train_size=2,
                validation_size=1,
                step_size=1,
                split_mode=WalkForwardSplit.MARKET_FAMILY,
                family_key="category",
            ),
            starting_cash=1_000.0,
        )
    )
    snapshots = [
        _make_resolved_snapshot(
            0,
            category=MarketCategory.OTHER,
            market_id="macro-0",
            market_metadata={"category": "macro"},
        ),
        _make_resolved_snapshot(
            1,
            category=MarketCategory.OTHER,
            market_id="macro-1",
            market_metadata={"category": "macro"},
        ),
        _make_resolved_snapshot(
            2,
            category=MarketCategory.OTHER,
            market_id="geo-0",
            market_metadata={"category": "geopolitics"},
        ),
        _make_resolved_snapshot(
            3,
            category=MarketCategory.OTHER,
            market_id="geo-1",
            market_metadata={"category": "geopolitics"},
        ),
        _make_resolved_snapshot(
            4,
            category=MarketCategory.OTHER,
            market_id="crypto-0",
            market_metadata={"category": "crypto"},
        ),
        _make_resolved_snapshot(
            5,
            category=MarketCategory.OTHER,
            market_id="crypto-1",
            market_metadata={"category": "crypto"},
        ),
    ]

    def fake_run(agent, fold_snapshots, starting_cash=1000.0):
        del agent, starting_cash
        return _make_result(
            log_score=0.20,
            brier_score=0.20,
            calibration_gap=0.01,
            total_pnl=1.0,
            slippage_bps=5.0,
        )

    monkeypatch.setattr(loop.backtester, "run", fake_run)

    report = loop.run_walk_forward(baseline_genome, snapshots)

    assert [fold.validation_split_labels for fold in report.folds] == [
        ("macro",),
        ("geopolitics",),
        ("crypto",),
    ]
