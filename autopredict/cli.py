"""Packaged CLI for running AutoPredict backtests and learning workflows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from .evaluation import (
    DatasetValidationError,
    evaluate_provider,
    load_dataset_v1,
    load_legacy_resolved_snapshots,
    report_json,
)
from .forecasting import MarketBaselineProvider, RecalibrationProvider
from .learning.analyzer import PerformanceAnalyzer
from .learning.logger import TradeLogger
from .live.safety_audit import run_safety_audit
from .self_improvement import (
    improvement_config_with_population,
    load_run_archive,
    promote_archive,
    run_forecast_owned_ratchet,
    run_market_recalibration_ratchet,
    write_run_archive,
)

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
BUNDLED_DEFAULT_ROOT = PACKAGE_ROOT / "_defaults"
SCAN_LIVE_DEFAULT_TIMEOUT_SECONDS = 30.0


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
    """Deprecated alias for the canonical baseline evaluation command."""

    if args.config:
        raise SystemExit(
            "canonical backtest does not accept --config; use `autopredict evaluate` "
            "with a versioned dataset manifest"
        )
    if not args.dataset:
        raise SystemExit(
            "backtest requires --dataset pointing to an autopredict.dataset.v1 manifest. "
            "AutoPredict does not ship synthetic default market datasets."
        )
    print("backtest is deprecated; using canonical market-baseline evaluation", file=sys.stderr)
    rendered = _evaluate_manifest(args.dataset, provider_name="market-baseline")
    defaults = _load_defaults()
    state_dir = _resolve_default(defaults["state_dir"], runtime_output=True)
    output_root = state_dir / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "metrics.json").write_text(rendered, encoding="utf-8")
    if args.output:
        output_path = _resolve_cli_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def _load_manifest(path_like: str | Path):
    try:
        return load_dataset_v1(_resolve_cli_path(path_like))
    except (DatasetValidationError, OSError, UnicodeError) as exc:
        raise SystemExit(f"dataset validation failed: {exc}") from exc


def _evaluate_manifest(
    path_like: str | Path,
    *,
    provider_name: str,
    recalibration_scale: float = 1.0,
    recalibration_shift: float = 0.0,
) -> str:
    if provider_name == "market-baseline":
        provider = MarketBaselineProvider()
    elif provider_name == "market-recalibration":
        try:
            provider = RecalibrationProvider(
                scale=recalibration_scale,
                shift=recalibration_shift,
            )
        except ValueError as exc:
            raise SystemExit(f"invalid provider configuration: {exc}") from exc
    else:
        raise SystemExit(f"unsupported forecast provider: {provider_name}")
    dataset = _load_manifest(path_like)
    try:
        report = evaluate_provider(dataset, provider)
    except ValueError as exc:
        raise SystemExit(f"evaluation failed: {exc}") from exc
    return report_json(report)


def command_validate(args: argparse.Namespace) -> None:
    """Validate a canonical dataset without evaluating forecasts."""

    dataset = _load_manifest(args.dataset)
    payload = {
        "valid": True,
        "schema_version": "autopredict.dataset.v1",
        "dataset_id": dataset.manifest.dataset_id,
        "dataset_sha256": dataset.dataset_sha256,
        "record_count": dataset.manifest.record_count,
        "observations": len(dataset.observations),
        "resolutions": len(dataset.resolutions),
        "independent_events": len({observation.event_id for observation in dataset.observations}),
        "completeness": dataset.manifest.completeness,
        "warnings": list(dataset.manifest.warnings),
    }
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))


def command_evaluate(args: argparse.Namespace) -> None:
    """Evaluate a canonical dataset with an explicit forecast provider."""

    rendered = _evaluate_manifest(
        args.dataset,
        provider_name=args.provider,
        recalibration_scale=args.recalibration_scale,
        recalibration_shift=args.recalibration_shift,
    )
    if args.output:
        output_path = _resolve_cli_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def command_score_latest(args: argparse.Namespace) -> None:
    defaults = _load_defaults()
    state_dir = _resolve_default(defaults["state_dir"], runtime_output=True)
    latest = _latest_metrics_file(state_dir)
    if latest is None:
        raise SystemExit("No metrics.json found under state directory")
    print(latest.read_text(encoding="utf-8"))


def command_trade_live(args: argparse.Namespace) -> None:
    raise SystemExit(
        "trade-live is disabled in AutoPredict pending shadow-trading and safety gates. "
        "Use scan-live for read-only public Polymarket data."
    )


def command_scan_live(args: argparse.Namespace) -> None:
    """Scan public Polymarket data without generating forecasts or orders."""

    from . import live_scan

    client = live_scan.PublicPolymarketClient(timeout_seconds=args.timeout)
    scanner = live_scan.LivePolymarketScanner(client)
    if args.events:
        reports = scanner.scan_events(
            limit=args.limit,
            top=args.top,
            min_markets=args.min_markets,
            tolerance=args.tolerance,
        )
        rendered = (
            live_scan.reports_to_json(reports)
            if args.json
            else live_scan.format_event_scan(reports, verbose=args.verbose)
        )
    else:
        reports = scanner.scan_markets(
            limit=args.limit,
            top=args.top,
            min_liquidity=args.min_liquidity,
            min_volume=args.min_volume,
            category=args.category,
            include_books=not args.no_books,
        )
        rendered = (
            live_scan.reports_to_json(reports)
            if args.json
            else live_scan.format_market_scan(reports, verbose=args.verbose)
        )
    print(rendered)


def command_safety_audit(args: argparse.Namespace) -> None:
    """Run local production-safety checks without touching venue APIs."""

    result = run_safety_audit(_resolve_cli_path(args.config) if args.config else None)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if not result.passed:
        raise SystemExit(1)


def command_learn_analyze(args: argparse.Namespace) -> None:
    """Analyze recent trading performance from logs."""

    defaults = _load_defaults()
    log_dir = (
        _resolve_cli_path(args.log_dir)
        if args.log_dir
        else _resolve_default("state/trades", runtime_output=True)
    )

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
    print("Use `autopredict learn improve --dataset <resolved-data.json>` for ratcheted runs.")
    print("\nExample:")
    print(
        "  autopredict learn improve --dataset resolved_markets.json --archive-dir state/archives"
    )


def command_learn_improve(args: argparse.Namespace) -> None:
    """Run the package-native forecast-owned ratchet."""

    if not args.dataset:
        raise SystemExit(
            "learn improve requires --dataset with real historical/resolved market data. "
            "AutoPredict does not ship synthetic default market datasets."
        )
    dataset_path = _resolve_cli_path(args.dataset)
    snapshots = load_legacy_resolved_snapshots(dataset_path)
    config = improvement_config_with_population(
        population_size=args.population_size,
        train_size=args.train_size,
        validation_size=args.validation_size,
    )
    if getattr(args, "recalibrate", False):
        summary = run_market_recalibration_ratchet(
            dataset_path,
            config=config,
            warmup_fraction=args.warmup_fraction,
        )
    else:
        summary = run_forecast_owned_ratchet(dataset_path, config=config)
    payload = {
        **summary.to_dict(),
        "num_snapshots": len(snapshots),
    }
    if getattr(args, "recalibrate", False):
        fit_sample_size = summary.initial_genome.get("metadata", {}).get("fit_sample_size", 0)
        payload["num_warmup_snapshots"] = fit_sample_size
        payload["num_evaluation_snapshots"] = len(snapshots) - fit_sample_size

    archive_path = None
    if args.archive_dir or args.frontier_path:
        archive_dir = (
            _resolve_cli_path(args.archive_dir)
            if args.archive_dir
            else _resolve_default("state/meta_harness/archives", runtime_output=True)
        )
        archive_path = write_run_archive(
            summary,
            archive_dir,
            dataset_path=dataset_path,
            config=config.walk_forward,
            genome=summary.final_genome,
            repo_root=REPO_ROOT,
        )
        payload["archive_path"] = str(archive_path)

    if args.frontier_path:
        if not summary.folds:
            raise SystemExit("frontier promotion requires at least one validation fold")
        final_metrics = summary.folds[-1]["winner_metrics"]
        metric_name = "log_score"
        score = float(final_metrics[metric_name])
        if archive_path is None:
            raise SystemExit("frontier promotion requires an archive path")
        promotion = promote_archive(
            _resolve_cli_path(args.frontier_path),
            load_run_archive(archive_path),
            score=score,
            metric_name=metric_name,
            archive_path=archive_path,
        )
        payload["frontier_promotion"] = {
            "accepted": promotion.accepted,
            "key": promotion.key,
            "entry": promotion.entry,
            "previous": promotion.previous,
        }
    if args.output:
        output_path = _resolve_cli_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoPredict experiment CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser(
        "backtest",
        help="Deprecated alias for canonical market-baseline evaluation",
    )
    backtest.add_argument("--config", help=argparse.SUPPRESS)
    backtest.add_argument("--dataset", help="Path to autopredict.dataset.v1 manifest")
    backtest.add_argument("--output", help="Optional deterministic report JSON path")
    backtest.set_defaults(func=command_backtest)

    validate = subparsers.add_parser(
        "validate",
        help="Validate a versioned point-in-time dataset",
    )
    validate.add_argument("--dataset", required=True, help="Path to dataset manifest JSON")
    validate.set_defaults(func=command_validate)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Evaluate forecasts against a market-implied baseline",
    )
    evaluate.add_argument("--dataset", required=True, help="Path to dataset manifest JSON")
    evaluate.add_argument(
        "--provider",
        choices=("market-baseline", "market-recalibration"),
        default="market-baseline",
    )
    evaluate.add_argument("--recalibration-scale", type=float, default=1.0)
    evaluate.add_argument("--recalibration-shift", type=float, default=0.0)
    evaluate.add_argument("--output", help="Optional deterministic report JSON path")
    evaluate.set_defaults(func=command_evaluate)

    score_latest = subparsers.add_parser("score-latest", help="Print the latest metrics JSON")
    score_latest.set_defaults(func=command_score_latest)

    scan_live = subparsers.add_parser(
        "scan-live",
        help="Scan public Polymarket data without forecasts or orders",
    )
    scan_live.add_argument("--events", action="store_true", help="Scan event sibling price sums")
    scan_live.add_argument("--category", help="Filter market scan by observed category")
    scan_live.add_argument("--min-liquidity", type=float, default=0.0)
    scan_live.add_argument("--min-volume", type=float, default=0.0)
    scan_live.add_argument("--min-markets", type=int, default=2)
    scan_live.add_argument("--tolerance", type=float, default=0.02)
    scan_live.add_argument("--limit", type=int, default=100)
    scan_live.add_argument("--top", type=int, default=15)
    scan_live.add_argument("--timeout", type=float, default=SCAN_LIVE_DEFAULT_TIMEOUT_SECONDS)
    scan_live.add_argument("--json", action="store_true", help="Emit JSON")
    scan_live.add_argument("--verbose", "-v", action="store_true", help="Show IDs and sources")
    scan_live.add_argument("--no-books", action="store_true", help="Skip CLOB order books")
    scan_live.set_defaults(func=command_scan_live)

    safety_audit = subparsers.add_parser(
        "safety-audit",
        help="Run no-network live deployment safety checks",
    )
    safety_audit.add_argument("--config", help="Optional live YAML config to audit")
    safety_audit.set_defaults(func=command_safety_audit)

    trade_live = subparsers.add_parser("trade-live", help="Disabled live order entrypoint")
    trade_live.add_argument("--config", help="Reserved for future live execution config")
    trade_live.set_defaults(func=command_trade_live)

    learn = subparsers.add_parser("learn", help="Self-improvement and learning tools")
    learn_subparsers = learn.add_subparsers(dest="learn_command", required=True)

    learn_analyze = learn_subparsers.add_parser(
        "analyze", help="Analyze recent trading performance"
    )
    learn_analyze.add_argument("--log-dir", help="Directory containing trade logs")
    learn_analyze.add_argument("--days", type=int, help="Only analyze last N days")
    learn_analyze.add_argument("--output", help="Save full report to JSON file")
    learn_analyze.set_defaults(func=command_learn_analyze)

    learn_tune = learn_subparsers.add_parser("tune", help="Tune strategy parameters")
    learn_tune.add_argument("--config", help="Current strategy config JSON file")
    learn_tune.add_argument("--output", help="Save tuned config to this file")
    learn_tune.set_defaults(func=command_learn_tune)

    learn_improve = learn_subparsers.add_parser("improve", help="Run full improvement loop")
    learn_improve.add_argument("--dataset", help="Resolved-market dataset JSON file")
    learn_improve.add_argument(
        "--population-size", type=int, default=5, help="Population size per fold"
    )
    learn_improve.add_argument(
        "--train-size", type=int, default=3, help="Train windows or groups per fold"
    )
    learn_improve.add_argument(
        "--validation-size", type=int, default=1, help="Validation windows or groups per fold"
    )
    learn_improve.add_argument(
        "--recalibrate",
        action="store_true",
        help="Learn a market-recalibration forecast (fit on a past window, validated out-of-sample) instead of the frozen no-edge model",
    )
    learn_improve.add_argument(
        "--warmup-fraction",
        type=float,
        default=0.4,
        help="Fraction of the earliest data used only to fit the recalibration seed (with --recalibrate)",
    )
    learn_improve.add_argument("--output", help="Optional JSON path for the ratchet summary")
    learn_improve.add_argument("--archive-dir", help="Write an auditable meta-harness archive")
    learn_improve.add_argument("--frontier-path", help="Promote the archive to this frontier JSON")
    learn_improve.set_defaults(func=command_learn_improve)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
