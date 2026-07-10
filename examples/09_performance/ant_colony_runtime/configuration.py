"""2D ECS ant-colony performance sketch.

Two competing ant colonies forage through a voxel-grid world. Anthills, food,
and randomized walls are placed on the grid, while ants move freely in continuous
2D space. Searching ants random-walk and leave home scent; ants carrying food
follow that scent home while laying food scent for nestmates. Setup verifies
that the randomized walls do not isolate either anthill from any food clump.
"""

from __future__ import annotations

import math
import random
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake import ecs
from gummysnake.ecs import canvas as ca

WIDTH = 960
HEIGHT = 540
TARGET_FPS = 60
OUTPUT = Path("examples/output/09_performance/ants_2d.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
FPS_SMOOTHING = 0.12

GRID_WIDTH = 128
GRID_HEIGHT = 96
CELL_SIZE = 6.0
GRID_OFFSET_X = (WIDTH - GRID_WIDTH * CELL_SIZE) * 0.5
GRID_OFFSET_Y = (HEIGHT - GRID_HEIGHT * CELL_SIZE) * 0.5
ANTS_PER_COLONY = 5_000

RED_ANT_TAG = "red_ant"
BLUE_ANT_TAG = "blue_ant"
RED_HILL_TAG = "red_hill"
BLUE_HILL_TAG = "blue_hill"
WALL_TAG = "ant_wall_voxel"
FOOD_TAG = "food_voxel"
PHEROMONE_TAG = "ant_pheromone_voxel"

RED_HILL = (14, GRID_HEIGHT // 2)
BLUE_HILL = (GRID_WIDTH - 15, GRID_HEIGHT // 2)
FOOD_CLUMPS = (
    (GRID_WIDTH // 2, 18),
    (GRID_WIDTH // 2, GRID_HEIGHT - 19),
    (GRID_WIDTH // 3, GRID_HEIGHT // 3),
    (GRID_WIDTH * 2 // 3, GRID_HEIGHT * 2 // 3),
)

WALL_AVOID_RADIUS = CELL_SIZE * 1.15
WALL_COLLISION_RADIUS = CELL_SIZE * 1.45

HOME_SCAN_RADIUS = CELL_SIZE * 3.0
PHEROMONE_STRIDE = 1
PHEROMONE_SENSOR_RADIUS = CELL_SIZE * 1.1
PHEROMONE_DEPOSIT_RADIUS = CELL_SIZE * 0.72
FOOD_COLLISION_RADIUS = CELL_SIZE * 1.1
SENSOR_DISTANCE = CELL_SIZE * 4.0
SENSOR_SPACING = 0.9
SENSOR_VECTOR_SCALE = 1.0 / math.hypot(1.0, SENSOR_SPACING)

ANT_SPEED = 2.6
FOOD_STEER = 1.45
HOME_STEER = 1.65
FOOD_PHEROMONE_STEER = 1.45
HOME_PHEROMONE_STEER = 1.55
HOME_GRADIENT_STEER = 1.55
HOME_COMPASS_STEER = 1.8
HOME_SCENT_COMPASS_SUPPRESSION = 0.25
WALL_STEER = 0.10
WALL_COLLISION_RESOLVE = 5.4
WALL_COLLISION_VELOCITY = 1.8
FOOD_COLLISION_RESOLVE = 1.8
FOOD_COLLISION_VELOCITY = 0.6
COLLISION_CORRECTION_MAX = CELL_SIZE * 1.6
WANDER_STEER = 0.82
BOUNDARY_STEER = 3.2

TURN_AROUND_STEER = 3.4
STATE_SWITCH_VELOCITY_DAMPING = 1.0
TRAIL_RUNOUT_FRAMES = 420.0
PHEROMONE_DECAY = 0.965
FOOD_PHEROMONE_DEPOSIT = 0.32
HOME_PHEROMONE_DEPOSIT = 0.022
HOME_PHEROMONE_SOURCE = 2.4
MAX_PHEROMONE = 90.0
PHEROMONE_FOLLOW_THRESHOLD = 0.45
SCENT_WANDER_SUPPRESSION = 0.82
WORLD_BOUNDS = ecs.spatial.Bounds2D(0.0, 0.0, GRID_WIDTH * CELL_SIZE, GRID_HEIGHT * CELL_SIZE)
VOXEL_QUADTREE = ecs.spatial.Quadtree(WORLD_BOUNDS, capacity=16)

fps_last_time: float | None = None
fps_value = float(TARGET_FPS)
world_counts: dict[str, int] = {}
saved_output = False


@dataclass
class AntAgent:
    x: float
    y: float
    vx: float
    vy: float
    sensor_center_x: float
    sensor_center_y: float
    sensor_left_x: float
    sensor_left_y: float
    sensor_right_x: float
    sensor_right_y: float
    wander_phase: float
    wander_rate: float
    home_dir_x: float
    home_dir_y: float
    carrying: float
    trail_age: float
    home_trail: float
    food_trail: float


@dataclass
class AntDecision:
    wall_resolve_x: float = 0.0
    wall_resolve_y: float = 0.0
    food_resolve_x: float = 0.0
    food_resolve_y: float = 0.0
    steer_x: float = 0.0
    steer_y: float = 0.0
    returning: float = 0.0


@dataclass
class GridVoxel:
    gx: float
    gy: float
    x: float
    y: float


@dataclass
class WallVoxel:
    density: float


@dataclass
class FoodVoxel:
    amount: float


@dataclass
class HillVoxel:
    colony: float


@dataclass
class PheromoneVoxel:
    x: float
    y: float
    red_food: float
    red_home: float
    red_home_x: float
    red_home_y: float
    blue_food: float
    blue_home: float
    blue_home_x: float
    blue_home_y: float
    red_home_source: float
    blue_home_source: float


@dataclass
class HudText:
    title: str
    stats: str


def _cell_center(cell: tuple[int, int]) -> tuple[float, float]:
    return ((cell[0] + 0.5) * CELL_SIZE, (cell[1] + 0.5) * CELL_SIZE)


def _manhattan_corridor(
    a: tuple[int, int], b: tuple[int, int], *, width: int = 2
) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    ax, ay = a
    bx, by = b
    for x in range(min(ax, bx), max(ax, bx) + 1):
        for dy in range(-width, width + 1):
            cells.add((x, ay + dy))
    for y in range(min(ay, by), max(ay, by) + 1):
        for dx in range(-width, width + 1):
            cells.add((bx + dx, y))
    return {(x, y) for x, y in cells if 0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT}


def _disk_cells(center: tuple[int, int], radius: int) -> set[tuple[int, int]]:
    cx, cy = center
    out: set[tuple[int, int]] = set()
    radius_sq = radius * radius
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (
                0 <= x < GRID_WIDTH
                and 0 <= y < GRID_HEIGHT
                and (x - cx) * (x - cx) + (y - cy) * (y - cy) <= radius_sq
            ):
                out.add((x, y))
    return out


def _food_voxels() -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for center in FOOD_CLUMPS:
        cells.update(_disk_cells(center, 3))
        cx, cy = center
        cells.update({(cx - 4, cy), (cx + 4, cy), (cx, cy - 4), (cx, cy + 4)})
    return {(x, y) for x, y in cells if 0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT}


def _hill_voxels(center: tuple[int, int]) -> set[tuple[int, int]]:
    return _disk_cells(center, 2)


def _protected_cells() -> set[tuple[int, int]]:
    protected = set(_food_voxels())
    protected.update(_hill_voxels(RED_HILL))
    protected.update(_hill_voxels(BLUE_HILL))
    for hill in (RED_HILL, BLUE_HILL):
        for food in FOOD_CLUMPS:
            protected.update(_manhattan_corridor(hill, food, width=2))
    return protected


def _neighbors4(cell: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    x, y = cell
    return ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))


def _assert_food_reachable_from_hills(walls: set[tuple[int, int]]) -> None:
    blocked = set(walls)
    targets: set[tuple[int, int]] = set(FOOD_CLUMPS)
    for hill in (RED_HILL, BLUE_HILL):
        seen: set[tuple[int, int]] = {hill}
        queue: deque[tuple[int, int]] = deque([hill])
        reached: set[tuple[int, int]] = set()
        while queue:
            x, y = queue.popleft()
            if (x, y) in targets:
                reached.add((x, y))
                if reached == targets:
                    break
            for nx, ny in _neighbors4((x, y)):
                if not (0 <= nx < GRID_WIDTH and 0 <= ny < GRID_HEIGHT):
                    continue
                candidate = (nx, ny)
                if candidate in blocked or candidate in seen:
                    continue
                seen.add(candidate)
                queue.append(candidate)
        if missing := targets - reached:
            raise RuntimeError(f"walls isolate anthill {hill} from food clumps {sorted(missing)!r}")


def _wall_voxels() -> set[tuple[int, int]]:
    rng = random.Random(20260703)
    protected = _protected_cells()
    walls: set[tuple[int, int]] = set()
    for y in range(2, GRID_HEIGHT - 2):
        for x in range(2, GRID_WIDTH - 2):
            cell = (x, y)
            if cell in protected:
                continue
            vein = (x * 17 + y * 31) % 23 == 0 and rng.random() < 0.48
            rubble = rng.random() < 0.035
            if vein or rubble:
                walls.add(cell)
    _assert_food_reachable_from_hills(walls)
    return walls
