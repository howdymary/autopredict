#!/usr/bin/env python3
"""Compatibility wrapper for the production-safe read-only live scanner."""

from __future__ import annotations

import sys

from autopredict.cli import main as autopredict_main


def main(argv: list[str] | None = None) -> None:
    """Run ``autopredict scan-live`` with legacy ``python predict.py`` ergonomics."""

    args = list(sys.argv[1:] if argv is None else argv)
    if "--fair" in args:
        raise SystemExit(
            "predict.py is read-only and does not produce trade recommendations. "
            "Use `python -m autopredict.cli scan-live` to inspect live markets, "
            "or provide explicit resolved data to `python -m autopredict.cli backtest`."
        )
    sys.argv = ["autopredict", "scan-live", *args]
    autopredict_main()


if __name__ == "__main__":
    main()
