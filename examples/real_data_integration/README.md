# Real Data Integration Example

This example shows how to integrate AutoPredict with real prediction market data.

## Adapter Pattern

AutoPredict uses an **adapter pattern** to connect to different data sources:

1. **Market Data Adapter**: Fetches market snapshots (prices, order books, etc.)
2. **Order Execution Adapter**: Submits orders to the real market

## Example Implementations

### Polymarket Adapter (Simulated)

This example shows the structure for a Polymarket integration. The actual API calls are simulated.

**Key Components**:
- `PolymarketDataAdapter`: Fetches market data
- `PolymarketExecutionAdapter`: Submits orders
- Data transformation from Polymarket format to AutoPredict format

### CSV Data Adapter

For backtesting on historical data from CSV files.

**Key Components**:
- `CSVDataAdapter`: Reads historical market snapshots from CSV
- Converts CSV rows to AutoPredict's MarketState format

## Running the Examples

### CSV Backtest
```bash
cd "/Users/howdymary/Documents/New project/autopredict"
python3 examples/real_data_integration/run_csv_backtest.py
```

### Polymarket Simulation
```bash
cd "/Users/howdymary/Documents/New project/autopredict"
python3 examples/real_data_integration/run_polymarket_sim.py
```

## Implementing Your Own Adapter

### Step 1: Define Data Adapter Interface

```python
from abc import ABC, abstractmethod
from autopredict.agent import MarketState

class MarketDataAdapter(ABC):
    @abstractmethod
    def fetch_markets(self) -> list[MarketState]:
        """Fetch current market snapshots."""
        pass
```

### Step 2: Implement for Your Platform

```python
class MyPlatformAdapter(MarketDataAdapter):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch_markets(self) -> list[MarketState]:
        # Call your platform's API
        raw_data = requests.get(
            "https://api.myplatform.com/markets",
            headers={"Authorization": f"Bearer {self.api_key}"}
        )

        # Transform to AutoPredict format
        markets = []
        for item in raw_data.json():
            markets.append(
                MarketState(
                    market_id=item['id'],
                    market_prob=item['current_price'],
                    fair_prob=self.calculate_fair_prob(item),
                    time_to_expiry_hours=item['time_remaining'],
                    order_book=self.transform_order_book(item['book']),
                    metadata={"category": item['category']}
                )
            )
        return markets
```

### Step 3: Run Backtest with Adapter

```python
from autopredict.run_experiment import run_backtest

adapter = MyPlatformAdapter(api_key="...")
markets = adapter.fetch_markets()

# Convert to JSON for run_backtest
import json
with open("temp_dataset.json", "w") as f:
    json.dump([m.__dict__ for m in markets], f)

metrics = run_backtest(
    config_path="strategy_configs/baseline.json",
    dataset_path="temp_dataset.json",
    starting_bankroll=1000.0
)
```

## Production Deployment Considerations

1. **Rate Limiting**: Respect API rate limits
2. **Error Handling**: Handle network failures, invalid data
3. **State Persistence**: Save agent state between runs
4. **Monitoring**: Log all trades and performance
5. **Safety Checks**: Validate orders before submission
6. **Capital Management**: Track actual bankroll, not simulated

See `production_deployment.md` for detailed guide.
