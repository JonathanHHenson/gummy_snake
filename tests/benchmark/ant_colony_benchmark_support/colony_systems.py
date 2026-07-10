from __future__ import annotations

from gummysnake import ecs

from tests.benchmark.ant_colony_benchmark_support.ant_simulation_query import _simulate_ant_query
from tests.benchmark.ant_colony_benchmark_support.configuration import (
    BLUE_ANT_TAG,
    BLUE_HILL_TAG,
    FOOD_TAG,
    PHEROMONE_TAG,
    RED_ANT_TAG,
    RED_HILL_TAG,
    WALL_TAG,
    AntAgent,
    AntDecision,
    FoodVoxel,
    GridVoxel,
    HillVoxel,
    PheromoneVoxel,
    WallVoxel,
)


@ecs.system_plan(group="simulation_ants")
def simulate_red_ants(
    ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent, AntDecision],
    wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel],
    food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel],
    hill: ecs.Query[ecs.Tag[RED_HILL_TAG], GridVoxel, HillVoxel],
    trail: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
) -> None:
    _simulate_ant_query(ant, wall, food, hill, trail, red_colony=True)


@ecs.system_plan(group="simulation_ants")
def simulate_blue_ants(
    ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent, AntDecision],
    wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel],
    food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel],
    hill: ecs.Query[ecs.Tag[BLUE_HILL_TAG], GridVoxel, HillVoxel],
    trail: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
) -> None:
    _simulate_ant_query(ant, wall, food, hill, trail, red_colony=False)
