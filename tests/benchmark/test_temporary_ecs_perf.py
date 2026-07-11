"""Compatibility forwarding entry point for the former temporary ECS benchmark."""

from __future__ import annotations

import os
from importlib import import_module

for _suffix in ("FRAMES", "REPEATS", "MODE"):
    _legacy_name = f"GUMMY_TEMP_ECS_BENCHMARK_{_suffix}"
    _canonical_name = f"GUMMY_ECS_SCENARIOS_BENCHMARK_{_suffix}"
    if _canonical_name not in os.environ and _legacy_name in os.environ:
        os.environ[_canonical_name] = os.environ[_legacy_name]

_ecs_scenarios = import_module("test_ecs_scenarios_perf")
SCENES = _ecs_scenarios.SCENES
_run_scene = _ecs_scenarios._run_scene
TemporaryEcsBenchmarkSummary = _ecs_scenarios.EcsScenarioBenchmarkSummary
test_ecs_performance_scenario_benchmark = _ecs_scenarios.test_ecs_performance_scenario_benchmark

test_temporary_ecs_example_benchmark = test_ecs_performance_scenario_benchmark

__all__ = [
    "SCENES",
    "TemporaryEcsBenchmarkSummary",
    "_run_scene",
    "test_temporary_ecs_example_benchmark",
]
