"""Generic question-conditioned models for domain-specialist strategies."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

TOKEN_RE = re.compile(r"[a-z0-9]+")
EPSILON = 1e-9


@dataclass(frozen=True)
class QuestionConditionedExample:
    """One supervised training example for a domain question model."""

    question: str
    outcome: int
    features: dict[str, Any]
    labels: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("question cannot be empty")
        if self.outcome not in (0, 1):
            raise ValueError("outcome must be 0 or 1")
        if self.weight <= 0:
            raise ValueError("weight must be positive")


@dataclass(frozen=True)
class QuestionConditionedDataset:
    """Offline train/calibration/evaluation examples for one domain."""

    name: str
    version: str
    domain: str
    examples_by_split: dict[str, tuple[QuestionConditionedExample, ...]]

    def split_examples(self, split: str) -> tuple[QuestionConditionedExample, ...]:
        """Return examples for one named split."""

        return self.examples_by_split.get(split, ())

    def split_counts(self) -> dict[str, int]:
        """Return per-split counts."""

        return {
            split: len(examples)
            for split, examples in self.examples_by_split.items()
        }

    def split_summary(self, split: str) -> "DatasetSplitSummary":
        """Return coverage summary for one split."""

        return DatasetSplitSummary.from_examples(split, self.split_examples(split))

    def split_summaries(self) -> tuple["DatasetSplitSummary", ...]:
        """Return stable split summaries for this dataset."""

        return tuple(
            self.split_summary(split)
            for split in sorted(self.examples_by_split)
        )

    @property
    def coverage_score(self) -> float:
        """Return the average split coverage score for this dataset."""

        summaries = self.split_summaries()
        if not summaries:
            return 0.0
        return _mean([summary.coverage_score for summary in summaries])


@dataclass(frozen=True)
class DatasetSplitSummary:
    """Coverage summary for one dataset split."""

    split: str
    example_count: int
    positive_rate: float
    market_family_count: int
    regime_count: int
    unique_question_count: int

    @classmethod
    def from_examples(
        cls,
        split: str,
        examples: Sequence[QuestionConditionedExample],
    ) -> "DatasetSplitSummary":
        """Build a split summary from examples."""

        families = {
            str(example.labels.get("market_family", "unknown"))
            for example in examples
        }
        regimes = {
            str(example.labels.get("regime", "unknown"))
            for example in examples
        }
        questions = {example.question for example in examples}
        outcomes = [float(example.outcome) for example in examples]
        return cls(
            split=split,
            example_count=len(examples),
            positive_rate=_mean(outcomes),
            market_family_count=len(families),
            regime_count=len(regimes),
            unique_question_count=len(questions),
        )

    @property
    def coverage_score(self) -> float:
        """Return a simple normalized coverage score for the split."""

        if self.example_count == 0:
            return 0.0
        family_component = min(1.0, self.market_family_count / 3.0)
        regime_component = min(1.0, self.regime_count / 3.0)
        question_component = min(1.0, self.unique_question_count / 6.0)
        return (family_component + regime_component + question_component) / 3.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the split summary to a dictionary."""

        return {
            "split": self.split,
            "example_count": self.example_count,
            "positive_rate": self.positive_rate,
            "market_family_count": self.market_family_count,
            "regime_count": self.regime_count,
            "unique_question_count": self.unique_question_count,
            "coverage_score": self.coverage_score,
        }


@dataclass(frozen=True)
class DomainModelReportCard:
    """Model card focused on dataset coverage and held-out calibration stability."""

    domain: str
    model_name: str
    dataset_name: str
    dataset_version: str
    split_summaries: tuple[DatasetSplitSummary, ...]
    train_brier_score: float
    calibration_brier_score: float
    evaluation_brier_score: float
    calibration_log_loss: float
    evaluation_log_loss: float
    calibration_improvement: float
    held_out_calibration_stability: float

    @property
    def coverage_score(self) -> float:
        """Return the average coverage score across all splits."""

        if not self.split_summaries:
            return 0.0
        return _mean([summary.coverage_score for summary in self.split_summaries])

    @property
    def selection_features(self) -> dict[str, float]:
        """Return a compact numeric surface for selection-time comparisons."""

        return {
            "coverage_score": self.coverage_score,
            "calibration_improvement": self.calibration_improvement,
            "held_out_calibration_stability": self.held_out_calibration_stability,
            "evaluation_brier_score": self.evaluation_brier_score,
            "evaluation_log_loss": self.evaluation_log_loss,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report card to a dictionary."""

        return {
            "domain": self.domain,
            "model_name": self.model_name,
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "split_summaries": [summary.to_dict() for summary in self.split_summaries],
            "coverage_score": self.coverage_score,
            "train_brier_score": self.train_brier_score,
            "calibration_brier_score": self.calibration_brier_score,
            "evaluation_brier_score": self.evaluation_brier_score,
            "calibration_log_loss": self.calibration_log_loss,
            "evaluation_log_loss": self.evaluation_log_loss,
            "calibration_improvement": self.calibration_improvement,
            "held_out_calibration_stability": self.held_out_calibration_stability,
            "selection_features": self.selection_features,
        }


@dataclass(frozen=True)
class ModelPrediction:
    """Probability prediction plus confidence and explanation metadata."""

    probability: float
    confidence: float
    rationale: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.probability <= 1.0):
            raise ValueError("probability must be in [0, 1]")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")


@dataclass(frozen=True)
class QuestionConditionedLinearModel:
    """Small deterministic logistic model over numeric features and question tokens."""

    name: str
    bias: float
    feature_weights: dict[str, float]
    token_weights: dict[str, float]
    feature_means: dict[str, float]
    feature_scales: dict[str, float]
    calibration_scale: float = 1.0
    calibration_bias: float = 0.0
    training_summary: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def fit(
        cls,
        name: str,
        examples: Sequence[QuestionConditionedExample],
        *,
        learning_rate: float = 0.15,
        epochs: int = 250,
        l2: float = 0.01,
    ) -> "QuestionConditionedLinearModel":
        """Fit a deterministic logistic model from supervised examples."""

        if not examples:
            raise ValueError("cannot fit model without examples")

        feature_names = _feature_names(examples)
        token_names = _token_names(examples)
        feature_means = {
            feature: _mean([_numeric_feature(example.features, feature) for example in examples])
            for feature in feature_names
        }
        feature_scales = {
            feature: _feature_scale(
                [_numeric_feature(example.features, feature) for example in examples],
                feature_means[feature],
            )
            for feature in feature_names
        }
        outcomes = [float(example.outcome) for example in examples]
        base_rate = min(max(_mean(outcomes), EPSILON), 1.0 - EPSILON)
        bias = math.log(base_rate / (1.0 - base_rate))
        feature_weights = {feature: 0.0 for feature in feature_names}
        token_weights = {token: 0.0 for token in token_names}

        for _ in range(epochs):
            for example in examples:
                score = bias
                standardized_features = {
                    feature: _standardize(
                        _numeric_feature(example.features, feature),
                        feature_means[feature],
                        feature_scales[feature],
                    )
                    for feature in feature_names
                }
                active_tokens = _tokenize_example(example.question, example.labels)
                for feature, value in standardized_features.items():
                    score += feature_weights[feature] * value
                for token in active_tokens:
                    score += token_weights.get(token, 0.0)

                probability = _sigmoid(score)
                error = (probability - float(example.outcome)) * example.weight
                bias -= learning_rate * error
                for feature, value in standardized_features.items():
                    feature_weights[feature] -= learning_rate * (
                        error * value + l2 * feature_weights[feature]
                    )
                for token in active_tokens:
                    token_weights[token] -= learning_rate * (
                        error + l2 * token_weights[token]
                    )

        return cls(
            name=name,
            bias=bias,
            feature_weights=feature_weights,
            token_weights=token_weights,
            feature_means=feature_means,
            feature_scales=feature_scales,
        )

    @classmethod
    def fit_with_calibration(
        cls,
        name: str,
        training_examples: Sequence[QuestionConditionedExample],
        calibration_examples: Sequence[QuestionConditionedExample],
        *,
        evaluation_examples: Sequence[QuestionConditionedExample] = (),
        dataset: QuestionConditionedDataset | None = None,
        learning_rate: float = 0.15,
        epochs: int = 250,
        l2: float = 0.01,
        calibration_learning_rate: float = 0.10,
        calibration_epochs: int = 300,
    ) -> "QuestionConditionedLinearModel":
        """Fit a model on training examples and calibrate on held-out examples."""

        base_model = cls.fit(
            name,
            training_examples,
            learning_rate=learning_rate,
            epochs=epochs,
            l2=l2,
        )
        calibration_bias, calibration_scale = _fit_sigmoid_calibrator(
            base_model,
            calibration_examples,
            learning_rate=calibration_learning_rate,
            epochs=calibration_epochs,
        )
        calibration_split = tuple(calibration_examples)
        evaluation_split = tuple(evaluation_examples)
        training_split = tuple(training_examples)
        train_brier_score = cls.brier_score(base_model, training_split)
        calibration_brier_before = cls.brier_score(base_model, calibration_split)
        calibration_brier_after = cls.brier_score(
            base_model,
            calibration_split,
            calibration_bias=calibration_bias,
            calibration_scale=calibration_scale,
        )
        calibration_log_loss_before = cls.log_loss(base_model, calibration_split)
        calibration_log_loss_after = cls.log_loss(
            base_model,
            calibration_split,
            calibration_bias=calibration_bias,
            calibration_scale=calibration_scale,
        )
        evaluation_brier_after = cls.brier_score(
            base_model,
            evaluation_split,
            calibration_bias=calibration_bias,
            calibration_scale=calibration_scale,
        )
        evaluation_log_loss_after = cls.log_loss(
            base_model,
            evaluation_split,
            calibration_bias=calibration_bias,
            calibration_scale=calibration_scale,
        )
        summary = {
            "train_example_count": len(training_split),
            "calibration_example_count": len(calibration_split),
            "evaluation_example_count": len(evaluation_split),
            "train_brier_score": train_brier_score,
            "calibration_brier_before": calibration_brier_before,
            "calibration_brier_after": calibration_brier_after,
            "calibration_log_loss_before": calibration_log_loss_before,
            "calibration_log_loss_after": calibration_log_loss_after,
            "evaluation_brier_after": evaluation_brier_after,
            "evaluation_log_loss_after": evaluation_log_loss_after,
        }
        if dataset is not None:
            report_card = build_domain_report_card(
                dataset=dataset,
                model_name=name,
                train_brier_score=train_brier_score,
                calibration_brier_score=calibration_brier_after,
                evaluation_brier_score=evaluation_brier_after,
                calibration_log_loss=calibration_log_loss_after,
                evaluation_log_loss=evaluation_log_loss_after,
                calibration_improvement=calibration_brier_before - calibration_brier_after,
            )
            summary.update(
                {
                    "dataset_name": dataset.name,
                    "dataset_version": dataset.version,
                    "dataset_domain": dataset.domain,
                    "dataset_split_counts": dataset.split_counts(),
                    "dataset_coverage_score": dataset.coverage_score,
                    "held_out_calibration_stability": report_card.held_out_calibration_stability,
                    "selection_features": dict(report_card.selection_features),
                    "report_card": report_card.to_dict(),
                }
            )
        return cls(
            name=base_model.name,
            bias=base_model.bias,
            feature_weights=base_model.feature_weights,
            token_weights=base_model.token_weights,
            feature_means=base_model.feature_means,
            feature_scales=base_model.feature_scales,
            calibration_scale=calibration_scale,
            calibration_bias=calibration_bias,
            training_summary=summary,
        )

    def predict(
        self,
        question: str,
        features: Mapping[str, Any],
        labels: Mapping[str, Any] | None = None,
    ) -> ModelPrediction:
        """Predict one question-conditioned probability."""

        raw_score = self.bias
        contributions: dict[str, float] = {}
        for feature, weight in self.feature_weights.items():
            raw_value = _numeric_feature(features, feature)
            standardized = _standardize(
                raw_value,
                self.feature_means[feature],
                self.feature_scales[feature],
            )
            contribution = weight * standardized
            raw_score += contribution
            contributions[f"feature:{feature}"] = contribution

        active_tokens = _tokenize_example(question, labels or {})
        for token in active_tokens:
            if token not in self.token_weights:
                continue
            contribution = self.token_weights[token]
            raw_score += contribution
            contributions[f"token:{token}"] = contribution

        calibrated_score = self.calibration_bias + self.calibration_scale * raw_score
        probability = _sigmoid(calibrated_score)
        confidence = _confidence(probability, active_tokens, contributions)
        top_contributors = sorted(
            contributions.items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:4]
        rationale_terms = [name.removeprefix("token:").removeprefix("feature:") for name, _ in top_contributors]
        rationale = (
            "Question-conditioned linear model using "
            + ", ".join(rationale_terms)
            if rationale_terms
            else "Question-conditioned linear model using domain features"
        )
        return ModelPrediction(
            probability=probability,
            confidence=confidence,
            rationale=rationale,
            metadata={
                "model": self.name,
                "dataset_name": self.training_summary.get("dataset_name"),
                "dataset_version": self.training_summary.get("dataset_version"),
                "dataset_domain": self.training_summary.get("dataset_domain"),
                "score": calibrated_score,
                "raw_score": raw_score,
                "calibration_scale": self.calibration_scale,
                "calibration_bias": self.calibration_bias,
                "active_tokens": tuple(sorted(active_tokens)),
                "top_contributors": tuple(top_contributors),
                "selection_features": dict(self.training_summary.get("selection_features", {})),
                "training_summary": dict(self.training_summary),
                "report_card": dict(self.training_summary.get("report_card", {})),
            },
        )

    @staticmethod
    def brier_score(
        model: "QuestionConditionedLinearModel",
        examples: Sequence[QuestionConditionedExample],
        *,
        calibration_bias: float | None = None,
        calibration_scale: float | None = None,
    ) -> float:
        """Return mean Brier score on a set of examples."""

        if not examples:
            return 0.0
        errors = []
        for example in examples:
            probability = model._predict_probability(
                example.question,
                example.features,
                example.labels,
                calibration_bias=calibration_bias,
                calibration_scale=calibration_scale,
            )
            errors.append((probability - float(example.outcome)) ** 2)
        return _mean(errors)

    @staticmethod
    def log_loss(
        model: "QuestionConditionedLinearModel",
        examples: Sequence[QuestionConditionedExample],
        *,
        calibration_bias: float | None = None,
        calibration_scale: float | None = None,
    ) -> float:
        """Return mean log loss on a set of examples."""

        if not examples:
            return 0.0
        losses = []
        for example in examples:
            probability = model._predict_probability(
                example.question,
                example.features,
                example.labels,
                calibration_bias=calibration_bias,
                calibration_scale=calibration_scale,
            )
            clipped = min(max(probability, 1e-12), 1.0 - 1e-12)
            if example.outcome == 1:
                losses.append(-math.log(clipped))
            else:
                losses.append(-math.log(1.0 - clipped))
        return _mean(losses)

    def _predict_probability(
        self,
        question: str,
        features: Mapping[str, Any],
        labels: Mapping[str, Any],
        *,
        calibration_bias: float | None = None,
        calibration_scale: float | None = None,
    ) -> float:
        """Return a probability without constructing a full prediction object."""

        raw_score = self._raw_score(question, features, labels)
        calibrated = (
            (self.calibration_bias if calibration_bias is None else calibration_bias)
            + (self.calibration_scale if calibration_scale is None else calibration_scale) * raw_score
        )
        return _sigmoid(calibrated)

    def _raw_score(
        self,
        question: str,
        features: Mapping[str, Any],
        labels: Mapping[str, Any],
    ) -> float:
        """Return the uncalibrated model score."""

        raw_score = self.bias
        for feature, weight in self.feature_weights.items():
            raw_value = _numeric_feature(features, feature)
            standardized = _standardize(
                raw_value,
                self.feature_means[feature],
                self.feature_scales[feature],
            )
            raw_score += weight * standardized
        for token in _tokenize_example(question, labels):
            raw_score += self.token_weights.get(token, 0.0)
        return raw_score


def load_question_conditioned_dataset(dataset_filename: str) -> QuestionConditionedDataset:
    """Load one offline domain dataset from package data."""

    path = _dataset_root() / dataset_filename
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    grouped: dict[str, list[QuestionConditionedExample]] = {}
    for item in payload["examples"]:
        split = str(item["split"])
        grouped.setdefault(split, []).append(
            QuestionConditionedExample(
                question=str(item["question"]),
                outcome=int(item["outcome"]),
                features=dict(item.get("features", {})),
                labels=dict(item.get("labels", {})),
                weight=float(item.get("weight", 1.0)),
            )
        )

    return QuestionConditionedDataset(
        name=str(payload["name"]),
        version=str(payload.get("version", "v1")),
        domain=str(payload.get("domain", "unknown")),
        examples_by_split={
            split: tuple(examples)
            for split, examples in grouped.items()
        },
    )


def build_domain_report_card(
    *,
    dataset: QuestionConditionedDataset,
    model_name: str,
    train_brier_score: float,
    calibration_brier_score: float,
    evaluation_brier_score: float,
    calibration_log_loss: float,
    evaluation_log_loss: float,
    calibration_improvement: float,
) -> DomainModelReportCard:
    """Build a model report card from dataset coverage and held-out metrics."""

    held_out_calibration_stability = abs(calibration_brier_score - evaluation_brier_score) + abs(
        calibration_log_loss - evaluation_log_loss
    )
    return DomainModelReportCard(
        domain=dataset.domain,
        model_name=model_name,
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        split_summaries=dataset.split_summaries(),
        train_brier_score=train_brier_score,
        calibration_brier_score=calibration_brier_score,
        evaluation_brier_score=evaluation_brier_score,
        calibration_log_loss=calibration_log_loss,
        evaluation_log_loss=evaluation_log_loss,
        calibration_improvement=calibration_improvement,
        held_out_calibration_stability=held_out_calibration_stability,
    )


def _token_names(examples: Sequence[QuestionConditionedExample]) -> tuple[str, ...]:
    names: set[str] = set()
    for example in examples:
        names.update(_tokenize_example(example.question, example.labels))
    return tuple(sorted(names))


def _feature_names(examples: Sequence[QuestionConditionedExample]) -> tuple[str, ...]:
    names: set[str] = set()
    for example in examples:
        for key, value in example.features.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                names.add(key)
    return tuple(sorted(names))


def _numeric_feature(features: Mapping[str, Any], key: str) -> float:
    value = features.get(key, 0.0)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _tokenize_example(question: str, labels: Mapping[str, Any]) -> tuple[str, ...]:
    tokens = set(TOKEN_RE.findall(question.lower()))
    for key, value in sorted(labels.items()):
        tokens.add(f"{key}:{str(value).lower()}")
    return tuple(sorted(tokens))


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _feature_scale(values: Sequence[float], mean: float) -> float:
    if not values:
        return 1.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return max(math.sqrt(variance), 1.0)


def _standardize(value: float, mean: float, scale: float) -> float:
    return (value - mean) / max(scale, EPSILON)


def _sigmoid(score: float) -> float:
    if score >= 0:
        exp_term = math.exp(-score)
        return 1.0 / (1.0 + exp_term)
    exp_term = math.exp(score)
    return exp_term / (1.0 + exp_term)


def _confidence(
    probability: float,
    active_tokens: Sequence[str],
    contributions: Mapping[str, float],
) -> float:
    margin = abs(probability - 0.5) * 2.0
    support = min(1.0, (len(active_tokens) + len(contributions)) / 10.0)
    return min(0.95, 0.5 + 0.3 * margin + 0.15 * support)


def _fit_sigmoid_calibrator(
    model: QuestionConditionedLinearModel,
    examples: Sequence[QuestionConditionedExample],
    *,
    learning_rate: float,
    epochs: int,
) -> tuple[float, float]:
    """Fit a monotonic sigmoid calibrator on held-out examples."""

    if not examples:
        return 0.0, 1.0

    bias = 0.0
    scale = 1.0
    raw_scores = [
        model._raw_score(example.question, example.features, example.labels)
        for example in examples
    ]
    outcomes = [float(example.outcome) for example in examples]
    for _ in range(epochs):
        for raw_score, outcome in zip(raw_scores, outcomes):
            calibrated = bias + scale * raw_score
            probability = _sigmoid(calibrated)
            error = probability - outcome
            bias -= learning_rate * error
            scale -= learning_rate * error * raw_score
            scale = max(scale, 0.1)
    return bias, scale


def _dataset_root() -> Path:
    return Path(__file__).resolve().parents[1] / "_defaults" / "datasets"
