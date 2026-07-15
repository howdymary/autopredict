"""Tests for the typed forecast-provider boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import timedelta
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from autopredict.evaluation import evaluate_provider, load_dataset_v1, report_json
from autopredict.forecasting import (
    CallableForecastProvider,
    ForecastAbstention,
    ForecastProviderFailure,
    ForecastRequest,
    ForecastResult,
    ForecastValidationError,
    MarketBaselineProvider,
    ObservationProvenance,
    RecalibrationProvider,
    invoke_provider,
)

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests/fixtures/datasets/resolved-v1/manifest.json"


def _request() -> ForecastRequest:
    observation = load_dataset_v1(MANIFEST).observations[0]
    return ForecastRequest.from_observation(observation)


def test_request_structurally_excludes_resolution_data() -> None:
    names = {item.name for item in fields(ForecastRequest)}
    assert {"outcome", "resolution", "resolved_at", "fair_prob"}.isdisjoint(names)
    request = _request()
    assert isinstance(request.provenance, ObservationProvenance)
    with pytest.raises(FrozenInstanceError):
        request.provenance.source = "mutated"


def test_request_rejects_untyped_or_label_bearing_provenance() -> None:
    request = _request()
    values = {item.name: getattr(request, item.name) for item in fields(ForecastRequest)}
    values["provenance"] = {"source": "fixture", "source_record_id": "1", "outcome": 1}

    with pytest.raises(ForecastValidationError, match="ObservationProvenance"):
        ForecastRequest(**values)

    values = {item.name: getattr(request, item.name) for item in fields(ForecastRequest)}
    values["order_book"] = {"outcome": 1}
    with pytest.raises(ForecastValidationError, match="ForecastOrderBook"):
        ForecastRequest(**values)

    class LabelBearingLevel:
        price = 0.4
        size = 1.0
        outcome = 1

    with pytest.raises(ForecastValidationError, match="ForecastPriceLevel"):
        request.order_book.__class__(
            bids=(LabelBearingLevel(),),
            asks=request.order_book.asks,
        )

    values = {item.name: getattr(request, item.name) for item in fields(ForecastRequest)}
    values["record_id"] = 123
    with pytest.raises(ForecastValidationError, match="non-empty string"):
        ForecastRequest(**values)


def test_baseline_and_recalibration_share_validated_protocol() -> None:
    request = _request()
    baseline = invoke_provider(MarketBaselineProvider(), request)
    recalibrated = invoke_provider(RecalibrationProvider(scale=1.1, shift=-0.1), request)

    assert isinstance(baseline, ForecastResult)
    assert baseline.probability == request.market_probability
    assert isinstance(recalibrated, ForecastResult)
    assert recalibrated.provenance.name == "market-recalibration"
    assert recalibrated.provenance.config_sha256 != baseline.provenance.config_sha256


@pytest.mark.parametrize("endpoint", [0.0, 1.0])
def test_identity_recalibration_preserves_probability_endpoints(endpoint: float) -> None:
    request = replace(_request(), market_probability=endpoint)
    result = invoke_provider(RecalibrationProvider(), request)

    assert isinstance(result, ForecastResult)
    assert result.probability == endpoint


@pytest.mark.parametrize(
    ("probability", "confidence", "message"),
    [
        (math.nan, 0.5, "probability"),
        (1.1, 0.5, "probability"),
        (0.5, math.inf, "confidence"),
        (0.5, -0.1, "confidence"),
    ],
)
def test_invalid_result_values_fail_closed(
    probability: float,
    confidence: float,
    message: str,
) -> None:
    provider = MarketBaselineProvider()
    with pytest.raises(ForecastValidationError, match=message):
        ForecastResult(
            probability=probability,
            confidence=confidence,
            as_of=_request().observed_at,
            provenance=provider.provenance,
        )


@pytest.mark.parametrize(("offset", "message"), [(-1, "stale"), (1, "future")])
def test_stale_and_future_outputs_fail_closed(offset: int, message: str) -> None:
    request = _request()
    baseline = MarketBaselineProvider()
    provider = CallableForecastProvider(
        callback=lambda item: ForecastResult(
            probability=item.market_probability,
            confidence=0.8,
            as_of=item.observed_at + timedelta(seconds=offset),
            provenance=baseline.provenance,
        ),
        name=baseline.provenance.name,
        version=baseline.provenance.version,
        config={"name": "market-baseline", "version": "1"},
    )

    with pytest.raises(ForecastValidationError, match=message):
        invoke_provider(provider, request)


def test_untyped_or_dynamic_provider_provenance_fails_closed() -> None:
    request = _request()

    class UntypedProvider:
        provenance = {"name": "unsafe"}

        def forecast(self, item):
            return object()

    with pytest.raises(ForecastValidationError, match="ProviderProvenance"):
        invoke_provider(UntypedProvider(), request)

    baseline = MarketBaselineProvider()

    class DynamicProvider:
        reads = 0

        @property
        def provenance(self):
            self.reads += 1
            return replace(baseline.provenance, version=str(self.reads))

        def forecast(self, item):
            return ForecastResult(
                probability=item.market_probability,
                confidence=1.0,
                as_of=item.observed_at,
                provenance=replace(baseline.provenance, version="1"),
            )

    with pytest.raises(ForecastValidationError, match="changed during invocation"):
        invoke_provider(DynamicProvider(), request)


def test_abstention_is_explicit_and_failure_is_separate() -> None:
    request = _request()
    abstaining = CallableForecastProvider(
        callback=lambda item: ForecastAbstention(
            reason="insufficient evidence",
            as_of=item.observed_at,
            provenance=abstaining.provenance,
        ),
        name="user-abstainer",
        version="1",
        config={"threshold": 0.9},
    )
    output = invoke_provider(abstaining, request)
    assert isinstance(output, ForecastAbstention)
    assert output.reason == "insufficient evidence"

    def broken(_: ForecastRequest):
        raise RuntimeError("model unavailable")

    failing = CallableForecastProvider(
        callback=broken,
        name="user-failure",
        version="1",
        config={},
    )
    with pytest.raises(ForecastProviderFailure, match="model unavailable"):
        invoke_provider(failing, request)


def test_callable_config_is_strict_json_and_deeply_immutable() -> None:
    original = {"nested": {"values": [{"threshold": 1}]}}
    provider = CallableForecastProvider(
        callback=MarketBaselineProvider().forecast,
        name="user-config",
        version="1",
        config=original,
    )
    original["nested"]["values"][0]["threshold"] = 2

    assert provider.config["nested"]["values"][0]["threshold"] == 1
    with pytest.raises(TypeError):
        provider.config["nested"]["values"][0]["threshold"] = 3

    with pytest.raises(ForecastValidationError, match="strict JSON"):
        CallableForecastProvider(
            callback=MarketBaselineProvider().forecast,
            name="tuple-config",
            version="1",
            config={"nested": ({"threshold": 1},)},
        )
    with pytest.raises(ForecastValidationError, match="keys must be strings"):
        CallableForecastProvider(
            callback=MarketBaselineProvider().forecast,
            name="key-config",
            version="1",
            config={1: "ambiguous"},
        )


def test_typed_provider_report_is_deterministic_and_paired() -> None:
    dataset = load_dataset_v1(MANIFEST)
    provider = RecalibrationProvider(scale=1.1, shift=-0.1)
    first = evaluate_provider(dataset, provider)
    second = evaluate_provider(dataset, provider)

    assert report_json(first) == report_json(second)
    assert first["provider"] == provider.provenance.to_dict()
    assert first["counts"]["requests"] == first["counts"]["forecasts"] == 2
    assert all(row["provider_as_of"] == row["observed_at"] for row in first["rows"])
    assert any(row["candidate_probability"] != row["market_probability"] for row in first["rows"])
    assert first["candidate"] != first["baseline"]


def test_all_abstentions_cannot_produce_performance_evidence() -> None:
    dataset = load_dataset_v1(MANIFEST)
    holder = {}

    def abstain(request: ForecastRequest) -> ForecastAbstention:
        return ForecastAbstention(
            reason="no forecast",
            as_of=request.observed_at,
            provenance=holder["provider"].provenance,
        )

    provider = CallableForecastProvider(
        callback=abstain,
        name="all-abstain",
        version="1",
        config={},
    )
    holder["provider"] = provider
    with pytest.raises(ValueError, match="non-abstained forecast"):
        evaluate_provider(dataset, provider)


def test_cli_recalibration_provider_is_deterministic(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "autopredict.cli",
        "evaluate",
        "--dataset",
        str(MANIFEST),
        "--provider",
        "market-recalibration",
        "--recalibration-scale",
        "1.1",
        "--recalibration-shift",
        "-0.1",
    ]
    first = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    second = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)

    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["provider"]["name"] == "market-recalibration"
