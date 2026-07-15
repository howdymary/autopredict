# Canonical Dataset Contract

AutoPredict's supported evaluation input is `autopredict.dataset.v1`: one JSON
manifest plus one immutable canonical-JSONL record file. It contains no model
forecast column and never substitutes missing values.

## Manifest

The manifest contains exactly:

- `schema_version`: `autopredict.dataset.v1`
- `dataset_id` and `venue`
- `records_file`, `records_sha256`, and `record_count`
- UTC `capture_started_at` and `capture_ended_at`
- non-empty `source_endpoints`
- `completeness`: `complete` or `partial`
- `warnings`: explicit capture or provenance warnings

`records_file` must be beside the manifest. Its SHA-256 is calculated over exact
bytes. Partial datasets may validate structurally but cannot be used as performance
evidence.

## Records

Each line is canonical JSON: UTF-8, sorted object keys, compact separators, and one
newline. Two record types keep features and labels separate.

`market_observation` contains:

- stable `record_id`, independent `event_id`, and `market_id`
- `question` and `category`
- aware UTC `observed_at` and `expiry`
- finite `market_probability` in `[0, 1]`
- non-empty bids in descending order and asks in ascending order
- `provenance` with `source` and `source_record_id`

It cannot contain `outcome`, `resolved_at`, `fair_prob`, or arbitrary future fields.

`resolution` contains:

- its own `record_id`
- matching `event_id` and `market_id`
- aware UTC `resolved_at`
- binary `outcome`
- the same explicit provenance shape

One resolution is required per market identity and must occur after every joined
observation. Multiple observations may share an event ID; statistical code must
count independent event IDs rather than treating snapshots as independent outcomes.

## Commands

```bash
autopredict validate --dataset /path/to/manifest.json
autopredict evaluate \
  --dataset /path/to/manifest.json \
  --provider market-baseline \
  --output /path/to/report.json
```

The baseline provider returns the recorded point-in-time market probability. It
therefore has zero claimed skill over itself. A later forecast-provider packet will
add user models without changing this dataset or report envelope.

The repository fixture under `tests/fixtures/` exists only for deterministic tests;
it is not bundled historical evidence or a runtime fallback.
