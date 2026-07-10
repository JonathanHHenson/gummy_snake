"""2D ECS ant-colony performance sketch entry point."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_RUNTIME_DIR = Path(__file__).resolve().parent
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

_configuration = importlib.import_module("ant_colony_runtime.configuration")
importlib.import_module("ant_colony_runtime.ant_simulation_query")
importlib.import_module("ant_colony_runtime.world_setup_and_pheromones")
importlib.import_module("ant_colony_runtime.sketch_systems")

ARGS = _configuration.ARGS

__all__ = ["ARGS"]
