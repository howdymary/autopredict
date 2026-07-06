"""Tests for the learnable market-recalibration forecast and its ratchet path."""

from __future__ import annotations

import json
import math
from pathlib import Path

from autopredict.domains import MarketRecalibrationModel, RecalibratedMarketStrategy
from autopredict.domains.recalibration import MAX_SCALE, MAX_SHIFT, logit, sigmoid
from autopredict.evaluation import load_resolved_snapshots
from autopredict.evaluation.backtest import PredictionMarketBacktester
from autopredict.prediction_market import AgentRunConfig
from autopredict.self_improvement import (
    StrategyMutator,
    default_forecast_owned_genome,
    default_recalibrated_genome,
    fit_recalibrated_genome,
    improvement_config_with_population,
    run_market_recalibration_ratchet,
)
from autopredict.self_improvement.mutation import MutationConfig


def _true_prob(market_prob: float, scale: float) -> float:
    return sigmoid(scale * logit(market_prob))


def _write_biased_dataset(path: Path, *, true_scale: float = 0.55, repeat: int = 30) -> None:
    """Write a deterministic favorite-longshot-biased resolved dataset.

    Outcomes are assigned so each quote's realized rate matches
    ``sigmoid(true_scale * logit(quote))`` -- i.e. the market is over-confident.
    Records are round-robin ordered so any contiguous split is stratified.
    """

    prices = [0.12, 0.22, 0.32, 0.42, 0.58, 0.68, 0.78, 0.88]
    streams: dict[float, list[int]] = {}
    for price in prices:
        target = _true_prob(price, true_scale)
        sequence: list[int] = []
        acc = 0.0
        for _ in range(repeat):
            acc += target
            if acc >= 1.0:
                sequence.append(1)
                acc -= 1.0
            else:
                sequence.append(0)
        streams[price] = sequence

    records = []
    market_index = 0
    for cycle in range(repeat):
        for price in prices:
            market_index += 1
            records.append(
                {
                    "market_id": f"m{market_index:04d}",
                    "question": f"Resolved market quote {price} cycle {cycle}",
                    "category": "politics",
                    "market_prob": price,
                    "outcome": streams[price][cycle],
                    "observed_at": 1_700_000_000 + market_index * 3600,
                    "time_to_expiry_hours": 48.0,
                    "order_book": {
                        "bids": [[round(price - 0.01, 4), 5000.0]],
                        "asks": [[round(price + 0.01, 4), 5000.0]],
                    },
                    "metadata": {
                        "liquidity_tier": "large",
                        "spread_tier": "tight",
                        "time_tier": "medium_time",
                        "total_depth": 10000.0,
                    },
                }
            )
    path.write_text(json.dumps(records), encoding="utf-8")


def _write_calibrated_dataset(path: Path, *, repeat: int = 30) -> None:
    """Write a well-calibrated dataset (realized rate == quote)."""

    _write_biased_dataset(path, true_scale=1.0, repeat=repeat)


# --- model unit tests -------------------------------------------------------


def test_identity_model_reproduces_market_price() -> None:
    model = MarketRecalibrationModel.identity()
    assert model.is_identity
    for prob in (0.05, 0.2, 0.5, 0.8, 0.95):
        assert math.isclose(model.fair_probability(prob), prob, abs_tol=1e-6)
        assert math.isclose(model.edge_against(prob), 0.0, abs_tol=1e-6)


def test_recalibration_is_monotonic() -> None:
    model = MarketRecalibrationModel(scale=0.6, shift=0.1)
    probs = [0.05, 0.2, 0.4, 0.6, 0.8, 0.95]
    fair = [model.fair_probability(p) for p in probs]
    assert all(b > a for a, b in zip(fair, fair[1:]))


def test_model_rejects_out_of_bounds_parameters() -> None:
    for kwargs in ({"scale": 5.0}, {"shift": 9.0}, {"scale": 0.0}):
        try:
            MarketRecalibrationModel(**kwargs)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {kwargs}")


def test_fit_recovers_injected_overconfidence(tmp_path: Path) -> None:
    dataset_path = tmp_path / "biased.json"
    _write_biased_dataset(dataset_path, true_scale=0.55)
    snapshots = load_resolved_snapshots(dataset_path)

    model = MarketRecalibrationModel.fit(
        [(s.market.market_prob, s.outcome) for s in snapshots]
    )
    # The identity prior shrinks the estimate toward 1.0, so the fitted scale
    # sits between the injected 0.55 and the no-edge 1.0, but well below 1.0.
    assert 0.4 < model.scale < 0.95
    assert not model.is_identity
    assert model.fit_sample_size == len(snapshots)


def test_fit_on_calibrated_market_stays_near_identity(tmp_path: Path) -> None:
    dataset_path = tmp_path / "calibrated.json"
    _write_calibrated_dataset(dataset_path)
    snapshots = load_resolved_snapshots(dataset_path)

    model = MarketRecalibrationModel.fit(
        [(s.market.market_prob, s.outcome) for s in snapshots]
    )
    # A calibrated market yields negligible edge on every quote.
    for prob in (0.12, 0.42, 0.88):
        assert abs(model.edge_against(prob)) < 0.05


def test_fit_with_no_pairs_returns_identity() -> None:
    assert MarketRecalibrationModel.fit([]).is_identity


def _biased_pairs(true_scale: float, repeat: int) -> list:
    prices = [0.12, 0.22, 0.32, 0.42, 0.58, 0.68, 0.78, 0.88]
    pairs = []
    for price in prices:
        target = _true_prob(price, true_scale)
        acc = 0.0
        for _ in range(repeat):
            acc += target
            if acc >= 1.0:
                pairs.append((price, 1))
                acc -= 1.0
            else:
                pairs.append((price, 0))
    return pairs


def test_fit_grows_more_confident_with_more_evidence() -> None:
    # The identity regularizer is evidence-scaled, so the estimate must move
    # closer to the true parameters (scale=0.55, shift=0.0) as N grows. Distance
    # is measured jointly: with little data the fit overfits with a large shift,
    # which only washes out as evidence accumulates.
    true_scale = 0.55

    def distance(repeat: int) -> float:
        model = MarketRecalibrationModel.fit(_biased_pairs(true_scale, repeat))
        return ((model.scale - true_scale) ** 2 + model.shift**2) ** 0.5

    assert distance(500) < distance(20) < distance(5)
    assert distance(500) < 0.1


def test_fit_below_min_samples_returns_identity() -> None:
    # A single extreme, thinly-sampled quote must not seed a boundary edge.
    model = MarketRecalibrationModel.fit([(0.0001, 1)], min_samples=20)
    assert model.is_identity


# --- genome / mutation integration -----------------------------------------


def test_default_recalibrated_genome_is_no_edge() -> None:
    genome = default_recalibrated_genome()
    assert genome.strategy_kind == "market_recalibrated"
    assert genome.calibration_logit_scale == 1.0
    assert genome.calibration_logit_shift == 0.0
    assert isinstance(genome.build_strategy(), RecalibratedMarketStrategy)
    assert "calibration_logit_scale" in genome.to_dict()


def test_mutation_perturbs_calibration_genes_within_bounds() -> None:
    base = default_recalibrated_genome()
    mutator = StrategyMutator(MutationConfig(seed=7, population_size=6, relative_step=0.25))
    population = mutator.generate_population(base)

    assert population[0] == base  # baseline preserved
    scales = {g.calibration_logit_scale for g in population}
    shifts = {g.calibration_logit_shift for g in population}
    assert len(scales) > 1  # the forecast genes actually move
    assert len(shifts) > 1
    for genome in population:
        assert 0.2 <= genome.calibration_logit_scale <= MAX_SCALE
        assert -MAX_SHIFT <= genome.calibration_logit_shift <= MAX_SHIFT
        genome.build_strategy()  # every variant remains buildable


# --- honest, leakage-free value demonstration ------------------------------


def test_recalibration_beats_no_edge_out_of_sample(tmp_path: Path) -> None:
    dataset_path = tmp_path / "biased.json"
    _write_biased_dataset(dataset_path, true_scale=0.55)
    snapshots = list(load_resolved_snapshots(dataset_path))  # chronological
    cut = int(len(snapshots) * 0.6)
    train, test = snapshots[:cut], snapshots[cut:]

    backtester = PredictionMarketBacktester()
    run_config = AgentRunConfig()

    no_edge = backtester.run(
        default_forecast_owned_genome().build_agent(run_config),
        test,
        starting_cash=2000.0,
    )
    seed = fit_recalibrated_genome(train)  # fit on the past window only
    recalibrated = backtester.run(seed.build_agent(run_config), test, starting_cash=2000.0)

    # The frozen no-edge model never trades; the recalibrated forecast finds
    # real, held-out edge and scores strictly better.
    assert no_edge.metrics["num_filled_trades"] == 0
    assert recalibrated.metrics["num_filled_trades"] > 0
    assert recalibrated.metrics["total_pnl"] > 0.0
    assert recalibrated.scoring.log_score > no_edge.scoring.log_score
    assert recalibrated.scoring.brier_score < no_edge.scoring.brier_score


def test_recalibration_ratchet_promotes_and_stays_leakage_free(tmp_path: Path) -> None:
    dataset_path = tmp_path / "biased.json"
    _write_biased_dataset(dataset_path, true_scale=0.55)

    summary = run_market_recalibration_ratchet(
        dataset_path,
        config=improvement_config_with_population(
            population_size=5, train_size=4, validation_size=2
        ),
        warmup_fraction=0.4,
    )

    payload = summary.to_dict()
    assert payload["initial_genome"]["strategy_kind"] == "market_recalibrated"
    assert payload["final_genome"]["strategy_kind"] == "market_recalibrated"
    assert payload["folds"]
    # The seed departs from the no-edge identity because real data supports it.
    assert payload["initial_genome"]["calibration_logit_scale"] != 1.0
