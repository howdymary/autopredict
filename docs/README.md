# Documentation

Use this folder when you want more detail than the top-level README and quickstart.

## Start here

- [../QUICKSTART.md](../QUICKSTART.md): first run, first config change, first comparison
- [ARCHITECTURE.md](ARCHITECTURE.md): how the simulator, agent, and CLI fit together
- [STRATEGIES.md](STRATEGIES.md): how to change trading behavior safely

## Reference guides

- [BACKTESTING.md](BACKTESTING.md): how to interpret backtest results and avoid common evaluation mistakes
- [DATASETS.md](DATASETS.md): canonical manifest, JSONL records, hashing, and point-in-time rules
- [FORECAST_PROVIDERS.md](FORECAST_PROVIDERS.md): typed forecast inputs, outputs, abstentions, and provenance
- [METRICS.md](METRICS.md): definitions and target ranges for the reported metrics
- [LEARNING.md](LEARNING.md): how to use the built-in feedback loop to improve the agent iteratively
- [DEPLOYMENT.md](DEPLOYMENT.md): paper deployment and the disabled live-execution boundary
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md): common setup, data, and execution issues
- [fair_prob_guidelines.md](fair_prob_guidelines.md): a practical guide for generating better `fair_prob` estimates

## Active product plan

- [Repository consolidation issue audit](specs/2026-07-14-repository-consolidation/issue-audit.md): prioritized product and engineering issues
- [Repository consolidation task plan](specs/2026-07-14-repository-consolidation/task-plan.md): sequenced implementation packets and verification gates
- [PRD](specs/2026-07-14-repository-consolidation/prd.md) and [technical PRP](specs/2026-07-14-repository-consolidation/prp.md): product outcomes, boundaries, and implementation design

## Archive

The working tree now keeps only active docs. Historical reports, phase notes, and prompt assets were
trimmed from the default checkout to keep the repo compact; use [archive/README.md](archive/README.md)
and git history if you need that older context.
