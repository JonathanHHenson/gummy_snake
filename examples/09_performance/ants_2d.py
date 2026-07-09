"""ants_2d.py compatibility module.

The ant-colony implementation lives in ``ant_colony_runtime`` helper modules so
this entry point stays navigable while preserving its original module globals.
"""

from __future__ import annotations
import __future__

from pathlib import Path

_PART_FILES = (
    "configuration.py",
    "world_setup_and_pheromones.py",
    "ant_simulation_query.py",
    "sketch_systems.py",
)


def _load_ant_colony_runtime() -> None:
    parts_dir = Path(__file__).with_name("ant_colony_runtime")
    flags = __future__.annotations.compiler_flag
    for name in _PART_FILES:
        source_path = parts_dir / name
        source = source_path.read_text()
        code = compile(source, str(source_path), "exec", flags=flags, dont_inherit=True)
        exec(code, globals())


_load_ant_colony_runtime()
del _load_ant_colony_runtime
