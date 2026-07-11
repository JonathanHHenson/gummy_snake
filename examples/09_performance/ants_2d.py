"""2D ECS ant-colony performance sketch entry point."""

from __future__ import annotations

import sys
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

ARGS = import_module("ant_colony_runtime.configuration").ARGS
run: Callable[[], None] = import_module("ant_colony_runtime.sketch_systems").run

__all__ = ["ARGS", "run"]


if __name__ == "__main__":
    run()
