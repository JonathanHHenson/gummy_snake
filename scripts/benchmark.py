#!/usr/bin/env python3
"""Entrypoint for the governed replacement benchmark CLI."""

import sys
from pathlib import Path

# Direct script execution starts with ``scripts/`` on sys.path, not the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
