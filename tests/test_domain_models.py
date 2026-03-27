"""Tests for question-conditioned domain models."""

from __future__ import annotations

from autopredict.domains import (
    FinanceDomainAdapter,
    PoliticsDomainAdapter,
    QuestionConditionedLinearModel,
    WeatherDomainAdapter,
    build_default_finance_model,
    build_default_politics_model,
    build_default_weather_model,
    finance_calibration_examples,
    finance_dataset,
    finance_evaluation_examples,
    finance_training_examples,
    politics_calibration_examples,
    politics_dataset,
    politics_evaluation_examples,
    politics_training_examples,
    weather_calibration_examples,
    weather_dataset,
    weather_evaluation_examples,
    weather_training_examples,
)


def test_question_conditioning_changes_probability_for_same_bundle_features() -> None:
    """Changing the market question should change the model probability."""

    finance_bundle = FinanceDomainAdapter.from_fixtures().build_bundle()
    finance_model = build_default_finance_model()
    hold_prediction = finance_model.predict(
        "Will the Fed hold rates at the March meeting?",
        {**finance_bundle.features, "market_prob": 0.45},
        finance_bundle.metadata,
    )
    cut_prediction = finance_model.predict(
        "Will the Fed cut rates at the March meeting?",
        {**finance_bundle.features, "market_prob": 0.45},
        finance_bundle.metadata,
    )

    politics_bundle = PoliticsDomainAdapter.from_fixtures().build_bundle()
    politics_model = build_default_politics_model()
    candidate_a_prediction = politics_model.predict(
        "Will candidate a win the election?",
        {**politics_bundle.features, "market_prob": 0.45},
        politics_bundle.metadata,
    )
    candidate_b_prediction = politics_model.predict(
        "Will candidate b win the election?",
        {**politics_bundle.features, "market_prob": 0.45},
        politics_bundle.metadata,
    )

    assert hold_prediction.probability > cut_prediction.probability
    assert candidate_a_prediction.probability > candidate_b_prediction.probability


def test_default_domain_models_are_deterministic_and_bundle_compatible() -> None:
    """Default models should produce stable predictions on fixture bundles."""

    for bundle, model in (
        (
            FinanceDomainAdapter.from_fixtures().build_bundle(),
            build_default_finance_model(),
        ),
        (
            WeatherDomainAdapter.from_fixtures().build_bundle(),
            build_default_weather_model(),
        ),
        (
            PoliticsDomainAdapter.from_fixtures().build_bundle(),
            build_default_politics_model(),
        ),
    ):
        first = model.predict(
            "Will this market resolve YES?",
            {**bundle.features, "market_prob": 0.40},
            bundle.metadata,
        )
        second = model.predict(
            "Will this market resolve YES?",
            {**bundle.features, "market_prob": 0.40},
            bundle.metadata,
        )

        assert first.probability == second.probability
        assert first.confidence == second.confidence
        assert first.metadata["model"].endswith("_question_conditioned")


def test_offline_domain_datasets_include_train_calibration_and_evaluation_splits() -> None:
    """Phase 4 datasets should expose all offline held-out splits."""

    for dataset in (finance_dataset(), weather_dataset(), politics_dataset()):
        counts = dataset.split_counts()

        assert dataset.name.endswith("_domain_examples")
        assert dataset.version == "v1"
        assert dataset.domain in {"finance", "weather", "politics"}
        assert counts["train"] >= 5
        assert counts["calibration"] >= 2
        assert counts["evaluation"] >= 2


def test_default_domain_models_are_calibrated_on_held_out_examples() -> None:
    """Default models should use held-out calibration examples, not just train fits."""

    cases = (
        (
            build_default_finance_model(),
            finance_training_examples(),
            finance_calibration_examples(),
            finance_evaluation_examples(),
            "finance_test",
        ),
        (
            build_default_weather_model(),
            weather_training_examples(),
            weather_calibration_examples(),
            weather_evaluation_examples(),
            "weather_test",
        ),
        (
            build_default_politics_model(),
            politics_training_examples(),
            politics_calibration_examples(),
            politics_evaluation_examples(),
            "politics_test",
        ),
    )

    for calibrated_model, training_examples, calibration_examples, evaluation_examples, name in cases:
        uncalibrated_model = QuestionConditionedLinearModel.fit(name, training_examples)
        summary = calibrated_model.training_summary

        assert summary["train_example_count"] == len(training_examples)
        assert summary["calibration_example_count"] == len(calibration_examples)
        assert summary["evaluation_example_count"] == len(evaluation_examples)
        assert (
            calibrated_model.calibration_scale != 1.0
            or calibrated_model.calibration_bias != 0.0
        )
        assert summary["calibration_brier_after"] <= summary["calibration_brier_before"] + 1e-9
        assert summary["calibration_log_loss_after"] <= summary["calibration_log_loss_before"] + 1e-9
        assert QuestionConditionedLinearModel.brier_score(
            calibrated_model,
            evaluation_examples,
        ) <= QuestionConditionedLinearModel.brier_score(
            uncalibrated_model,
            evaluation_examples,
        ) + 0.05


def test_default_domain_models_publish_dataset_report_cards() -> None:
    """Calibrated default models should expose dataset-aware report cards."""

    cases = (
        (build_default_finance_model(), finance_dataset()),
        (build_default_weather_model(), weather_dataset()),
        (build_default_politics_model(), politics_dataset()),
    )

    for model, dataset in cases:
        summary = model.training_summary
        report_card = summary["report_card"]
        split_summaries = {item["split"]: item for item in report_card["split_summaries"]}
        selection_features = report_card["selection_features"]

        assert summary["dataset_name"] == dataset.name
        assert summary["dataset_version"] == dataset.version
        assert summary["dataset_domain"] == dataset.domain
        assert summary["dataset_split_counts"] == dataset.split_counts()
        assert summary["dataset_coverage_score"] == report_card["coverage_score"]
        assert summary["held_out_calibration_stability"] == report_card["held_out_calibration_stability"]
        assert split_summaries.keys() == {"calibration", "evaluation", "train"}
        assert selection_features["coverage_score"] == report_card["coverage_score"]
        assert (
            selection_features["held_out_calibration_stability"]
            == report_card["held_out_calibration_stability"]
        )
        assert selection_features["calibration_improvement"] >= 0.0


def test_prediction_metadata_carries_phase5_dataset_identity_and_selection_features() -> None:
    """Predictions should surface dataset identity and report-card features."""

    bundle = FinanceDomainAdapter.from_fixtures().build_bundle()
    prediction = build_default_finance_model().predict(
        "Will the Fed hold rates at the March meeting?",
        {**bundle.features, "market_prob": 0.45},
        bundle.metadata,
    )

    report_card = prediction.metadata["report_card"]
    selection_features = prediction.metadata["selection_features"]

    assert prediction.metadata["dataset_name"] == "finance_domain_examples"
    assert prediction.metadata["dataset_version"] == "v1"
    assert prediction.metadata["dataset_domain"] == "finance"
    assert report_card["dataset_name"] == "finance_domain_examples"
    assert report_card["dataset_version"] == "v1"
    assert selection_features["coverage_score"] == report_card["coverage_score"]
    assert (
        selection_features["held_out_calibration_stability"]
        == report_card["held_out_calibration_stability"]
    )
