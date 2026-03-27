# Custom Strategy Example

This example shows how to create a custom trading strategy by extending the AutoPredict agent.

## Conservative Limit-Only Strategy

This strategy NEVER uses market orders, always using limit orders to capture the spread.

### Implementation

See `conservative_agent.py` for the custom agent implementation.

### Key Modifications

1. **Override `decide_order_type()`**: Always return "limit"
2. **Adjust sizing**: More conservative position sizes
3. **Stricter gating**: Higher edge threshold

### Running the Example

```bash
cd "/Users/howdymary/Documents/New project/autopredict"
python3 examples/custom_strategy/run_conservative.py
```

### Expected Results

Compared to baseline:
- Lower slippage (only using limit orders)
- Lower fill rate (passive orders don't always fill)
- Higher Sharpe ratio (better execution quality)
- Fewer trades (stricter filters)

### When to Use This Strategy

- Markets with wide spreads
- High liquidity environments
- When you can afford to wait for fills
- Prioritizing execution quality over fill rate
