# Configuration Files

This directory contains configuration files for AutoPredict trading experiments.

## Files

- `shadow_replay.yaml.example` - Durable credential-free shadow replay configuration
- `paper_trading.yaml` - Legacy experiment config retained for offline tests
- `live_trading.yaml.example` - Inactive reference config retained for safety-audit tests

## Usage

### Paper Trading (Safe)

Paper trading is completely safe - it simulates trading without risking real capital.

```bash
# Run credential-free shadow execution
cp configs/shadow_replay.yaml.example configs/my_shadow.yaml
autopredict shadow run --config configs/my_shadow.yaml
```

You can freely experiment with paper trading configurations.

### Live Trading (Disabled)

Live execution through supported commands is intentionally unavailable. The package
does not install an `autopredict-live` command, `autopredict trade-live` fails closed,
and direct invocation of `scripts/run_live.py` exits before loading credentials or
creating a venue adapter. Lower-level Python APIs remain for offline fake-adapter tests
only and are not safety-approved. Do not copy this reference file into an operational
config or provision trading credentials for AutoPredict.

## Important Notes

- Always start with paper trading to validate your strategy
- Use the read-only scanner or paper mode while live execution is disabled
- Keep all logs for post-trade analysis

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
  mode: paper  # live execution is disabled
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

Example for a non-secret data path:
```yaml
data:
  root: ${AUTOPREDICT_DATA_ROOT:./data}
```

## Safety Features

All configurations include multiple safety layers:

1. **Position Limits**: Max size per market
2. **Exposure Limits**: Total capital at risk
3. **Daily Loss Limits**: Stop trading if loss exceeds threshold
4. **Kill Switch**: Emergency stop at severe loss level
5. **Position Timeouts**: Force close stale positions

Treat these as simulation controls, not live-readiness evidence.
