"""Presentation configuration layered over the shared ant-colony domain core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from examples.common import example_parser
from examples.support.ant_colony.configuration import (
    CELL_SIZE,
    GRID_HEIGHT,
    GRID_WIDTH,
)

WIDTH = 960
HEIGHT = 540
TARGET_FPS = 60
OUTPUT = Path("examples/output/09_performance/ants_2d.png")
ARGS = example_parser("2D ECS ant-colony performance sketch.", OUTPUT).parse_args()
FPS_SMOOTHING = 0.12
GRID_OFFSET_X = (WIDTH - GRID_WIDTH * CELL_SIZE) * 0.5
GRID_OFFSET_Y = (HEIGHT - GRID_HEIGHT * CELL_SIZE) * 0.5

fps_last_time: float | None = None
fps_value = float(TARGET_FPS)
world_counts: dict[str, int] = {}
saved_output = False


@dataclass
class HudText:
    title: str
    stats: str
