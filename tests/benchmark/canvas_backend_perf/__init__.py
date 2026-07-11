"""Canonical canvas backend benchmark scenarios and subprocess runner."""

from __future__ import annotations

BENCHMARK_ID = "canvas_backend_interactive_v1"
BUILD_MODE = "maturin develop --release"
COMPARISON_TOLERANCE = "Compare only matching machine, OS, Python, and release-build fingerprints."
