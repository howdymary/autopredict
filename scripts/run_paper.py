#!/usr/bin/env python3
"""Compatibility wrapper for the real durable shadow runner."""

from __future__ import annotations

import argparse
import json

from autopredict.config import load_shadow_config
from autopredict.live.shadow.runner import run_shadow


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run deterministic shadow execution (no venue order capability)"
    )
    parser.add_argument("--config", required=True, help="Shadow YAML configuration")
    args = parser.parse_args()
    print(json.dumps(run_shadow(load_shadow_config(args.config)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
