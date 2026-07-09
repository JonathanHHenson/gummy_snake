"""test_ecs_ants_2d_perf.py compatibility module.

The benchmark support code lives in ``ant_colony_benchmark_support`` helper
modules so this test entry point stays navigable while preserving its original
module globals.
"""

from __future__ import annotations
import __future__

from pathlib import Path

_PART_FILES = (
    "configuration.py",
    "world_setup_and_pheromones.py",
    "ant_simulation_query.py",
    "colony_systems.py",
    "benchmark_runner.py",
)


def _load_ant_colony_benchmark_support() -> None:
    parts_dir = Path(__file__).with_name("ant_colony_benchmark_support")
    flags = __future__.annotations.compiler_flag
    for name in _PART_FILES:
        source_path = parts_dir / name
        source = source_path.read_text()
        code = compile(source, str(source_path), "exec", flags=flags, dont_inherit=True)
        exec(code, globals())


_load_ant_colony_benchmark_support()
del _load_ant_colony_benchmark_support
