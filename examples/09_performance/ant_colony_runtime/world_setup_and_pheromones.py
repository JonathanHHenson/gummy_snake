"""Sketch adapter for shared ant-world seeding and pheromone plan construction."""

from __future__ import annotations

import gummysnake as gs
from examples.support.ant_colony.configuration import (
    BLUE_ANT_TAG,
    PHEROMONE_TAG,
    RED_ANT_TAG,
    AntAgent,
    PheromoneVoxel,
)
from examples.support.ant_colony.world import populate_world, update_pheromone_query
from gummysnake import ecs

from . import configuration as cfg


def _prepare_world() -> None:
    cfg.world_counts = populate_world(gs.add_entity)


@ecs.system_plan(group=("simulation", "simulation_pheromones"))
def update_red_pheromones(
    marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
    ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent],
) -> None:
    update_pheromone_query(marker, ant, red_colony=True)


@ecs.system_plan(group=("simulation", "simulation_pheromones"))
def update_blue_pheromones(
    marker: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
    ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent],
) -> None:
    update_pheromone_query(marker, ant, red_colony=False)
