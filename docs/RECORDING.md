# Read-only Polymarket recording and replay

AutoPredict records public point-in-time evidence in
`autopredict.capture.v1`, then deterministically replays that evidence into the
supported `autopredict.dataset.v1` evaluation contract. Capture files are an
audit log; they are not passed directly to a forecast provider.

## Safety boundary

The recorder accepts a `PolymarketCaptureSource` with only four public-data
methods: Gamma market metadata, CLOB order books, public Data API trades, and
Gamma resolution reads. The included transport protocol can only express
`get_json`. It has no credential fields and no place-order, cancel-order,
position, or balance method. The default requests transport rejects non-HTTPS
or non-Polymarket hosts and sessions containing authentication headers.
It also disables ambient environment/netrc proxy discovery and rejects injected
sessions carrying auth handlers, cookies, client certificates, configured
proxies, session-level query parameters, credential-bearing headers, or enabled
`trust_env` behavior. Query keys are fail-closed: only the recorder's documented
public `token_id`, `market`, `limit`, and `offset` keys are allowed. Configured
and prepared headers are likewise limited to the harmless standard headers used
by Requests; every custom header name is rejected. The fully prepared URL and
headers are checked again before the request is sent.

The default endpoint families are:

- `https://gamma-api.polymarket.com` for event, market, and resolution metadata
- `https://clob.polymarket.com/book` for public YES-token order books
- `https://data-api.polymarket.com/trades` for public trades

Callers may use `RequestsPublicJSONTransport` or inject another GET-only
transport and UTC clock. An injected transport is a trusted boundary: the
caller is responsible for ensuring it remains credential-free and read-only.
Tests use local fakes; repository tests never perform network, credential, or
order actions.

## Capture contract

`write_capture` writes a JSON manifest and canonical `capture.jsonl`. Exact
record bytes are SHA-256 hashed, and an existing file is never overwritten with
different bytes. Payloads are canonicalized when received, so later mutation of
an upstream response object cannot alter the captured evidence.

Every envelope records the source endpoint, canonical request parameters,
record ID, capture ordering, optional source sequencing and source timestamp,
a snapshot join ID, and distinct UTC `requested_at`/`received_at` timestamps.
Those fields participate in the record ID. Its record types are:

- `event`
- `market_metadata`
- `order_book`
- `trade`
- `trade_page` (including the terminal empty/undersized page evidence)
- `resolution`
- `gap`

Resolution labels are separate from observations. A resolution is rejected if
it appears to have been received before its declared `resolved_at` time.
Sequence discontinuities, reconnects, and an exhausted pagination safety bound
produce explicit `gap` records, warnings, and `completeness: partial`.
Production REST responses do not expose a source sequence, so their manifest
uses `sequence_completeness: not_available_polling`; this must not be read as a
claim that no changes occurred between polls. When sequences are present, both
the writer and loader reject an undeclared discontinuity.

Gamma's numeric market ID, event ID, condition ID, and YES token ID are retained
as separate identities. CLOB `market` and `asset_id` and each Data API trade's
`conditionId` must match those Gamma identities. Trade reads paginate with
`limit` and `offset` until an undersized page proves exhaustion.

## Deterministic replay

```python
from autopredict.recording import PolymarketRecorder, replay_capture, write_capture

recorder = PolymarketRecorder(public_source)
recorder.capture_snapshot("numeric-gamma-market-id")
# Later, after the market has resolved:
recorder.capture_resolution("numeric-gamma-market-id")
capture_manifest = write_capture(recorder.bundle(), "artifacts/capture")
dataset_manifest = replay_capture(capture_manifest, "artifacts/dataset")
```

Snapshot capture never requests a resolution. Resolution capture is an explicit
later lifecycle step and verifies the preserved Gamma-to-event/condition/token
identity before appending the label. A persisted observation bundle can be
restored with `PolymarketRecorder.from_bundle(source, bundle)` so the two steps
can occur in different process lifetimes. Restore preserves the original venue,
warnings, and partial-completeness state; later successful reads can never
upgrade a previously partial artifact to complete. Restore accepts only the
exact contract values `complete` and `partial`; unknown or differently cased
values fail closed.

Replay joins only same-snapshot event, metadata, and book records. It derives the
observation time from the later of the Gamma metadata receive time and CLOB book
receive time, then adds the label from a separate captured resolution. The
output is validated by `load_dataset_v1` before replay returns.

Identical capture bytes produce identical dataset bytes. Missing books,
metadata, events, or resolutions fail replay. Captures with gaps still produce a
structurally inspectable canonical dataset, but retain `completeness: partial`;
the evaluator refuses to use it as performance evidence.

Capture and replay preflight and validate both output files, write them in a
temporary sibling directory, and publish the complete two-file artifact with a
single directory rename. Existing partial or conflicting output is rejected
without creating the missing companion file. Capture runs `load_capture` against
the exact temporary candidate before publication, so forged envelope IDs or
other internal integrity failures cannot be published. An already-existing
byte-identical destination is also loaded and integrity-validated before the
idempotent write returns.

The checked-in fixture at
`tests/fixtures/recording/polymarket-v1/manifest.json` is synthetic test data,
not historical performance evidence.
