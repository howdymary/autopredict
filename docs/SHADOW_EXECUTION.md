# Shadow Execution

AutoPredict shadow mode exercises the forecast, strategy, risk, order, fill, and
reconciliation path without possessing a venue-order capability. Live submission
remains disabled.

## Run a trusted capture

Copy `configs/shadow_replay.yaml.example`, point `capture_manifest` at a Packet 5
capture, then run:

```bash
autopredict shadow run --config /path/to/shadow.yaml
# compatibility entrypoint
autopredict-paper --config /path/to/shadow.yaml
```

The configuration rejects credential-shaped fields and environment substitution
before constructing the runtime. The replay feed accepts only the validated Packet 5
capture contract. A partial capture, explicit gap, reconnect, stale observation,
out-of-order event, integrity conflict, accounting conflict, or runtime error latches
a breaker and transactionally cancels all simulated open orders.

## Operator commands

```bash
autopredict shadow status --state /path/to/autopredict.db
autopredict shadow cancel-all --state /path/to/autopredict.db --reason "operator stop"
autopredict shadow reset --state /path/to/autopredict.db \
  --reason "feed and state reviewed" --freshness-seconds 30
```

Reset is explicit and fails unless every persisted feed cursor is fresh and durable
state reconciles. An active writer owns a renewable fencing token; another process
cannot mutate the database, and an expired writer remains fenced after takeover.

## Execution semantics

- Prices use nanos (`1e9` per unit); quantity and cash use micros (`1e6`). Decimal
  conversion uses round-half-even and SQLite never stores floating-point risk state.
- Market and crossing-limit orders walk only displayed opposing depth. Any remainder
  is canceled as IOC.
- Passive limits fill only from a later, stable-ID public trade. Displayed same-price
  size is consumed as queue-ahead first. There is no randomness or fabricated volume.
- Risk uses signed low/high inventory bounds including open-order reservations. Long
  exposure is `q*p`; short exposure is `abs(q)*(1-p)`, rounded conservatively upward.
  A valid reduce-only close bypasses ordinary caps but never feed or integrity gates.
- Decisions, intent IDs, fills, positions, breaker events, and cursors persist in
  SQLite v1 with WAL, `synchronous=FULL`, foreign keys, content hashes, and an
  authoritative state journal. Restart rebuilds projections and resumes incomplete
  deterministic application without invoking an already-approved provider again.

## Safety boundary

Shadow modules do not import `LiveTrader`, authenticated adapters, credentials,
balances, positions, or order-submission methods. Public polling accepts only a
credential-free Packet 5 recorder source; unsupported in-memory shortcuts fail closed.
`autopredict trade-live` and `scripts/run_live.py` remain disabled.
