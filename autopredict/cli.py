"""Packaged CLI for running AutoPredict backtests and learning workflows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .learning.analyzer import PerformanceAnalyzer
from .learning.logger import TradeLogger
from .run_experiment import run_backtest


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
BUNDLED_DEFAULT_ROOT = PACKAGE_ROOT / "_defaults"


def _project_root() -> Path:
    """Return the repo root when available, otherwise bundled defaults."""

    repo_config = REPO_ROOT / "config.json"
    if repo_config.exists():
        return REPO_ROOT
    return BUNDLED_DEFAULT_ROOT


def _using_bundled_defaults() -> bool:
    return _project_root() == BUNDLED_DEFAULT_ROOT


def _default_config_path() -> Path:
    return _project_root() / "config.json"


def _load_defaults() -> dict[str, object]:
    with _default_config_path().open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_cli_path(path_like: str | Path) -> Path:
    """Resolve user-supplied paths relative to the current working directory."""

    path = Path(path_like)
    return path if path.is_absolute() else Path.cwd() / path


def _resolve_default(path_like: str | Path, *, runtime_output: bool = False) -> Path:
    """Resolve default paths against the repo or bundled defaults."""

    path = Path(path_like)
    if path.is_absolute():
        return path

    if runtime_output and _using_bundled_defaults():
        return Path.cwd() / path

    base = _project_root()
    return base / path


def _latest_metrics_file(state_dir: Path) -> Path | None:
    metrics_files = sorted(state_dir.glob("*/metrics.json"))
    return metrics_files[-1] if metrics_files else None


def command_backtest(args: argparse.Namespace) -> None:
    defaults = _load_defaults()
    config_path = (
        _resolve_cli_path(args.config)
        if args.config
        else _resolve_default(defaults["default_strategy_config"])
    )
    dataset_path = (
        _resolve_cli_path(args.dataset)
        if args.dataset
        else _resolve_default(defaults["default_dataset"])
    )
    guidance_path = _resolve_default(defaults["strategy_guidance"])
    state_dir = _resolve_default(defaults["state_dir"], runtime_output=True)
    output_root = state_dir / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_root.mkdir(parents=True, exist_ok=True)

    metrics = run_backtest(
        config_path=config_path,
        dataset_path=dataset_path,
        strategy_guidance_path=guidance_path,
        starting_bankroll=float(defaults["starting_bankroll"]),
    )
    output_path = output_root / "metrics.json"
    output_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(metrics, indent=2, sort_keys=True))


def command_score_latest(args: argparse.Namespace) -> None:
    defaults = _load_defaults()
    state_dir = _resolve_default(defaults["state_dir"], runtime_output=True)
    latest = _latest_metrics_file(state_dir)
    if latest is None:
        raise SystemExit("No metrics.json found under state directory")
    print(latest.read_text(encoding="utf-8"))


def command_trade_live(args: argparse.Namespace) -> None:
    defaults = _load_defaults()
    if not bool(defaults.get("live_trading_enabled", False)):
        raise SystemExit("trade-live is disabled by default in AutoPredict")
    raise SystemExit("Live trading adapter is intentionally not implemented in this scaffold")


def command_learn_analyze(args: argparse.Namespace) -> None:
    """Analyze recent trading performance from logs."""

    defaults = _load_defaults()
    log_dir = _resolve_cli_path(args.log_dir) if args.log_dir else _resolve_default("state/trades", runtime_output=True)

    logger = TradeLogger(log_dir)
    if args.days:
        logs = logger.load_recent(days=args.days)
        print(f"Loaded {len(logs)} trade logs from last {args.days} days")
    else:
        logs = logger.load_all()
        print(f"Loaded {len(logs)} total trade logs")

    if not logs:
        print("No trade logs found. Run some backtests first!")
        return

    analyzer = PerformanceAnalyzer(logs)
    report = analyzer.generate_report()

    print("\n" + "=" * 60)
    print("PERFORMANCE ANALYSIS")
    print("=" * 60)
    print(f"Total trades: {report.total_trades}")
    print(f"Total PnL: ${report.total_pnl:.2f}")
    print(f"Win rate: {report.win_rate:.2%}")
    print(f"Avg win: ${report.avg_win:.2f}")
    print(f"Avg loss: ${report.avg_loss:.2f}")
    if report.sharpe_ratio is not None:
        print(f"Sharpe ratio: {report.sharpe_ratio:.3f}")
    print(f"Calibration error: {report.calibration_error:.3f}")
    print(f"Edge capture rate: {report.edge_capture_rate:.2%}")

    print("\nDecision breakdown:")
    for decision, count in report.by_decision.items():
        print(f"  {decision}: {count}")

    if report.failure_regimes:
        print("\nFailure regimes identified:")
        for regime in report.failure_regimes:
            print(f"  - {regime}")

    if report.recommendations:
        print("\nRecommendations:")
        for rec in report.recommendations:
            print(f"  - {rec}")

    if args.output:
        output_path = Path(args.output)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2)
        print(f"\nFull report saved to {output_path}")


def command_learn_tune(args: argparse.Namespace) -> None:
    """Describe the current parameter tuning entrypoint."""

    print("Parameter tuning requires full backtest integration.")
    print("Use scripts/learn_and_improve.py for advanced tuning workflows.")
    print("\nExample:")
    print("  python scripts/learn_and_improve.py tune \\")
    print(f"    --config {args.config or 'strategy_configs/default.json'} \\")
    print("    --output configs/strategy_tuned.json")


def command_learn_improve(args: argparse.Namespace) -> None:
    """Describe the current improvement-loop entrypoint."""

    print("Full improvement loop requires complete backtest integration.")
    print("Use scripts/learn_and_improve.py for the complete workflow.")
    print("\nExample:")
    print("  python scripts/learn_and_improve.py improve \\")
    print(f"    --config {args.config or 'strategy_configs/default.json'} \\")
    print("    --log-dir state/trades \\")
    print("    --auto-save")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoPredict experiment CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest", help="Run a sample backtest over market snapshots")
    backtest.add_argument("--config", help="Path to strategy config JSON")
    backtest.add_argument("--dataset", help="Path to dataset JSON")
    backtest.set_defaults(func=command_backtest)

    score_latest = subparsers.add_parser("score-latest", help="Print the latest metrics JSON")
    score_latest.set_defaults(func=command_score_latest)

    trade_live = subparsers.add_parser("trade-live", help="Placeholder live trading entrypoint")
    trade_live.add_argument("--config", help="Unused placeholder for future adapter parity")
    trade_live.set_defaults(func=command_trade_live)

    learn = subparsers.add_parser("learn", help="Self-improvement and learning tools")
    learn_subparsers = learn.add_subparsers(dest="learn_command", required=True)

    learn_analyze = learn_subparsers.add_parser("analyze", help="Analyze recent trading performance")
    learn_analyze.add_argument("--log-dir", help="Directory containing trade logs")
    learn_analyze.add_argument("--days", type=int, help="Only analyze last N days")
    learn_analyze.add_argument("--output", help="Save full report to JSON file")
    learn_analyze.set_defaults(func=command_learn_analyze)

    learn_tune = learn_subparsers.add_parser("tune", help="Tune strategy parameters")
    learn_tune.add_argument("--config", help="Current strategy config JSON file")
    learn_tune.add_argument("--output", help="Save tuned config to this file")
    learn_tune.set_defaults(func=command_learn_tune)

    learn_improve = learn_subparsers.add_parser("improve", help="Run full improvement loop")
    learn_improve.add_argument("--config", help="Current strategy config JSON file")
    learn_improve.add_argument("--log-dir", help="Directory containing trade logs")
    learn_improve.add_argument("--auto-save", action="store_true", help="Auto-save improved config")
    learn_improve.set_defaults(func=command_learn_improve)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
