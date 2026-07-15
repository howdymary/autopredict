# Forecast Providers

Forecast generation is separated from evaluation and trading decisions by the
`ForecastProvider` protocol. Providers receive an immutable `ForecastRequest`
containing only point-in-time observation fields. The request has no outcome,
resolution, label, or `fair_prob` field.

A successful provider returns a `ForecastResult` with:

- a finite probability and confidence in `[0, 1]`
- an aware UTC `as_of` exactly matching the observation boundary
- provider name, version, and deterministic configuration hash

`ForecastAbstention` represents an intentional no-forecast result with a reason.
It is not treated as a provider exception, and an all-abstention evaluation cannot
produce performance evidence. Exceptions become `ForecastProviderFailure`; bad
types, non-finite values, mismatched provenance, and stale or future timestamps
fail validation.

## Built-ins

`MarketBaselineProvider` returns the observed market probability and claims no
edge. `RecalibrationProvider` applies explicit, bounded log-odds scale and shift
parameters:

```bash
autopredict evaluate \
  --dataset /path/to/manifest.json \
  --provider market-recalibration \
  --recalibration-scale 1.1 \
  --recalibration-shift -0.1
```

Recalibration parameters must come from a separately fitted past window. Their
values are included in the provider configuration hash. Provider-aware reports
use `autopredict.evaluation.v2`; the version bump covers the added abstention,
confidence, as-of, request-count, and provider-provenance fields.

## User adapters

`CallableForecastProvider` wraps a callable with an explicit name, version, and
JSON configuration. The callable receives `ForecastRequest` directly; no opaque
model object is stored in dataset rows or snapshot features. Arbitrary user code
is intentionally not loadable by the CLI.
