# Real Data Integration Example

This folder shows two honest integration paths:

- read historical data from an explicit CSV file
- inspect live public Polymarket data through the read-only scanner

No example in this folder fabricates live API responses or fair probabilities.

## CSV Data

```bash
python examples/real_data_integration/adapters.py --csv /path/to/markets.csv
```

The CSV adapter expects observed market columns such as `market_id`, `market_prob`, `fair_prob`, `time_to_expiry_hours`, and order-book levels like `bid1_price`, `bid1_size`, `ask1_price`, `ask1_size`.

## Live Public Scan

```bash
python examples/real_data_integration/adapters.py --live --limit 5
```

This uses `autopredict.live_scan.LivePolymarketScanner`, which reports observed Gamma/CLOB data and never submits orders.

## Production Notes

- Keep venue reads, forecast generation, and order execution as separate adapters.
- Treat `fair_prob` as an external forecast input with its own validation and provenance.
- Store the source dataset hash for any backtest or self-improvement run.
- Use dry-run or paper trading before enabling live order execution.
