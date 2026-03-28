# AutoPredict Deployment Guide

Complete guide for deploying AutoPredict trading strategies in paper and live modes.

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

AutoPredict supports two deployment modes:

- **Paper Trading**: Simulated trading with no real money. Safe for development and testing.
- **Live Trading**: Real trading with real capital. Requires explicit confirmation and has multiple safety layers.

### Quick Start

```bash
# Paper trading (safe)
python scripts/run_paper.py --config configs/paper_trading.yaml

# Live trading (DANGER - real money)
python scripts/run_live.py --config configs/live_trading.yaml
```

## Paper Trading

Paper trading simulates order execution without risking real capital. Use this to:

- Develop and test trading strategies
- Validate configuration settings
- Learn the system safely
- Backtest strategy performance

### Setup

1. **Use the provided configuration:**
   ```bash
   # configs/paper_trading.yaml is ready to use
   python scripts/run_paper.py --config configs/paper_trading.yaml
   ```

2. **Or create your own:**
   ```bash
   cp configs/paper_trading.yaml configs/my_paper_config.yaml
   # Edit my_paper_config.yaml
   python scripts/run_paper.py --config configs/my_paper_config.yaml
   ```

### Running Paper Trading

```bash
# Run indefinitely
python scripts/run_paper.py --config configs/paper_trading.yaml

# Run for 1 hour (3600 seconds)
python scripts/run_paper.py --config configs/paper_trading.yaml --duration 3600

# Enable verbose logging
python scripts/run_paper.py --config configs/paper_trading.yaml --verbose
```

### What Gets Simulated

- Order execution with realistic slippage
- Commission charges
- Position tracking
- P&L calculation
- Risk limit enforcement
- All logging functionality

### What's Different from Live

- No real API calls to venues
- Simplified order book simulation
- Probabilistic limit order fills
- No actual capital at risk

## Live Trading

**WARNING: Live trading uses REAL MONEY on REAL markets.**

### Prerequisites

Before running live trading:

1. **Extensive paper trading experience**
   - Test your strategy thoroughly in paper mode
   - Understand all configuration parameters
   - Verify risk limits are appropriate

2. **API credentials**
   - Obtain API keys from your chosen venue (e.g., Polymarket)
   - Verify API access and permissions
   - Test in testnet/sandbox mode if available

3. **Capital preparation**
   - Fund your venue account
   - Start with small amounts
   - Never risk more than you can afford to lose

4. **Monitoring setup**
   - Plan to monitor continuously
   - Set up alerts for errors/losses
   - Have a manual intervention plan

### Setup

1. **Copy the live configuration template:**
   ```bash
   cp configs/live_trading.yaml.example configs/live_trading.yaml
   ```

2. **Set up environment variables:**
   ```bash
   # Add to ~/.bashrc or ~/.zshrc for persistence
   export POLYMARKET_API_KEY="your-api-key-here"
   export POLYMARKET_API_SECRET="your-api-secret-here"

   # Or set for current session only
   export POLYMARKET_API_KEY="..."
   export POLYMARKET_API_SECRET="..."
   ```

3. **Edit the configuration:**
   ```yaml
   # configs/live_trading.yaml

   risk:
     max_position_per_market: 50.0    # Adjust based on your risk tolerance
     max_total_exposure: 200.0        # Total capital you're willing to risk
     max_daily_loss: 25.0             # Stop trading if daily loss hits this
     kill_switch_threshold: -50.0     # Emergency stop at severe loss

   venue:
     mode: live                        # CRITICAL: Must be "live"
     api_key: ${POLYMARKET_API_KEY}   # Loaded from environment
     api_secret: ${POLYMARKET_API_SECRET}
     testnet: false                    # Set to true for testnet
   ```

   For authenticated Polymarket trading you also need:
   `POLYMARKET_API_PASSPHRASE`, `POLYMARKET_PRIVATE_KEY`, and `POLYMARKET_FUNDER`.

4. **IMPORTANT: Add to .gitignore**
   ```bash
   # Make sure live_trading.yaml is in .gitignore
   echo "configs/live_trading.yaml" >> .gitignore
   ```

### Running Live Trading

**Step 1: Dry Run (Recommended)**

Test configuration without executing trades:

```bash
python scripts/run_live.py --config configs/live_trading.yaml --dry-run
```

This validates:
- Configuration is correct
- Risk limits are sane for live mode
- Missing credential env vars are surfaced without blocking the dry run
- Risk limits are reasonable

**Step 2: Live Run**

```bash
python scripts/run_live.py --config configs/live_trading.yaml
```

You will be prompted:

```
WARNING: LIVE TRADING MODE
This will execute REAL trades using REAL money on REAL markets.

Configuration Summary:
  Experiment: live_trading_experiment
  Venue: polymarket
  Risk Limits: ...

Type 'CONFIRM LIVE TRADING' (exact case) to proceed:
>
```

Type exactly `CONFIRM LIVE TRADING` to proceed.

**Step 3: Final Countdown**

After confirmation, you have 5 seconds to abort:

```
LIVE TRADING STARTING IN 5 SECONDS
Press Ctrl+C NOW to abort
5...
4...
3...
2...
1...
STARTING LIVE TRADING NOW
```

### Stopping Live Trading

**Graceful Stop:**
- Press `Ctrl+C` in the terminal
- Positions remain open (you must close manually)

**Emergency Stop (Kill Switch):**
- Activated automatically if daily loss exceeds `kill_switch_threshold`
- Can be activated manually (see [Kill Switch](#kill-switch) section)

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

### Environment Variables

Use `${VAR_NAME}` syntax for sensitive values:

```yaml
venue:
  api_key: ${POLYMARKET_API_KEY}              # Required
  base_url: ${API_URL:https://api.default}    # Optional with default
```

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

AutoPredict includes multiple safety layers to protect your capital:

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
  enable_kill_switch: true         # Must be true for live trading
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
    # Safe to execute
    trader.place_order(order)
else:
    # Blocked by risk limits
    print(f"Order blocked: {result.reason}")
```

### 6. Mode Separation

Paper and live traders are completely separate:

```python
# Paper trader - safe simulation
paper_trader = PaperTrader()

# Live trader - requires confirmation
live_trader = LiveTrader(venue_adapter)  # Prompts for confirmation
```

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
  "execution_mode": "live",
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

**1. "Environment variable not found"**

```bash
# Make sure you've exported the variable
echo $POLYMARKET_API_KEY

# If empty, set it:
export POLYMARKET_API_KEY="your-key-here"
```

**2. "Configuration is not in live mode"**

```yaml
# Make sure venue.mode is set correctly
venue:
  mode: live    # Not "paper"
```

**3. "Kill switch must be enabled for live trading"**

```yaml
# Enable kill switch (required for live mode)
risk:
  enable_kill_switch: true
```

**4. "API key is required for live trading mode"**

```yaml
venue:
  mode: live
  api_key: ${POLYMARKET_API_KEY}    # Must be set
```

**5. Kill switch activated unexpectedly**

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
python scripts/run_paper.py --config configs/paper_trading.yaml --verbose
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

### Live Trading

1. **Pre-flight checklist:**
   - [ ] Strategy tested extensively in paper mode
   - [ ] Configuration validated with dry-run
   - [ ] API credentials tested (testnet if available)
   - [ ] Risk limits reviewed and appropriate
   - [ ] Monitoring plan in place
   - [ ] Manual intervention plan ready

2. **During operation:**
   - Monitor continuously when starting
   - Check logs regularly for errors
   - Verify positions match expectations
   - Watch for kill switch warnings
   - Have manual stop plan ready

3. **Position management:**
   - Close positions before extended downtime
   - Monitor for position timeouts
   - Review open positions daily
   - Don't let positions accumulate accidentally

4. **After trading:**
   - Review all trades in logs
   - Analyze decisions (both trades and skips)
   - Calculate actual vs expected performance
   - Adjust configuration based on results

### Risk Management

1. **Never disable the kill switch in live mode**
   ```yaml
   risk:
     enable_kill_switch: true    # ALWAYS true for live trading
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

1. **Never commit API keys**
   ```bash
   # Make sure .gitignore includes:
   configs/live_trading.yaml
   .env
   ```

2. **Use environment variables**
   ```yaml
   # Good
   api_key: ${POLYMARKET_API_KEY}

   # Bad (never do this)
   api_key: "sk-1234567890"
   ```

3. **Limit API key permissions**
   - Only grant necessary permissions
   - Use testnet keys for testing
   - Rotate keys periodically

4. **Secure log files**
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

4. **Close positions manually if needed:**
   - Use venue's web interface
   - Or submit manual closing orders

5. **Investigate root cause:**
   - Review all relevant logs
   - Check for configuration errors
   - Look for unexpected market conditions

6. **Fix and test before resuming:**
   - Fix identified issues
   - Test fix in paper mode
   - Resume cautiously with low limits

### Support

For issues not covered here:

1. Check logs for detailed error messages
2. Review configuration validation warnings
3. Test in paper mode to isolate issue
4. Consult the main README.md and ARCHITECTURE.md

---

## Appendix: Configuration Reference

### Complete Configuration Example

See `configs/paper_trading.yaml` and `configs/live_trading.yaml.example` for complete annotated examples.

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

**Remember: Start with paper trading. Be conservative. Monitor continuously. Respect risk limits.**
