# AutoPredict Deployment Guide

Guide for paper/shadow deployment and the current live-execution safety boundary.

> **Live execution through supported commands is disabled.** AutoPredict does not install an
> `autopredict-live` command, `autopredict trade-live` fails closed, and direct
> invocation of `scripts/run_live.py` exits before loading configuration or
> constructing a venue client. Lower-level live Python APIs remain for offline
> fake-adapter tests and are not safety-approved. The live runtime remains
> experimental pending the shadow-trading and safety gates in the active product plan.

## Table of Contents

1. [Overview](#overview)
2. [Paper Trading](#paper-trading)
3. [Live Trading](#live-trading)
4. [Configuration](#configuration)
5. [Safety Features](#safety-features)
6. [Monitoring](#monitoring)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

## Overview

AutoPredict currently exposes one executable deployment mode:

- **Paper Trading**: Simulated trading with no real money. Safe for development and testing.
- **Live Trading**: Disabled. Lower-level code is retained only for offline fake-adapter testing and future safety review.

### Quick Start

```bash
# Shadow execution (safe, from an installed package)
autopredict shadow run --config /path/to/shadow.yaml

# Live execution intentionally fails closed
autopredict trade-live
```

## Paper Trading

Shadow execution processes validated public captures without risking real capital. Use this to:

- Develop and test trading strategies
- Validate configuration settings
- Learn the system safely
- Backtest strategy performance

### Setup

1. **Use the provided configuration:**
   ```bash
   cp configs/shadow_replay.yaml.example configs/my_shadow.yaml
   autopredict-paper --config configs/my_shadow.yaml
   ```

2. **Or create your own:**
   ```bash
   cp configs/shadow_replay.yaml.example configs/my_shadow.yaml
   # Edit my_shadow.yaml
   autopredict shadow run --config configs/my_shadow.yaml
   ```

### Running Paper Trading

```bash
# Run a deterministic capture through durable shadow state
autopredict shadow run --config configs/my_shadow.yaml
```

### What Gets Simulated

- Displayed-depth and later-public-trade fills with no randomness
- Signed position, realized P&L, fee, and mark accounting
- Reservation-aware worst-case risk limits
- Durable decisions, intents, fills, cursors, and breaker state
- Restart reconciliation and deterministic state hashes

### What's Different from Live

- No credential, balance, position, cancel, or submission capability
- No probabilistic or fabricated fills
- No actual capital at risk

See [Shadow Execution](SHADOW_EXECUTION.md) for contracts, breaker semantics, and
operator commands.

## Live Trading

Neither supported command can be enabled by supplying configuration or credentials.
The following invocations both terminate without creating a client or adapter:

```bash
autopredict trade-live
python scripts/run_live.py --config configs/live_trading.yaml.example
```

Use `autopredict scan-live` for read-only public market inspection and
`autopredict-paper` for simulated execution. A future release must first provide
real shadow execution, durable state/reconciliation, direction-aware risk tests,
stale-feed and circuit-breaker coverage, and an explicit human safety review.

## Configuration

### Configuration Structure

All configs follow this structure:

```yaml
name: experiment_name
description: Human-readable description

strategy:
  # How to identify and size trades
  min_edge: 0.05                    # Minimum probability edge
  kelly_fraction: 0.25              # Position sizing (quarter-Kelly)
  max_position_pct: 0.02            # Max 2% of bankroll per trade
  aggressive_edge: 0.12             # Threshold for market orders
  ...

risk:
  # Risk management limits
  max_position_per_market: 100.0    # Per-market position cap
  max_total_exposure: 500.0         # Total exposure cap
  max_daily_loss: 50.0              # Daily loss limit
  kill_switch_threshold: -100.0     # Emergency stop threshold
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

### Environment Variables

Supported paper and read-only workflows do not require trading credentials. Do
not provision venue API keys for AutoPredict while live execution is disabled.

### Configuration Validation

The system validates configurations on load:

```python
from autopredict.config import load_config, validate_config

config = load_config("configs/my_config.yaml")
warnings = validate_config(config)

for warning in warnings:
    print(f"WARNING: {warning}")
```

## Safety Features

AutoPredict includes risk controls for simulation and future safety testing.
They are not evidence that live execution is approved or reachable.

### 1. Position Limits

**Per-Market Limit:**
```yaml
risk:
  max_position_per_market: 100.0
```

Prevents over-concentration in a single market.

**Total Exposure Limit:**
```yaml
risk:
  max_total_exposure: 500.0
```

Caps total capital at risk across all positions.

**Maximum Positions:**
```yaml
risk:
  max_positions: 20
```

Limits number of simultaneous open positions.

### 2. Loss Limits

**Daily Loss Limit:**
```yaml
risk:
  max_daily_loss: 50.0
```

Stops trading if daily losses exceed this amount. Resets at midnight.

### 3. Kill Switch

**Automatic Activation:**
```yaml
risk:
  kill_switch_threshold: -100.0    # Negative value
  enable_kill_switch: true         # Keep enabled in paper/shadow testing
```

Immediately halts all trading if daily P&L drops below threshold.

**Manual Activation:**
```python
from autopredict.live import RiskManager

risk_manager.manual_kill_switch("Market conditions deteriorating")
```

**Reset Kill Switch:**
```python
# Requires exact confirmation
risk_manager.reset_kill_switch("RESET KILL SWITCH")
```

### 4. Position Timeouts

```yaml
risk:
  position_timeout_hours: 168.0    # 1 week
```

Forces review of positions held longer than timeout. Prevents forgotten positions.

### 5. Pre-Trade Checks

Every order is checked before execution:

```python
result = risk_manager.check_order(order, current_price)

if result.passed:
    # Safe to simulate
    trader.place_order(order)
else:
    # Blocked by risk limits
    print(f"Order blocked: {result.reason}")
```

### 6. Mode Separation

Only the paper trader is a supported executable mode:

```python
# Paper trader - safe simulation
paper_trader = PaperTrader()
```

Lower-level live classes remain solely for offline fake-adapter tests and a
future independent safety review.

## Monitoring

### Log Files

All activity is logged to structured files:

```
logs/
├── trades.jsonl          # All trade executions
├── decisions.jsonl       # All trading decisions (including skips)
├── errors.log            # Errors and exceptions
├── performance.jsonl     # Periodic performance snapshots
└── monitor.log           # General system logs
```

### Structured Logging

All logs use JSON format for easy parsing:

**Trade Log:**
```json
{
  "timestamp": "2026-03-26T12:34:56",
  "market_id": "polymarket-election-2024",
  "side": "buy",
  "order_type": "limit",
  "size": 100.0,
  "price": 0.55,
  "commission": 1.0,
  "slippage_bps": 0.0,
  "execution_mode": "paper",
  "success": true
}
```

**Decision Log:**
```json
{
  "timestamp": "2026-03-26T12:34:56",
  "market_id": "polymarket-sports-2024",
  "decision": "skip",
  "reason": "Edge below minimum threshold",
  "edge": 0.03,
  "market_price": 0.50,
  "fair_price": 0.53
}
```

### Real-Time Monitoring

```python
from autopredict.live import Monitor

monitor = Monitor(config.logging)

# Get live metrics
metrics = monitor.get_live_metrics()
print(f"Trades: {metrics['trade_count']}")
print(f"Errors: {metrics['error_count']}")
```

### Performance Snapshots

Automatically logged at configured intervals:

```yaml
logging:
  performance_interval_minutes: 15.0    # Log every 15 minutes
```

## Troubleshooting

### Common Issues

**1. Live execution is disabled**

This is the expected fail-closed behavior. Use `autopredict scan-live` or
`autopredict shadow run`; configuration and credentials cannot override the gate.

**2. Kill switch activated unexpectedly**

```bash
# Check daily P&L in logs
tail logs/performance.jsonl

# If justified, reset after fixing issue:
# (in Python/interactive shell)
risk_manager.reset_kill_switch("RESET KILL SWITCH")
```

### Debugging

Enable verbose logging:

```bash
autopredict shadow status --state state/shadow/autopredict.db
```

Or in configuration:

```yaml
logging:
  log_level: DEBUG
```

## Best Practices

### Strategy Development

1. **Always start with paper trading**
   - Test thoroughly before risking real money
   - Run for extended periods to see edge cases
   - Analyze logs for unexpected behavior

2. **Start with conservative parameters**
   ```yaml
   strategy:
     min_edge: 0.08              # Higher threshold
     kelly_fraction: 0.20        # Conservative sizing
     max_position_pct: 0.01      # Small positions
   ```

3. **Use tight risk limits initially**
   ```yaml
   risk:
     max_daily_loss: 25.0        # Small limit initially
     kill_switch_threshold: -50.0
   ```

4. **Gradually increase limits**
   - Only after proven success in paper trading
   - Increase limits incrementally
   - Monitor closely when increasing

### Disabled Live Boundary

- Do not provision trading credentials for AutoPredict.
- Do not instantiate retained live classes outside offline fake-adapter tests.
- Do not weaken the entrypoint guards to run an experiment.
- Track shadow and safety prerequisites in the active product plan.

### Risk Management

1. **Keep the kill switch enabled during paper/shadow testing**
   ```yaml
   risk:
     enable_kill_switch: true
   ```

2. **Set conservative initial limits**
   - Better to be too conservative than too aggressive
   - Can always increase limits later
   - Hard to recover from large losses

3. **Respect the kill switch**
   - Don't immediately reset after activation
   - Investigate why it triggered
   - Fix underlying issues before resuming

4. **Monitor daily P&L closely**
   - Set up external alerts if possible
   - Check frequently when starting out
   - Have a plan if limits are approached

### Security

1. **Do not provision or store venue credentials**
   - Live execution is disabled and supported workflows do not need them.
   - Never weaken the disabled entrypoint based on credential presence.

2. **Secure log files**
   ```bash
   # Logs may contain sensitive data
   chmod 700 logs/
   ```

### Monitoring

1. **Set up log rotation**
   ```bash
   # Prevent logs from growing indefinitely
   # Use logrotate or similar
   ```

2. **Monitor disk space**
   - Logs can grow large
   - Set up alerts for low disk space

3. **Archive important logs**
   - Keep trade history for analysis
   - Compress old logs
   - Back up performance data

4. **Set up external monitoring**
   - Email/SMS alerts for errors
   - Dashboard for real-time metrics
   - Automated health checks

## Emergency Procedures

### If Something Goes Wrong

1. **Stop trading immediately:**
   ```bash
   # Press Ctrl+C in terminal
   # Or activate kill switch manually
   ```

2. **Check positions:**
   ```python
   summary = risk_manager.get_positions_summary()
   print(summary)
   ```

3. **Review recent logs:**
   ```bash
   tail -n 100 logs/errors.log
   tail -n 100 logs/trades.jsonl
   ```

4. **Investigate root cause:**
   - Review all relevant logs
   - Check for configuration errors
   - Look for unexpected market conditions

5. **Fix and test before resuming:**
   - Fix identified issues
   - Test fix in paper mode
   - Resume cautiously with low limits

### Support

For issues not covered here:

1. Check logs for detailed error messages
2. Review configuration validation warnings
3. Test in paper mode to isolate issue
4. Consult the main `README.md` and `docs/ARCHITECTURE.md`

---

## Appendix: Configuration Reference

### Complete Configuration Example

See `configs/shadow_replay.yaml.example` for the supported annotated example. The live
example is retained only for offline safety-audit tests.

### Risk Configuration Defaults

```python
RiskConfig(
    max_position_per_market=100.0,
    max_total_exposure=500.0,
    max_daily_loss=50.0,
    kill_switch_threshold=-100.0,
    max_positions=20,
    max_correlation_exposure=0.3,
    position_timeout_hours=168.0,
    enable_kill_switch=True,
)
```

### Strategy Configuration Defaults

```python
StrategyConfig(
    name="mispriced_probability",
    min_edge=0.05,
    kelly_fraction=0.25,
    max_position_pct=0.02,
    aggressive_edge=0.12,
    min_book_liquidity=60.0,
    max_spread_pct=0.04,
    max_depth_fraction=0.15,
    split_threshold_fraction=0.25,
    limit_price_improvement_ticks=1.0,
)
```

---

**Remember: live execution is disabled. Use paper mode, preserve evidence, and respect risk limits.**
