# Configuration Files

This directory contains configuration files for AutoPredict trading experiments.

## Files

- `paper_trading.yaml` - Safe paper trading configuration (no real money)
- `live_trading.yaml.example` - Template for live trading (DANGER: real money)

## Usage

### Paper Trading (Safe)

Paper trading is completely safe - it simulates trading without risking real capital.

```bash
# Run paper trading
python scripts/run_paper.py --config configs/paper_trading.yaml
```

You can freely experiment with paper trading configurations.

### Live Trading (DANGER)

Live trading uses REAL MONEY and REAL APIs. Follow these steps carefully:

1. **Copy the template:**
   ```bash
   cp configs/live_trading.yaml.example configs/live_trading.yaml
   ```

2. **Set up environment variables:**
   ```bash
   # Add to your ~/.bashrc or ~/.zshrc
   export POLYMARKET_API_KEY="your-api-key-here"
   export POLYMARKET_API_SECRET="your-api-secret-here"

   # Or set for current session
   export POLYMARKET_API_KEY="..."
   export POLYMARKET_API_SECRET="..."
   ```

3. **Edit the configuration:**
   - Open `configs/live_trading.yaml`
   - Carefully review ALL risk limits
   - Start with SMALL limits (e.g., max_daily_loss: 10.0)
   - Adjust based on your risk tolerance

4. **Test in dry-run mode first:**
   ```bash
   python scripts/run_live.py --config configs/live_trading.yaml --dry-run
   ```

5. **Run live (requires confirmation):**
   ```bash
   python scripts/run_live.py --config configs/live_trading.yaml
   # You will be prompted to type "CONFIRM LIVE" to proceed
   ```

## Important Notes

- **NEVER** commit `live_trading.yaml` to git (it's in `.gitignore`)
- Always start with paper trading to validate your strategy
- Monitor live trading continuously
- Test the kill switch before going live
- Keep all logs for post-trade analysis
- Use testnet if available before production

## Configuration Structure

All configurations have the same structure:

```yaml
name: experiment_name
description: Human-readable description

strategy:
  # Trading strategy parameters
  min_edge: 0.05
  kelly_fraction: 0.25
  ...

risk:
  # Risk management limits
  max_position_per_market: 100.0
  max_daily_loss: 50.0
  kill_switch_threshold: -100.0
  ...

venue:
  # Trading venue settings
  name: polymarket
  mode: paper  # or "live"
  api_key: ${POLYMARKET_API_KEY}
  ...

backtest:
  # Backtesting parameters
  initial_bankroll: 1000.0
  commission_rate: 0.01
  ...

logging:
  # Logging configuration
  log_dir: ./logs
  log_level: INFO
  ...
```

## Environment Variables

Configuration files support environment variable substitution:

- `${VAR_NAME}` - Required variable (error if not set)
- `${VAR_NAME:default}` - Optional with default value

Example:
```yaml
venue:
  api_key: ${POLYMARKET_API_KEY}
  base_url: ${API_BASE_URL:https://api.polymarket.com}
```

## Safety Features

All configurations include multiple safety layers:

1. **Position Limits**: Max size per market
2. **Exposure Limits**: Total capital at risk
3. **Daily Loss Limits**: Stop trading if loss exceeds threshold
4. **Kill Switch**: Emergency stop at severe loss level
5. **Position Timeouts**: Force close stale positions

Adjust these based on your risk tolerance and capital.
