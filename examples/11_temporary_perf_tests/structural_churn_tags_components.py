"""Legacy forwarding entry point for the stable ECS performance scenario."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(
    str(
        Path(__file__).resolve().parents[1]
        / "09_performance"
        / "ecs_scenarios"
        / "structural_churn_tags_components.py"
    ),
    run_name="__main__",
)
