"""Tests for the legacy run_experiment backtest path."""

from __future__ import annotations

import json

import pytest

from autopredict.run_experiment import _build_order_book, run_backtest


def test_build_order_book_rejects_invalid_prices():
    with pytest.raises(ValueError, match="must be a finite probability"):
        _build_order_book(
            "bad-market",
            {
                "bids": [[1.2, 10.0]],
                "asks": [[0.6, 10.0]],
            },
        )


def test_build_order_book_rejects_non_positive_size():
    with pytest.raises(ValueError, match="must be a finite positive float"):
        _build_order_book(
            "bad-market",
            {
                "bids": [[0.4, 0.0]],
                "asks": [[0.6, 10.0]],
            },
        )


def test_build_order_book_rejects_crossed_books():
    with pytest.raises(ValueError, match="crossed order book"):
        _build_order_book(
            "crossed-market",
            {
                "bids": [[0.7, 10.0]],
                "asks": [[0.6, 10.0]],
            },
        )


def test_run_backtest_rejects_invalid_outcome(tmp_path):
    config_path = tmp_path / "config.json"
    dataset_path = tmp_path / "dataset.json"
    strategy_path = tmp_path / "strategy.md"

    config_path.write_text(
        json.dumps(
            {
                "min_edge": 0.05,
                "aggressive_edge": 0.12,
                "max_risk_fraction": 0.02,
                "max_position_notional": 25.0,
                "min_book_liquidity": 60.0,
                "max_spread_pct": 0.04,
                "max_depth_fraction": 0.15,
                "split_threshold_fraction": 0.25,
                "passive_requote_fraction": 0.25,
            }
        ),
        encoding="utf-8",
    )
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "market_id": "bad-outcome",
                    "market_prob": 0.52,
                    "fair_prob": 0.60,
                    "outcome": 2,
                    "time_to_expiry_hours": 24.0,
                    "next_mid_price": 0.55,
                    "order_book": {
                        "bids": [[0.50, 100.0]],
                        "asks": [[0.54, 100.0]],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    strategy_path.write_text("test guidance", encoding="utf-8")

    with pytest.raises(ValueError, match="outcome must be 0 or 1"):
        run_backtest(
            config_path=config_path,
            dataset_path=dataset_path,
            strategy_guidance_path=strategy_path,
        )


def test_run_backtest_marks_external_forecast_source(tmp_path):
    config_path = tmp_path / "config.json"
    dataset_path = tmp_path / "dataset.json"
    strategy_path = tmp_path / "strategy.md"

    config_path.write_text(
        json.dumps(
            {
                "min_edge": 0.05,
                "aggressive_edge": 0.12,
                "max_risk_fraction": 0.02,
                "max_position_notional": 25.0,
                "min_book_liquidity": 60.0,
                "max_spread_pct": 0.04,
                "max_depth_fraction": 0.15,
                "split_threshold_fraction": 0.25,
                "passive_requote_fraction": 0.25,
            }
        ),
        encoding="utf-8",
    )
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "market_id": "m1",
                    "market_prob": 0.50,
                    "fair_prob": 0.55,
                    "outcome": 0,
                    "time_to_expiry_hours": 24.0,
                    "next_mid_price": 0.50,
                    "order_book": {
                        "bids": [[0.499, 100.0]],
                        "asks": [[0.501, 100.0]],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    strategy_path.write_text("test guidance", encoding="utf-8")

    metrics = run_backtest(
        config_path=config_path,
        dataset_path=dataset_path,
        strategy_guidance_path=strategy_path,
    )

    assert metrics["forecast_source"] == "dataset_fair_prob"
    assert metrics["forecast_scope"] == "input_forecast_quality"
    assert metrics["agent_feedback"]["weakness"] == "forecast_input_quality"
