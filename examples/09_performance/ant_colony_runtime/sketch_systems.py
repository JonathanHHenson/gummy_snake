from __future__ import annotations

from time import perf_counter

import ant_colony_runtime.configuration as cfg
import gummysnake as gs
from examples.common import save_once
from gummysnake import ecs
from gummysnake.ecs import canvas as ca

from .ant_simulation_query import _simulate_ant_query
from .configuration import (
    ARGS,
    BLUE_ANT_TAG,
    BLUE_HILL_TAG,
    CELL_SIZE,
    FOOD_TAG,
    FPS_SMOOTHING,
    GRID_HEIGHT,
    GRID_OFFSET_X,
    GRID_OFFSET_Y,
    GRID_WIDTH,
    HEIGHT,
    PHEROMONE_TAG,
    RED_ANT_TAG,
    RED_HILL_TAG,
    TARGET_FPS,
    WALL_TAG,
    WIDTH,
    AntAgent,
    AntDecision,
    FoodVoxel,
    GridVoxel,
    HillVoxel,
    HudText,
    PheromoneVoxel,
    WallVoxel,
)
from .world_setup_and_pheromones import (
    _prepare_world,
    update_blue_pheromones,
    update_red_pheromones,
)


@ecs.system_plan(group=("simulation", "simulation_ants"))
def simulate_red_ants(
    ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent, AntDecision],
    wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel],
    food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel],
    hill: ecs.Query[ecs.Tag[RED_HILL_TAG], GridVoxel, HillVoxel],
    trail: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
) -> None:
    _simulate_ant_query(ant, wall, food, hill, trail, red_colony=True)


@ecs.system_plan(group=("simulation", "simulation_ants"))
def simulate_blue_ants(
    ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent, AntDecision],
    wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel],
    food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel],
    hill: ecs.Query[ecs.Tag[BLUE_HILL_TAG], GridVoxel, HillVoxel],
    trail: ecs.Query[ecs.Tag[PHEROMONE_TAG], PheromoneVoxel],
) -> None:
    _simulate_ant_query(ant, wall, food, hill, trail, red_colony=False)


def _update_fps() -> float:
    now = perf_counter()
    if cfg.fps_last_time is None:
        cfg.fps_last_time = now
        return cfg.fps_value
    elapsed = now - cfg.fps_last_time
    cfg.fps_last_time = now
    if elapsed <= 0.0:
        return cfg.fps_value
    cfg.fps_value += (1.0 / elapsed - cfg.fps_value) * FPS_SMOOTHING
    return cfg.fps_value


def _hud_text(fps: float) -> HudText:
    return HudText(
        title=f"ECS ants | {cfg.world_counts.get('ants', 0):,} ants | voxel walls + food clumps",
        stats=(
            f"fps {fps:5.1f} | walls {cfg.world_counts.get('walls', 0)} "
            f"food voxels {cfg.world_counts.get('food_voxels', 0)} "
            f"scent voxels {cfg.world_counts.get('pheromone_voxels', 0)}"
        ),
    )


@ecs.system(group="hud")
def update_hud_text() -> None:
    gs.set_resource(_hud_text(_update_fps()))


@ecs.system_plan(group=("draw", "draw_background"))
def draw_background() -> None:
    ca.background(7, 8, 12)
    ca.no_stroke()
    ca.fill(16, 18, 26)
    ca.rect(GRID_OFFSET_X, GRID_OFFSET_Y, GRID_WIDTH * CELL_SIZE, GRID_HEIGHT * CELL_SIZE)


@ecs.system_plan(group=("draw", "draw_walls"))
def draw_walls(wall: ecs.Query[ecs.Tag[WALL_TAG], GridVoxel, WallVoxel]) -> None:
    voxel = wall[GridVoxel]
    ca.fill(68, 72, 86, 240)
    ca.rect(
        voxel.x + GRID_OFFSET_X - CELL_SIZE * 0.5,
        voxel.y + GRID_OFFSET_Y - CELL_SIZE * 0.5,
        CELL_SIZE,
        CELL_SIZE,
    )


@ecs.system_plan(group=("draw", "draw_pheromones"))
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


@ecs.system_plan(group=("draw", "draw_pheromones"))
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


@ecs.system_plan(group=("draw", "draw_food"))
def draw_food(food: ecs.Query[ecs.Tag[FOOD_TAG], GridVoxel, FoodVoxel]) -> None:
    voxel = food[GridVoxel]
    ca.fill(116, 238, 126, 220)
    ca.rect(
        voxel.x + GRID_OFFSET_X - CELL_SIZE * 0.5,
        voxel.y + GRID_OFFSET_Y - CELL_SIZE * 0.5,
        CELL_SIZE,
        CELL_SIZE,
    )


@ecs.system_plan(group=("draw", "draw_hills"))
def draw_red_hill(hill: ecs.Query[ecs.Tag[RED_HILL_TAG], GridVoxel, HillVoxel]) -> None:
    voxel = hill[GridVoxel]
    ca.fill(255, 88, 76, 220)
    ca.rect(
        voxel.x + GRID_OFFSET_X - CELL_SIZE * 0.5,
        voxel.y + GRID_OFFSET_Y - CELL_SIZE * 0.5,
        CELL_SIZE,
        CELL_SIZE,
    )


@ecs.system_plan(group=("draw", "draw_hills"))
def draw_blue_hill(hill: ecs.Query[ecs.Tag[BLUE_HILL_TAG], GridVoxel, HillVoxel]) -> None:
    voxel = hill[GridVoxel]
    ca.fill(82, 148, 255, 220)
    ca.rect(
        voxel.x + GRID_OFFSET_X - CELL_SIZE * 0.5,
        voxel.y + GRID_OFFSET_Y - CELL_SIZE * 0.5,
        CELL_SIZE,
        CELL_SIZE,
    )


@ecs.system_plan(group=("draw", "draw_ants"))
def draw_red_ants(ant: ecs.Query[ecs.Tag[RED_ANT_TAG], AntAgent]) -> None:
    state = ant[AntAgent]
    ca.fill(255, 80, 70, 185)
    ca.circle(state.x + GRID_OFFSET_X, state.y + GRID_OFFSET_Y, 2.1 + state.carrying * 0.9)


@ecs.system_plan(group=("draw", "draw_ants"))
def draw_blue_ants(ant: ecs.Query[ecs.Tag[BLUE_ANT_TAG], AntAgent]) -> None:
    state = ant[AntAgent]
    ca.fill(75, 145, 255, 185)
    ca.circle(state.x + GRID_OFFSET_X, state.y + GRID_OFFSET_Y, 2.1 + state.carrying * 0.9)


@ecs.system_plan(group=("draw", "draw_hud"))
def draw_hud(hud: ecs.Res[HudText]) -> None:
    ca.fill(238, 244, 255, 235)
    ca.text_size(15)
    ca.text(hud[HudText].title, 24, 32)
    ca.text(hud[HudText].stats, 24, HEIGHT - 24)


@ecs.system(group="export")
def save_frame() -> None:
    if cfg.saved_output:
        return
    save_once(ARGS, 0, gs.save_canvas)
    cfg.saved_output = True


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
