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


def _add_voxel(cell: tuple[int, int], *components: Any, tags: list[str]) -> None:
    x, y = _cell_center(cell)
    gs.add_entity(GridVoxel(float(cell[0]), float(cell[1]), x, y), *components, tags=tags)


def _add_pheromone_voxels(
    walls: set[tuple[int, int]],
    red_hills: set[tuple[int, int]],
    blue_hills: set[tuple[int, int]],
) -> int:
    required_cells = red_hills | blue_hills
    count = 0
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            cell = (x, y)
            if cell in walls:
                continue
            if cell not in required_cells and (
                x % PHEROMONE_STRIDE != 0 or y % PHEROMONE_STRIDE != 0
            ):
                continue
            px, py = _cell_center(cell)
            red_source = HOME_PHEROMONE_SOURCE if cell in red_hills else 0.0
            blue_source = HOME_PHEROMONE_SOURCE if cell in blue_hills else 0.0
            gs.add_entity(
                PheromoneVoxel(
                    x=px,
                    y=py,
                    red_food=0.0,
                    red_home=red_source,
                    red_home_x=0.0,
                    red_home_y=0.0,
                    blue_food=0.0,
                    blue_home=blue_source,
                    blue_home_x=0.0,
                    blue_home_y=0.0,
                    red_home_source=red_source,
                    blue_home_source=blue_source,
                ),
                tags=[PHEROMONE_TAG],
            )
            count += 1
    return count


def _seed_ants(center: tuple[int, int], tag: str, *, seed: int) -> None:
    rng = random.Random(seed)
    cx, cy = _cell_center(center)
    for _ in range(ANTS_PER_COLONY):
        angle = rng.random() * math.tau
        radius = math.sqrt(rng.random()) * CELL_SIZE * 3.0
        speed = rng.uniform(0.2, ANT_SPEED)
        wander_sign = 1.0 if rng.random() < 0.5 else -1.0
        x = cx + math.cos(angle) * radius
        y = cy + math.sin(angle) * radius
        forward_x = math.cos(angle)
        forward_y = math.sin(angle)
        left_x = (forward_x - forward_y * SENSOR_SPACING) / math.hypot(1.0, SENSOR_SPACING)
        left_y = (forward_y + forward_x * SENSOR_SPACING) / math.hypot(1.0, SENSOR_SPACING)
        right_x = (forward_x + forward_y * SENSOR_SPACING) / math.hypot(1.0, SENSOR_SPACING)
        right_y = (forward_y - forward_x * SENSOR_SPACING) / math.hypot(1.0, SENSOR_SPACING)
        gs.add_entity(
            AntAgent(
                x=x,
                y=y,
                vx=forward_x * speed,
                vy=forward_y * speed,
                sensor_center_x=x + forward_x * SENSOR_DISTANCE,
                sensor_center_y=y + forward_y * SENSOR_DISTANCE,
                sensor_left_x=x + left_x * SENSOR_DISTANCE,
                sensor_left_y=y + left_y * SENSOR_DISTANCE,
                sensor_right_x=x + right_x * SENSOR_DISTANCE,
                sensor_right_y=y + right_y * SENSOR_DISTANCE,
                wander_phase=rng.random() * math.tau,
                wander_rate=wander_sign * rng.uniform(0.045, 0.115),
                home_dir_x=-forward_x,
                home_dir_y=-forward_y,
                carrying=0.0,
                trail_age=0.0,
                home_trail=1.0,
                food_trail=0.0,
            ),
            AntDecision(),
            tags=[tag],
        )


def _prepare_world() -> None:
    global world_counts
    walls = _wall_voxels()
    foods = _food_voxels()
    red_hill_cells = _hill_voxels(RED_HILL)
    blue_hill_cells = _hill_voxels(BLUE_HILL)

    for cell in sorted(walls):
        _add_voxel(cell, WallVoxel(1.0), tags=[WALL_TAG])
    for cell in sorted(foods):
        _add_voxel(cell, FoodVoxel(1.0), tags=[FOOD_TAG])
    for cell in sorted(red_hill_cells):
        _add_voxel(cell, HillVoxel(0.0), tags=[RED_HILL_TAG])
    for cell in sorted(blue_hill_cells):
        _add_voxel(cell, HillVoxel(1.0), tags=[BLUE_HILL_TAG])
    pheromone_voxels = _add_pheromone_voxels(walls, red_hill_cells, blue_hill_cells)
    _seed_ants(RED_HILL, RED_ANT_TAG, seed=11)
    _seed_ants(BLUE_HILL, BLUE_ANT_TAG, seed=29)
    world_counts = {
        "ants": ANTS_PER_COLONY * 2,
        "walls": len(walls),
        "food_voxels": len(foods),
        "hill_voxels": len(red_hill_cells) + len(blue_hill_cells),
        "pheromone_voxels": pheromone_voxels,
    }


def _update_pheromone_query(marker: ecs.Query, ant: ecs.Query, *, red_colony: bool) -> None:
    trail = marker[PheromoneVoxel]
    colony_name = "red" if red_colony else "blue"
    trail_point = ecs.spatial.point2(trail.x, trail.y)
    ant_point = ecs.spatial.point2(ant[AntAgent].x, ant[AntAgent].y)
    nearby_ants = ecs.spatial.join(
        marker,
        ant,
        origin_position=trail_point,
        target_position=ant_point,
        radius=PHEROMONE_DEPOSIT_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PHEROMONE_DEPOSIT_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name=f"{colony_name}_ant_pheromone_deposit",
    )
    food_deposit = nearby_ants.sum(nearby_ants.item[AntAgent].food_trail)
    home_deposit = nearby_ants.sum(nearby_ants.item[AntAgent].home_trail)
    home_vector_x_deposit = nearby_ants.sum(nearby_ants.item[AntAgent].home_dir_x)
    home_vector_y_deposit = nearby_ants.sum(nearby_ants.item[AntAgent].home_dir_y)

    if red_colony:
        next_food = (
            trail.red_food * PHEROMONE_DECAY + food_deposit * FOOD_PHEROMONE_DEPOSIT
        ).clamp(0.0, MAX_PHEROMONE)
        next_home = (
            trail.red_home * PHEROMONE_DECAY
            + home_deposit * HOME_PHEROMONE_DEPOSIT
            + trail.red_home_source
        ).clamp(0.0, MAX_PHEROMONE)
        trail.red_food.set_to(next_food)
        trail.red_home.set_to(next_home)
        trail.red_home_x.set_to(
            (
                trail.red_home_x * PHEROMONE_DECAY + home_vector_x_deposit * HOME_PHEROMONE_DEPOSIT
            ).clamp(-MAX_PHEROMONE, MAX_PHEROMONE)
        )
        trail.red_home_y.set_to(
            (
                trail.red_home_y * PHEROMONE_DECAY + home_vector_y_deposit * HOME_PHEROMONE_DEPOSIT
            ).clamp(-MAX_PHEROMONE, MAX_PHEROMONE)
        )
    else:
        next_food = (
            trail.blue_food * PHEROMONE_DECAY + food_deposit * FOOD_PHEROMONE_DEPOSIT
        ).clamp(0.0, MAX_PHEROMONE)
        next_home = (
            trail.blue_home * PHEROMONE_DECAY
            + home_deposit * HOME_PHEROMONE_DEPOSIT
            + trail.blue_home_source
        ).clamp(0.0, MAX_PHEROMONE)
        trail.blue_food.set_to(next_food)
        trail.blue_home.set_to(next_home)
        trail.blue_home_x.set_to(
            (
                trail.blue_home_x * PHEROMONE_DECAY + home_vector_x_deposit * HOME_PHEROMONE_DEPOSIT
            ).clamp(-MAX_PHEROMONE, MAX_PHEROMONE)
        )
        trail.blue_home_y.set_to(
            (
                trail.blue_home_y * PHEROMONE_DECAY + home_vector_y_deposit * HOME_PHEROMONE_DEPOSIT
            ).clamp(-MAX_PHEROMONE, MAX_PHEROMONE)
        )


@ecs.system(group=("simulation", "simulation_pheromones"))
def update_red_pheromones(
    marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
    ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent],
) -> None:
    _update_pheromone_query(marker, ant, red_colony=True)


@ecs.system(group=("simulation", "simulation_pheromones"))
def update_blue_pheromones(
    marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
    ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent],
) -> None:
    _update_pheromone_query(marker, ant, red_colony=False)


def _simulate_ant_query(
    ant: ecs.Query,
    wall: ecs.Query,
    food: ecs.Query,
    hill: ecs.Query,
    trail: ecs.Query,
    *,
    red_colony: bool,
) -> None:
    state = ant[AntAgent]
    decision = ant[AntDecision]
    colony_name = "red" if red_colony else "blue"
    ant_point = ecs.spatial.point2(state.x, state.y)
    wall_point = ecs.spatial.point2(wall[GridVoxel].x, wall[GridVoxel].y)
    food_point = ecs.spatial.point2(food[GridVoxel].x, food[GridVoxel].y)
    hill_point = ecs.spatial.point2(hill[GridVoxel].x, hill[GridVoxel].y)
    center_point = ecs.spatial.point2(state.sensor_center_x, state.sensor_center_y)
    left_point = ecs.spatial.point2(state.sensor_left_x, state.sensor_left_y)
    right_point = ecs.spatial.point2(state.sensor_right_x, state.sensor_right_y)
    trail_point = ecs.spatial.point2(trail[PheromoneVoxel].x, trail[PheromoneVoxel].y)

    walls = ecs.spatial.join(
        ant,
        wall,
        origin_position=ant_point,
        target_position=wall_point,
        radius=WALL_AVOID_RADIUS,
        algorithm=VOXEL_QUADTREE,
        include_self=False,
        allow_fallback=False,
        name="ant_wall_avoidance",
    )
    wall_collisions = ecs.spatial.join(
        ant,
        wall,
        origin_position=ant_point,
        target_position=wall_point,
        radius=WALL_COLLISION_RADIUS,
        algorithm=VOXEL_QUADTREE,
        include_self=False,
        allow_fallback=False,
        name="ant_wall_collision",
    )
    food_contacts = ecs.spatial.join(
        ant,
        food,
        origin_position=ant_point,
        target_position=food_point,
        radius=FOOD_COLLISION_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=FOOD_COLLISION_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name="ant_food_collision",
    )
    hills = ecs.spatial.join(
        ant,
        hill,
        origin_position=ant_point,
        target_position=hill_point,
        radius=HOME_SCAN_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=HOME_SCAN_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name=f"{colony_name}_ant_home_scan",
    )
    center_trails = ecs.spatial.join(
        ant,
        trail,
        origin_position=center_point,
        target_position=trail_point,
        radius=PHEROMONE_SENSOR_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PHEROMONE_SENSOR_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name="ant_center_pheromone_sensor",
    )
    left_trails = ecs.spatial.join(
        ant,
        trail,
        origin_position=left_point,
        target_position=trail_point,
        radius=PHEROMONE_SENSOR_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PHEROMONE_SENSOR_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name="ant_left_pheromone_sensor",
    )
    right_trails = ecs.spatial.join(
        ant,
        trail,
        origin_position=right_point,
        target_position=trail_point,
        radius=PHEROMONE_SENSOR_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PHEROMONE_SENSOR_RADIUS, dimensions=2),
        include_self=False,
        allow_fallback=False,
        name="ant_right_pheromone_sensor",
    )

    current_speed = (state.vx * state.vx + state.vy * state.vy).sqrt().clamp_min(1.0e-6)
    forward_x = state.vx / current_speed
    forward_y = state.vy / current_speed
    left_dir_x = (forward_x - forward_y * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
    left_dir_y = (forward_y + forward_x * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
    right_dir_x = (forward_x + forward_y * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
    right_dir_y = (forward_y - forward_x * SENSOR_SPACING) * SENSOR_VECTOR_SCALE

    wall_push_x = walls.sum(-walls.delta.x / walls.distance.clamp_min(1.0))
    wall_push_y = walls.sum(-walls.delta.y / walls.distance.clamp_min(1.0))
    wall_collision_count = wall_collisions.count()
    wall_contact_push_x = wall_collisions.sum(
        -wall_collisions.delta.x / wall_collisions.distance.clamp_min(1.0)
    )
    wall_contact_push_y = wall_collisions.sum(
        -wall_collisions.delta.y / wall_collisions.distance.clamp_min(1.0)
    )
    wall_contact_length_raw = (
        wall_contact_push_x * wall_contact_push_x + wall_contact_push_y * wall_contact_push_y
    ).sqrt()
    wall_contact_length = wall_contact_length_raw.clamp_min(1.0)

    food_contact_count = food_contacts.count()
    food_contact_push_x = food_contacts.sum(
        -food_contacts.delta.x / food_contacts.distance.clamp_min(1.0)
    )
    food_contact_push_y = food_contacts.sum(
        -food_contacts.delta.y / food_contacts.distance.clamp_min(1.0)
    )
    food_contact_length_raw = (
        food_contact_push_x * food_contact_push_x + food_contact_push_y * food_contact_push_y
    ).sqrt()
    food_contact_length = food_contact_length_raw.clamp_min(1.0)

    food_count = food_contact_count
    hill_count = hills.count()
    inv_food = 1.0 / food_count.clamp_min(1.0)
    inv_hill = 1.0 / hill_count.clamp_min(1.0)
    food_x = food_contacts.sum(food_contacts.item[GridVoxel].x) * inv_food
    food_y = food_contacts.sum(food_contacts.item[GridVoxel].y) * inv_food
    home_x = hills.sum(hills.item[GridVoxel].x) * inv_hill
    home_y = hills.sum(hills.item[GridVoxel].y) * inv_hill

    food_dx = food_x - state.x
    food_dy = food_y - state.y
    food_distance = (food_dx * food_dx + food_dy * food_dy).sqrt().clamp_min(1.0)
    home_dx = home_x - state.x
    home_dy = home_y - state.y
    home_distance = (home_dx * home_dx + home_dy * home_dy).sqrt().clamp_min(1.0)
    home_anchor_x, home_anchor_y = _cell_center(RED_HILL if red_colony else BLUE_HILL)
    home_anchor_dx = home_anchor_x - state.x
    home_anchor_dy = home_anchor_y - state.y
    home_anchor_distance = (
        (home_anchor_dx * home_anchor_dx + home_anchor_dy * home_anchor_dy).sqrt().clamp_min(1.0)
    )

    if red_colony:
        center_food_scent = center_trails.sum(center_trails.item[PheromoneVoxel].red_food)
        left_food_scent = left_trails.sum(left_trails.item[PheromoneVoxel].red_food)
        right_food_scent = right_trails.sum(right_trails.item[PheromoneVoxel].red_food)
        center_home_scent = center_trails.sum(center_trails.item[PheromoneVoxel].red_home)
        left_home_scent = left_trails.sum(left_trails.item[PheromoneVoxel].red_home)
        right_home_scent = right_trails.sum(right_trails.item[PheromoneVoxel].red_home)
        center_home_weighted_x = center_trails.sum(center_trails.item[PheromoneVoxel].red_home_x)
        center_home_weighted_y = center_trails.sum(center_trails.item[PheromoneVoxel].red_home_y)
    else:
        center_food_scent = center_trails.sum(center_trails.item[PheromoneVoxel].blue_food)
        left_food_scent = left_trails.sum(left_trails.item[PheromoneVoxel].blue_food)
        right_food_scent = right_trails.sum(right_trails.item[PheromoneVoxel].blue_food)
        center_home_scent = center_trails.sum(center_trails.item[PheromoneVoxel].blue_home)
        left_home_scent = left_trails.sum(left_trails.item[PheromoneVoxel].blue_home)
        right_home_scent = right_trails.sum(right_trails.item[PheromoneVoxel].blue_home)
        center_home_weighted_x = center_trails.sum(center_trails.item[PheromoneVoxel].blue_home_x)
        center_home_weighted_y = center_trails.sum(center_trails.item[PheromoneVoxel].blue_home_y)

    home_vector_length = (
        (
            center_home_weighted_x * center_home_weighted_x
            + center_home_weighted_y * center_home_weighted_y
        )
        .sqrt()
        .clamp_min(1.0e-6)
    )

    margin = CELL_SIZE * 4.0
    max_x = GRID_WIDTH * CELL_SIZE - CELL_SIZE * 0.5
    max_y = GRID_HEIGHT * CELL_SIZE - CELL_SIZE * 0.5

    wander_noise = state.wander_phase.sin() + (state.wander_phase * 1.618).cos() * 0.55
    wander_angle = wander_noise * 1.35
    wander_cos = wander_angle.cos()
    wander_sin = wander_angle.sin()
    wander_dir_x = forward_x * wander_cos - forward_y * wander_sin
    wander_dir_y = forward_y * wander_cos + forward_x * wander_sin
    next_wander_phase = state.wander_phase + state.wander_rate
    food_scent_total = center_food_scent + left_food_scent + right_food_scent
    home_scent_total = center_home_scent + left_home_scent + right_home_scent

    with ecs.do:
        decision.wall_resolve_x.set_to(0.0)
        decision.wall_resolve_y.set_to(0.0)
        decision.food_resolve_x.set_to(0.0)
        decision.food_resolve_y.set_to(0.0)
        decision.steer_x.set_to(0.0)
        decision.steer_y.set_to(0.0)
        decision.returning.set_to(0.0)
        state.trail_age.set_to(state.trail_age + 1.0)

        with ecs.conditional(), ecs.when(wall_collision_count > 0), ecs.conditional():
            with ecs.when(wall_contact_length_raw >= 1.0):
                decision.wall_resolve_x.set_to(wall_contact_push_x / wall_contact_length)
                decision.wall_resolve_y.set_to(wall_contact_push_y / wall_contact_length)
            with ecs.otherwise():
                decision.wall_resolve_x.set_to(-forward_x)
                decision.wall_resolve_y.set_to(-forward_y)

        with ecs.conditional(), ecs.when(food_contact_count > 0), ecs.conditional():
            with ecs.when(food_contact_length_raw >= 1.0):
                decision.food_resolve_x.set_to(food_contact_push_x / food_contact_length)
                decision.food_resolve_y.set_to(food_contact_push_y / food_contact_length)
            with ecs.otherwise():
                decision.food_resolve_x.set_to(-forward_x)
                decision.food_resolve_y.set_to(-forward_y)

        with ecs.conditional():
            with ecs.when(state.carrying >= 0.5):
                decision.returning.set_to(1.0)
                with ecs.conditional(), ecs.when(hill_count > 0):
                    state.carrying.set_to(0.0)
                    decision.steer_x.set_to(
                        decision.steer_x
                        - state.vx * STATE_SWITCH_VELOCITY_DAMPING
                        - forward_x * TURN_AROUND_STEER
                    )
                    decision.steer_y.set_to(
                        decision.steer_y
                        - state.vy * STATE_SWITCH_VELOCITY_DAMPING
                        - forward_y * TURN_AROUND_STEER
                    )
                    state.trail_age.set_to(0.0)
            with ecs.otherwise(), ecs.conditional(), ecs.when(food_contact_count > 0):
                state.carrying.set_to(1.0)
                decision.returning.set_to(1.0)
                decision.steer_x.set_to(
                    decision.steer_x
                    - state.vx * STATE_SWITCH_VELOCITY_DAMPING
                    - forward_x * TURN_AROUND_STEER
                )
                decision.steer_y.set_to(
                    decision.steer_y
                    - state.vy * STATE_SWITCH_VELOCITY_DAMPING
                    - forward_y * TURN_AROUND_STEER
                )
                state.trail_age.set_to(0.0)

        with ecs.conditional(), ecs.when((decision.returning < 0.5) & (food_count > 0)):
            decision.steer_x.set_to(decision.steer_x + food_dx / food_distance * FOOD_STEER)
            decision.steer_y.set_to(decision.steer_y + food_dy / food_distance * FOOD_STEER)

        with ecs.conditional(), ecs.when((decision.returning >= 0.5) & (hill_count > 0)):
            decision.steer_x.set_to(decision.steer_x + home_dx / home_distance * HOME_STEER)
            decision.steer_y.set_to(decision.steer_y + home_dy / home_distance * HOME_STEER)

        with (
            ecs.conditional(),
            ecs.when(
                (decision.returning < 0.5)
                & (food_count <= 0)
                & (food_scent_total > PHEROMONE_FOLLOW_THRESHOLD)
            ),
            ecs.conditional(),
        ):
            with ecs.when(
                (center_food_scent >= left_food_scent) & (center_food_scent >= right_food_scent)
            ):
                decision.steer_x.set_to(decision.steer_x + forward_x * FOOD_PHEROMONE_STEER)
                decision.steer_y.set_to(decision.steer_y + forward_y * FOOD_PHEROMONE_STEER)
            with ecs.when(
                (left_food_scent > center_food_scent) & (left_food_scent >= right_food_scent)
            ):
                decision.steer_x.set_to(decision.steer_x + left_dir_x * FOOD_PHEROMONE_STEER)
                decision.steer_y.set_to(decision.steer_y + left_dir_y * FOOD_PHEROMONE_STEER)
            with ecs.when(
                (right_food_scent > center_food_scent) & (right_food_scent > left_food_scent)
            ):
                decision.steer_x.set_to(decision.steer_x + right_dir_x * FOOD_PHEROMONE_STEER)
                decision.steer_y.set_to(decision.steer_y + right_dir_y * FOOD_PHEROMONE_STEER)

        with (
            ecs.conditional(),
            ecs.when(
                (decision.returning >= 0.5)
                & (hill_count <= 0)
                & (home_scent_total > PHEROMONE_FOLLOW_THRESHOLD)
            ),
        ):
            with ecs.conditional():
                with ecs.when(
                    (center_home_scent >= left_home_scent) & (center_home_scent >= right_home_scent)
                ):
                    decision.steer_x.set_to(decision.steer_x + forward_x * HOME_PHEROMONE_STEER)
                    decision.steer_y.set_to(decision.steer_y + forward_y * HOME_PHEROMONE_STEER)
                with ecs.when(
                    (left_home_scent > center_home_scent) & (left_home_scent >= right_home_scent)
                ):
                    decision.steer_x.set_to(decision.steer_x + left_dir_x * HOME_PHEROMONE_STEER)
                    decision.steer_y.set_to(decision.steer_y + left_dir_y * HOME_PHEROMONE_STEER)
                with ecs.when(
                    (right_home_scent > center_home_scent) & (right_home_scent > left_home_scent)
                ):
                    decision.steer_x.set_to(decision.steer_x + right_dir_x * HOME_PHEROMONE_STEER)
                    decision.steer_y.set_to(decision.steer_y + right_dir_y * HOME_PHEROMONE_STEER)
            decision.steer_x.set_to(
                decision.steer_x + center_home_weighted_x / home_vector_length * HOME_GRADIENT_STEER
            )
            decision.steer_y.set_to(
                decision.steer_y + center_home_weighted_y / home_vector_length * HOME_GRADIENT_STEER
            )

        with ecs.conditional(), ecs.when((decision.returning >= 0.5) & (hill_count <= 0)):
            decision.steer_x.set_to(
                decision.steer_x + home_anchor_dx / home_anchor_distance * HOME_COMPASS_STEER
            )
            decision.steer_y.set_to(
                decision.steer_y + home_anchor_dy / home_anchor_distance * HOME_COMPASS_STEER
            )
            with ecs.conditional(), ecs.when(home_scent_total > PHEROMONE_FOLLOW_THRESHOLD):
                compass_suppression = HOME_COMPASS_STEER * HOME_SCENT_COMPASS_SUPPRESSION
                decision.steer_x.set_to(
                    decision.steer_x - home_anchor_dx / home_anchor_distance * compass_suppression
                )
                decision.steer_y.set_to(
                    decision.steer_y - home_anchor_dy / home_anchor_distance * compass_suppression
                )

        with ecs.conditional():
            with ecs.when(state.x < margin):
                decision.steer_x.set_to(decision.steer_x + BOUNDARY_STEER)
            with ecs.when(state.x > max_x - margin):
                decision.steer_x.set_to(decision.steer_x - BOUNDARY_STEER)

        with ecs.conditional():
            with ecs.when(state.y < margin):
                decision.steer_y.set_to(decision.steer_y + BOUNDARY_STEER)
            with ecs.when(state.y > max_y - margin):
                decision.steer_y.set_to(decision.steer_y - BOUNDARY_STEER)

        with ecs.conditional():
            with ecs.when(
                (decision.returning >= 0.5) & (home_scent_total <= PHEROMONE_FOLLOW_THRESHOLD)
            ):
                decision.steer_x.set_to(decision.steer_x + wander_dir_x * WANDER_STEER * 0.04)
                decision.steer_y.set_to(decision.steer_y + wander_dir_y * WANDER_STEER * 0.04)
            with ecs.when((decision.returning < 0.5) & (food_count > 0)):
                decision.steer_x.set_to(decision.steer_x + wander_dir_x * WANDER_STEER * 0.15)
                decision.steer_y.set_to(decision.steer_y + wander_dir_y * WANDER_STEER * 0.15)
            with ecs.when(
                (decision.returning < 0.5)
                & (food_count <= 0)
                & (food_scent_total > PHEROMONE_FOLLOW_THRESHOLD)
            ):
                decision.steer_x.set_to(
                    decision.steer_x
                    + wander_dir_x * WANDER_STEER * (1.0 - SCENT_WANDER_SUPPRESSION)
                )
                decision.steer_y.set_to(
                    decision.steer_y
                    + wander_dir_y * WANDER_STEER * (1.0 - SCENT_WANDER_SUPPRESSION)
                )
            with ecs.when(
                (decision.returning < 0.5)
                & (food_count <= 0)
                & (food_scent_total <= PHEROMONE_FOLLOW_THRESHOLD)
            ):
                decision.steer_x.set_to(decision.steer_x + wander_dir_x * WANDER_STEER)
                decision.steer_y.set_to(decision.steer_y + wander_dir_y * WANDER_STEER)

        desired_vx = state.vx + decision.steer_x + wall_push_x * WALL_STEER
        desired_vy = state.vy + decision.steer_y + wall_push_y * WALL_STEER
        desired_speed = (desired_vx * desired_vx + desired_vy * desired_vy).sqrt().clamp_min(1.0e-6)
        speed_scale = ANT_SPEED / desired_speed.clamp_min(ANT_SPEED)
        collision_velocity_x = (
            decision.wall_resolve_x * WALL_COLLISION_VELOCITY
            + decision.food_resolve_x * FOOD_COLLISION_VELOCITY
        )
        collision_velocity_y = (
            decision.wall_resolve_y * WALL_COLLISION_VELOCITY
            + decision.food_resolve_y * FOOD_COLLISION_VELOCITY
        )
        resolved_vx = desired_vx * speed_scale + collision_velocity_x
        resolved_vy = desired_vy * speed_scale + collision_velocity_y
        resolved_speed = (
            (resolved_vx * resolved_vx + resolved_vy * resolved_vy).sqrt().clamp_min(1.0e-6)
        )
        resolved_speed_scale = ANT_SPEED / resolved_speed.clamp_min(ANT_SPEED)
        next_vx = resolved_vx * resolved_speed_scale
        next_vy = resolved_vy * resolved_speed_scale
        collision_resolve_x = (
            decision.wall_resolve_x * WALL_COLLISION_RESOLVE
            + decision.food_resolve_x * FOOD_COLLISION_RESOLVE
        ).clamp(-COLLISION_CORRECTION_MAX, COLLISION_CORRECTION_MAX)
        collision_resolve_y = (
            decision.wall_resolve_y * WALL_COLLISION_RESOLVE
            + decision.food_resolve_y * FOOD_COLLISION_RESOLVE
        ).clamp(-COLLISION_CORRECTION_MAX, COLLISION_CORRECTION_MAX)
        next_x = (state.x + next_vx + collision_resolve_x).clamp(CELL_SIZE * 0.5, max_x)
        next_y = (state.y + next_vy + collision_resolve_y).clamp(CELL_SIZE * 0.5, max_y)
        next_speed = (next_vx * next_vx + next_vy * next_vy).sqrt().clamp_min(1.0e-6)
        next_forward_x = next_vx / next_speed
        next_forward_y = next_vy / next_speed
        next_left_x = (next_forward_x - next_forward_y * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
        next_left_y = (next_forward_y + next_forward_x * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
        next_right_x = (next_forward_x + next_forward_y * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
        next_right_y = (next_forward_y - next_forward_x * SENSOR_SPACING) * SENSOR_VECTOR_SCALE
        trail_raw = (1.0 - state.trail_age / TRAIL_RUNOUT_FRAMES).clamp(0.0, 1.0)
        home_trail_strength = trail_raw * trail_raw
        food_trail_strength = 0.45 + trail_raw * 0.55

        state.x.set_to(next_x)
        state.y.set_to(next_y)
        state.vx.set_to(next_vx)
        state.vy.set_to(next_vy)
        state.wander_phase.set_to(next_wander_phase)
        state.sensor_center_x.set_to(next_x + next_forward_x * SENSOR_DISTANCE)
        state.sensor_center_y.set_to(next_y + next_forward_y * SENSOR_DISTANCE)
        state.sensor_left_x.set_to(next_x + next_left_x * SENSOR_DISTANCE)
        state.sensor_left_y.set_to(next_y + next_left_y * SENSOR_DISTANCE)
        state.sensor_right_x.set_to(next_x + next_right_x * SENSOR_DISTANCE)
        state.sensor_right_y.set_to(next_y + next_right_y * SENSOR_DISTANCE)
        state.home_dir_x.set_to(0.0)
        state.home_dir_y.set_to(0.0)
        state.home_trail.set_to(0.0)
        state.food_trail.set_to(0.0)
        with ecs.conditional():
            with ecs.when(state.carrying < 0.5):
                state.home_dir_x.set_to(-next_forward_x * home_trail_strength)
                state.home_dir_y.set_to(-next_forward_y * home_trail_strength)
                state.home_trail.set_to(home_trail_strength)
            with ecs.otherwise(), ecs.conditional(), ecs.when(trail_raw > 0.0):
                state.food_trail.set_to(food_trail_strength)


@ecs.system(group=("simulation", "simulation_ants"))
def simulate_red_ants(
    ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent, AntDecision],
    wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel],
    food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel],
    hill: ecs.Query[ecs.Tag[RED_HILL_TAG], GridVoxel, HillVoxel],
    trail: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
) -> None:
    _simulate_ant_query(ant, wall, food, hill, trail, red_colony=True)


@ecs.system(group=("simulation", "simulation_ants"))
def simulate_blue_ants(
    ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent, AntDecision],
    wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel],
    food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel],
    hill: ecs.Query[ecs.Tag[BLUE_HILL_TAG], GridVoxel, HillVoxel],
    trail: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
) -> None:
    _simulate_ant_query(ant, wall, food, hill, trail, red_colony=False)


def _update_fps() -> float:
    global fps_last_time, fps_value
    now = perf_counter()
    if fps_last_time is None:
        fps_last_time = now
        return fps_value
    elapsed = now - fps_last_time
    fps_last_time = now
    if elapsed <= 0.0:
        return fps_value
    fps_value += (1.0 / elapsed - fps_value) * FPS_SMOOTHING
    return fps_value


def _hud_text(fps: float) -> HudText:
    return HudText(
        title=f"ECS ants | {world_counts.get('ants', 0):,} ants | voxel walls + food clumps",
        stats=(
            f"fps {fps:5.1f} | walls {world_counts.get('walls', 0)} "
            f"food voxels {world_counts.get('food_voxels', 0)} "
            f"scent voxels {world_counts.get('pheromone_voxels', 0)}"
        ),
    )


@ecs.system(python=True, group="hud")
def update_hud_text() -> None:
    gs.set_resource(_hud_text(_update_fps()))


@ecs.system(group=("draw", "draw_background"))
def draw_background() -> None:
    ca.background(7, 8, 12)
    ca.no_stroke()
    ca.fill(16, 18, 26)
    ca.rect(GRID_OFFSET_X, GRID_OFFSET_Y, GRID_WIDTH * CELL_SIZE, GRID_HEIGHT * CELL_SIZE)


@ecs.system(group=("draw", "draw_walls"))
def draw_walls(wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel]) -> None:
    voxel = wall[GridVoxel]
    ca.fill(68, 72, 86, 240)
    ca.rect(
        voxel.x + GRID_OFFSET_X - CELL_SIZE * 0.5,
        voxel.y + GRID_OFFSET_Y - CELL_SIZE * 0.5,
        CELL_SIZE,
        CELL_SIZE,
    )


@ecs.system(group=("draw", "draw_pheromones"))
def draw_red_pheromones(marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel]) -> None:
    trail = marker[PheromoneVoxel]
    red_signal = trail.red_food + trail.red_home * 0.22
    blue_signal = trail.blue_food + trail.blue_home * 0.22
    ca.fill(255, 92, 72, 56)
    with (
        ecs.conditional(),
        ecs.when((red_signal + blue_signal >= 1.2) & (red_signal >= blue_signal)),
    ):
        ca.rect(trail.x + GRID_OFFSET_X - 2.0, trail.y + GRID_OFFSET_Y - 2.0, 4.0, 4.0)


@ecs.system(group=("draw", "draw_pheromones"))
def draw_blue_pheromones(marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel]) -> None:
    trail = marker[PheromoneVoxel]
    red_signal = trail.red_food + trail.red_home * 0.22
    blue_signal = trail.blue_food + trail.blue_home * 0.22
    ca.fill(72, 144, 255, 56)
    with (
        ecs.conditional(),
        ecs.when((red_signal + blue_signal >= 1.2) & (blue_signal > red_signal)),
    ):
        ca.rect(trail.x + GRID_OFFSET_X - 2.0, trail.y + GRID_OFFSET_Y - 2.0, 4.0, 4.0)


@ecs.system(group=("draw", "draw_food"))
def draw_food(food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel]) -> None:
    voxel = food[GridVoxel]
    ca.fill(116, 238, 126, 220)
    ca.rect(
        voxel.x + GRID_OFFSET_X - CELL_SIZE * 0.5,
        voxel.y + GRID_OFFSET_Y - CELL_SIZE * 0.5,
        CELL_SIZE,
        CELL_SIZE,
    )


@ecs.system(group=("draw", "draw_hills"))
def draw_red_hill(hill: ecs.Query[ecs.Tag[RED_HILL_TAG], GridVoxel, HillVoxel]) -> None:
    voxel = hill[GridVoxel]
    ca.fill(255, 88, 76, 220)
    ca.rect(
        voxel.x + GRID_OFFSET_X - CELL_SIZE * 0.5,
        voxel.y + GRID_OFFSET_Y - CELL_SIZE * 0.5,
        CELL_SIZE,
        CELL_SIZE,
    )


@ecs.system(group=("draw", "draw_hills"))
def draw_blue_hill(hill: ecs.Query[ecs.Tag[BLUE_HILL_TAG], GridVoxel, HillVoxel]) -> None:
    voxel = hill[GridVoxel]
    ca.fill(82, 148, 255, 220)
    ca.rect(
        voxel.x + GRID_OFFSET_X - CELL_SIZE * 0.5,
        voxel.y + GRID_OFFSET_Y - CELL_SIZE * 0.5,
        CELL_SIZE,
        CELL_SIZE,
    )


@ecs.system(group=("draw", "draw_ants"))
def draw_red_ants(ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent]) -> None:
    state = ant[AntAgent]
    ca.fill(255, 80, 70, 185)
    ca.circle(state.x + GRID_OFFSET_X, state.y + GRID_OFFSET_Y, 2.1 + state.carrying * 0.9)


@ecs.system(group=("draw", "draw_ants"))
def draw_blue_ants(ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent]) -> None:
    state = ant[AntAgent]
    ca.fill(75, 145, 255, 185)
    ca.circle(state.x + GRID_OFFSET_X, state.y + GRID_OFFSET_Y, 2.1 + state.carrying * 0.9)


@ecs.system(group=("draw", "draw_hud"))
def draw_hud(hud: ecs.Res[HudText]) -> None:
    ca.fill(238, 244, 255, 235)
    ca.text_size(15)
    ca.text(hud[HudText].title, 24, 32)
    ca.text(hud[HudText].stats, 24, HEIGHT - 24)


@ecs.system(python=True, group="export")
def save_frame() -> None:
    global saved_output
    if saved_output:
        return
    save_once(ARGS, 0, gs.save_canvas)
    saved_output = True


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT)
    gs.frame_rate(TARGET_FPS)
    gs.no_stroke()
    gs.describe(
        "A 2D ECS ant-colony simulation with voxel-grid hills, food, "
        "randomized walls, pheromone scent trails, and 10k ants."
    )
    gs.configure_ecs(strict=False, warn_on_ambiguity=False)
    gs.order(["simulation", "hud", "draw", "export"])
    gs.order(["simulation_pheromones", "simulation_ants"])
    gs.order(
        [
            "draw_background",
            "draw_walls",
            "draw_pheromones",
            "draw_food",
            "draw_hills",
            "draw_ants",
            "draw_hud",
        ]
    )
    gs.add_system(update_red_pheromones)
    gs.add_system(update_blue_pheromones)
    gs.add_system(simulate_red_ants)
    gs.add_system(simulate_blue_ants)
    gs.add_system(update_hud_text)
    gs.add_system(draw_background)
    gs.add_system(draw_walls)
    gs.add_system(draw_red_pheromones)
    gs.add_system(draw_blue_pheromones)
    gs.add_system(draw_food)
    gs.add_system(draw_red_hill)
    gs.add_system(draw_blue_hill)
    gs.add_system(draw_red_ants)
    gs.add_system(draw_blue_ants)
    gs.add_system(draw_hud)
    gs.add_system(save_frame)
    _prepare_world()


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
