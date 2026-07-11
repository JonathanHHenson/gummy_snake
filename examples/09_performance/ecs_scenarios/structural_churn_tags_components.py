"""ECS performance scenario: dynamic tag/component churn with visual effects.

Rust ECS systems add and remove a glow component plus a hot tag as entities move
through wave bands. The structure changes are functional: orbs add a
``GlowTrail`` marker when they cross the hot threshold, keep their aura through a
warm hysteresis band, and remove the component/tag when they cool below the cold
threshold.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake import ecs
from gummysnake.ecs import canvas as ca

WIDTH = 900
HEIGHT = 520
TARGET_FPS = 60
ORB_COUNT = 1_400
ACTIVATE_HEAT_THRESHOLD = 0.72
REMOVE_HEAT_THRESHOLD = 0.30
OUTPUT = Path("examples/output/09_performance/ecs_scenarios/structural_churn_tags_components.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

HOT_TAG = "hot_glow"
ORB_TAG = "glow_orb"
SAVED_OUTPUT = False


@dataclass
class OrbState:
    x: float
    y: float
    vx: float
    vy: float
    phase: float
    heat: float
    radius: float
    bucket: int


@dataclass
class GlowTrail:
    marker: int


@dataclass
class ChurnStats:
    active_glows: int


@ecs.system_plan(parallel=True, group=("simulation", "simulation_motion"))
def animate_orbs(orb: ecs.Query[OrbState]) -> None:
    state = orb[OrbState]
    dt = ecs.dt() / (1000.0 / TARGET_FPS)
    heat = (state.phase.sin() * 0.5 + 0.5).clamp(0.0, 1.0)
    state.x.set_to((state.x + state.vx * dt + WIDTH) % WIDTH)
    state.y.set_to((state.y + state.vy * dt + HEIGHT) % HEIGHT)
    state.phase.set_to(state.phase + 0.035 + state.bucket * 0.0009)
    state.heat.set_to(heat)


@ecs.system_plan(group=("structure", "structure_activate"))
def activate_hot_glows(
    orb: ecs.Query[ecs.Tag[ORB_TAG], OrbState, ecs.Without[GlowTrail]],
    stats: ecs.ResMut[ChurnStats],
) -> None:
    entity = cast(Any, orb).entity
    with ecs.conditional(), ecs.when(orb[OrbState].heat > ACTIVATE_HEAT_THRESHOLD):
        entity.add_component(GlowTrail(1))
        entity.add_tag(HOT_TAG)
        stats[ChurnStats].active_glows.increase_by(1)


@ecs.system_plan(group=("structure", "structure_update"))
def update_or_remove_glows(
    orb: ecs.Query[ecs.Tag[ORB_TAG], OrbState, GlowTrail], stats: ecs.ResMut[ChurnStats]
) -> None:
    state = orb[OrbState]
    entity = cast(Any, orb).entity
    with ecs.conditional(), ecs.when(state.heat < REMOVE_HEAT_THRESHOLD):
        entity.remove_component(GlowTrail)
        entity.remove_tag(HOT_TAG)
        stats[ChurnStats].active_glows.decrease_by(1)


@ecs.system_plan(group=("draw", "draw_background"))
def draw_background() -> None:
    ca.background(8, 8, 15)
    ca.no_stroke()
    ca.fill(18, 17, 30)
    ca.rect(0, 0, WIDTH, HEIGHT)


@ecs.system_plan(group=("draw", "draw_glows"))
def draw_glow_halos(orb: ecs.Query[ecs.Tag[HOT_TAG], OrbState, GlowTrail]) -> None:
    state = orb[OrbState]
    heat_ratio = ((state.heat - REMOVE_HEAT_THRESHOLD) / (1.0 - REMOVE_HEAT_THRESHOLD)).clamp(
        0.0, 1.0
    )
    ca.fill(72 + state.bucket * 28, 194 + heat_ratio * 38, 255, 82 + heat_ratio * 148)
    ca.circle(state.x, state.y, state.radius * (7.2 + heat_ratio * 3.2))


@ecs.system_plan(group=("draw", "draw_orbs"))
def draw_orb_cores(orb: ecs.Query[ecs.Tag[ORB_TAG], OrbState]) -> None:
    state = orb[OrbState]
    ca.fill(70 + state.bucket * 25, 110 + state.heat * 116, 230, 145 + state.heat * 92)
    ca.circle(state.x, state.y, state.radius * (1.2 + state.heat * 0.8))


@ecs.system_plan(group=("draw", "draw_hud"))
def draw_hud(stats: ecs.Res[ChurnStats]) -> None:
    ca.fill(234, 243, 255, 224)
    ca.text_size(15)
    ca.text("Structural ECS churn: hot orbs add GlowTrail, cold orbs remove it", 22, 30)
    ca.text("active glow components", 22, HEIGHT - 24)
    ca.text(stats[ChurnStats].active_glows, 188, HEIGHT - 24)


@ecs.system(group="export")
def save_frame() -> None:
    global SAVED_OUTPUT
    if SAVED_OUTPUT:
        return
    save_once(ARGS, 0, gs.save_canvas)
    SAVED_OUTPUT = True


def _seed_orbs() -> None:
    rng = random.Random(3109)
    for index in range(ORB_COUNT):
        angle = rng.random() * math.tau
        speed = rng.uniform(0.32, 1.72)
        gs.add_entity(
            OrbState(
                x=rng.uniform(0, WIDTH),
                y=rng.uniform(0, HEIGHT),
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                phase=rng.random() * math.tau,
                heat=0.0,
                radius=rng.uniform(2.2, 5.2),
                bucket=index % 5,
            ),
            tags=[ORB_TAG],
        )


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT)
    gs.frame_rate(TARGET_FPS)
    gs.describe("Rust ECS structural actions add/remove components and tags for glow rendering.")
    gs.configure_ecs(strict=False, warn_on_ambiguity=False)
    gs.set_resource(ChurnStats(0))
    gs.order(["simulation", "structure", "draw", "export"])
    gs.order(["structure_activate", "structure_update"])
    gs.order(["draw_background", "draw_glows", "draw_orbs", "draw_hud"])
    gs.add_system(animate_orbs)
    gs.add_system(activate_hot_glows)
    gs.add_system(update_or_remove_glows)
    gs.add_system(draw_background)
    gs.add_system(draw_glow_halos)
    gs.add_system(draw_orb_cores)
    gs.add_system(draw_hud)
    gs.add_system(save_frame)
    _seed_orbs()


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
