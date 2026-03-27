# AutoPredict Strategy Guidance

## Current focus
- Improve execution quality before chasing more raw PnL.
- Prefer smaller orders in thin books.
- Use passive orders when edge is real but not urgent.
- Use aggressive orders only when edge is strong or expiry is near.

## Hard constraints
- Never risk more than 2% of bankroll on one market snapshot.
- Avoid markets with visible depth below the configured minimum.
- Treat wide spreads as execution cost, not alpha.

## Research questions
- Are weak-edge market orders causing slippage drag?
- Are passive orders too timid, hurting fill rate?
- Does time-to-expiry justify more aggressive execution?
- Which categories show the worst calibration drift?
