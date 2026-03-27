"""CLI for running minimal AutoPredict backtests and scoring the latest run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autopredict.run_experiment import run_backtest


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.json"


def _load_defaults() -> dict[str, object]:
    with DEFAULT_CONFIG.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve(path_like: str | Path) -> Path:
    path = Path(path_like)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _latest_metrics_file(state_dir: Path) -> Path | None:
    metrics_files = sorted(state_dir.glob("*/metrics.json"))
    return metrics_files[-1] if metrics_files else None


def command_backtest(args: argparse.Namespace) -> None:
    defaults = _load_defaults()
    config_path = _resolve(args.config or defaults["default_strategy_config"])
    dataset_path = _resolve(args.dataset or defaults["default_dataset"])
    guidance_path = _resolve(defaults["strategy_guidance"])
    state_dir = _resolve(defaults["state_dir"])
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
    state_dir = _resolve(defaults["state_dir"])
    latest = _latest_metrics_file(state_dir)
    if latest is None:
        raise SystemExit("No metrics.json found under state directory")
    print(latest.read_text(encoding="utf-8"))


def command_trade_live(args: argparse.Namespace) -> None:
    defaults = _load_defaults()
    if not bool(defaults.get("live_trading_enabled", False)):
        raise SystemExit("trade-live is disabled by default in AutoPredict")
    raise SystemExit("Live trading adapter is intentionally not implemented in this scaffold")


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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
