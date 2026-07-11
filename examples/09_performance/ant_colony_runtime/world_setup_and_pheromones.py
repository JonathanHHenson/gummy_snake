from __future__ import annotations

import math
import random
from typing import Any

import ant_colony_runtime.configuration as cfg
import gummysnake as gs
from gummysnake import ecs

from .configuration import (
    ANT_SPEED,
    ANTS_PER_COLONY,
    BLUE_ANT_TAG,
    BLUE_HILL,
    BLUE_HILL_TAG,
    CELL_SIZE,
    FOOD_PHEROMONE_DEPOSIT,
    FOOD_TAG,
    GRID_HEIGHT,
    GRID_WIDTH,
    HOME_PHEROMONE_DEPOSIT,
    HOME_PHEROMONE_SOURCE,
    MAX_PHEROMONE,
    PHEROMONE_DECAY,
    PHEROMONE_DEPOSIT_RADIUS,
    PHEROMONE_STRIDE,
    PHEROMONE_TAG,
    RED_ANT_TAG,
    RED_HILL,
    RED_HILL_TAG,
    SENSOR_DISTANCE,
    SENSOR_SPACING,
    WALL_TAG,
    AntAgent,
    AntDecision,
    FoodVoxel,
    GridVoxel,
    HillVoxel,
    PheromoneVoxel,
    WallVoxel,
    _cell_center,
    _food_voxels,
    _hill_voxels,
    _wall_voxels,
)


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
    cfg.world_counts = {
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


@ecs.system_plan(group=("simulation", "simulation_pheromones"))
def update_red_pheromones(
    marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
    ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent],
) -> None:
    _update_pheromone_query(marker, ant, red_colony=True)


@ecs.system_plan(group=("simulation", "simulation_pheromones"))
def update_blue_pheromones(
    marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
    ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent],
) -> None:
    _update_pheromone_query(marker, ant, red_colony=False)
