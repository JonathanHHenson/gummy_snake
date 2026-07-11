"""Stable ECS performance scenario sketches.

Each module is executable as a bounded example and is measured by
``tests/benchmark/test_ecs_scenarios_perf.py``.
"""

from __future__ import annotations

SCENARIO_IDS = (
    "rust_2d_primitives_branching",
    "python_systems_udfs_sprites",
    "structural_churn_tags_components",
    "spatial_events_for_each_stress",
    "webgl_3d_ecs_primitives_models",
)
