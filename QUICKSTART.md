# AutoPredict Quick Start

This walkthrough gets you from clone to scanning real Polymarket data.

## 1. Install

```bash
git clone https://github.com/howdymary/autopredict.git
cd autopredict
python -m pip install -e .
```

## 2. Scan live markets

```bash
python predict.py
```

This fetches active markets from Polymarket's Gamma API, pulls real order books from the CLOB, and shows you price, spread, depth, and volume for each market.

```bash
python predict.py --top 5 --verbose    # show fewer markets with detail
python predict.py --category politics   # filter by category
python predict.py --min-liquidity 5000  # only liquid markets
```

## 3. Find structural edges in multi-outcome events

```bash
python predict.py --events
```

Shows events where sibling market prices should sum to ~1.0. If they don't, the gap is a real structural edge.

## 4. Test your own prediction

If you think a market is mispriced, supply your probability estimate:

```bash
python predict.py --fair 0.60 <condition_id>
```

This fetches the real market + order book, computes the edge, and runs the AutoPredict agent to give you a trade recommendation (side, size, order type, limit price).

## 5. Iterate on the agent config

Open `strategy_configs/baseline.json` and change one parameter:

```json
{
  "min_edge": 0.08,
  "aggressive_edge": 0.16,
  "max_risk_fraction": 0.015
}
```

Then re-run `predict.py --fair` to see how the agent's recommendation changes.

That is the core loop:

1. find a market you have an opinion on
2. supply your fair_prob
3. see what the agent recommends
4. adjust config if the recommendation doesn't match your conviction
5. repeat

## 6. Pick the next guide

- Forecast quality: [docs/fair_prob_guidelines.md](docs/fair_prob_guidelines.md)
- Execution tuning: [docs/BACKTESTING.md](docs/BACKTESTING.md)
- Metrics explained: [docs/METRICS.md](docs/METRICS.md)
- Strategy ideas: [docs/STRATEGIES.md](docs/STRATEGIES.md)
- System overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Something broke: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
