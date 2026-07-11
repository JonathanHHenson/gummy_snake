"""Rust physical-plan measurement adapter for the shared ant-colony core."""

from __future__ import annotations

from examples.support.ant_colony.configuration import (
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
from examples.support.ant_colony.simulation import _simulate_ant_query
from examples.support.ant_colony.world import populate_world, update_pheromone_query
from gummysnake import ecs
from gummysnake.ecs.world import EcsWorld


@ecs.system_plan(group="simulation_pheromones")
def update_red_pheromones(
    marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
    ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent],
) -> None:
    update_pheromone_query(marker, ant, red_colony=True)


@ecs.system_plan(group="simulation_pheromones")
def update_blue_pheromones(
    marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
    ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent],
) -> None:
    update_pheromone_query(marker, ant, red_colony=False)


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


def seed_world() -> tuple[EcsWorld, dict[str, int]]:
    """Build the deterministic benchmark world and compile its four Rust plans."""
    world = EcsWorld()
    counts = populate_world(world.add_entity)
    world.order(["simulation_pheromones", "simulation_ants"])
    world.add_system(update_red_pheromones, name="update_red_pheromones")
    world.add_system(update_blue_pheromones, name="update_blue_pheromones")
    world.add_system(simulate_red_ants, name="simulate_red_ants")
    world.add_system(simulate_blue_ants, name="simulate_blue_ants")
    return world, counts
