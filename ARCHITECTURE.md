# Architecture

The detailed system guide lives in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

For Step 1, the main architectural addition is [`autopredict/prediction_market`](autopredict/prediction_market), which introduces:

- typed venue/snapshot/signal/decision objects for prediction-market workflows
- a composable `PredictionMarketAgent`
- a strategy registry for running multiple agent variants cleanly
- compatibility adapters that bridge the new package to the existing strategy implementations

That keeps the current experiment loop stable while making room for Step 2 backtesting and scoring infrastructure, followed by Step 3 self-improvement and strategy-selection logic.

Step 2 is the evaluation seam: `autopredict/evaluation/` holds proper scoring rules, calibration summaries, and scaffold-level backtests so the new prediction-market layer can be judged independently from strategy code.

Step 3 is the mutation-and-selection seam: `autopredict/self_improvement/` generates strategy variants, evaluates them through `autopredict/evaluation/`, and promotes winners only when score and calibration guardrails are satisfied across chronological, regime, or market-family holdouts.
