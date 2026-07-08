"""Temporary ECS perf sketch: Rust systems, branching, events, and 2D primitives.

This sketch keeps simulation and drawing in Rust-executed ECS plans. It covers
parallel systems, serial and parallel action blocks, conditionals, otherwise
branches, event-reader ``for_each``, list-field ``for_each``, Rust expression
UDFs, and ECS canvas primitive commands.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake import ecs
from gummysnake.ecs import canvas as ca
from gummysnake.ecs import types as ecs_t

WIDTH = 900
HEIGHT = 520
TARGET_FPS = 60
PARTICLE_COUNT = 1_600
HOT_ENERGY_THRESHOLD = 0.68
OUTPUT = Path("examples/output/11_temporary_perf_tests/rust_2d_primitives_branching.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

SAVED_OUTPUT = False


@dataclass
class Particle2D:
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    phase: float
    energy: float
    bucket: int


@dataclass
class TrailSamples:
    samples: Annotated[list[float], ecs_t.List(ecs_t.Float64)]


@dataclass
class SparkPulse:
    amount: int


@dataclass
class BranchStats:
    spark_events: int
    hot_rows: int


@ecs.udf
def wave01(value: ecs.Expression[float]) -> ecs.Expression[float]:
    """Plan-build expression UDF that compiles to Rust math at runtime."""

    return value.sin() * 0.5 + 0.5


@ecs.udf
def wrapped(value: ecs.Expression[float], extent: ecs.Expression[float]) -> ecs.Expression[float]:
    """Wrap a positive coordinate into ``[0, extent)`` as an ECS expression."""

    return (value + extent) % extent


def _wave01(value: ecs.Expression) -> ecs.Expression:
    return cast(ecs.Expression, wave01(value))


def _wrapped(value: ecs.Expression, extent: float) -> ecs.Expression:
    return cast(ecs.Expression, wrapped(value, extent))


@ecs.system(parallel=True, group=("simulation", "simulation_motion"))
def integrate_particles(particle: ecs.Query[Particle2D]) -> None:
    state = particle[Particle2D]
    dt = ecs.dt() / (1000.0 / TARGET_FPS)
    shimmer = _wave01(state.phase)
    with ecs.do(parallel=True):
        state.x.set_to(_wrapped(state.x + (state.vx + shimmer * 0.24) * dt, WIDTH))
        state.y.set_to(_wrapped(state.y + (state.vy - shimmer * 0.18) * dt, HEIGHT))
        state.phase.set_to(state.phase + 0.021 + state.radius * 0.0015)


@ecs.system(group=("simulation", "simulation_for_each"))
def fold_trail_samples(particle: ecs.Query[Particle2D, TrailSamples]) -> None:
    state = particle[Particle2D]
    state.energy.set_to(0.16 + _wave01(state.phase * 0.73) * 0.32)
    with ecs.for_each(particle[TrailSamples].samples) as sample:
        state.energy.increase_by(sample * 0.055)


@ecs.system(group=("simulation", "simulation_branching"))
def branch_particle_state(
    particle: ecs.Query[Particle2D], writer: ecs.EventWriter[SparkPulse]
) -> None:
    state = particle[Particle2D]
    with ecs.conditional():
        with ecs.when(state.energy > HOT_ENERGY_THRESHOLD):
            state.vx.set_to((state.vx * 0.985 - state.vy * 0.012).clamp(-3.2, 3.2))
            state.vy.set_to((state.vy * 0.985 + state.vx * 0.012).clamp(-3.2, 3.2))
            writer.emit(SparkPulse(1))
        with ecs.when(state.energy < 0.26):
            state.vx.set_to(state.vx * 1.006)
            state.vy.set_to(state.vy * 1.006)
        with ecs.otherwise():
            state.phase.increase_by(0.006)


@ecs.system(group=("simulation", "simulation_events"))
def consume_sparks(reader: ecs.EventReader[SparkPulse], stats: ecs.ResMut[BranchStats]) -> None:
    stats[BranchStats].spark_events.set_to(0)
    stats[BranchStats].hot_rows.set_to(0)
    with ecs.for_each(reader) as event:
        stats[BranchStats].spark_events.increase_by(event.amount)
        stats[BranchStats].hot_rows.increase_by(event.amount)


@ecs.system(group=("draw", "draw_background"))
def draw_background() -> None:
    ca.background(7, 9, 18)
    ca.no_stroke()
    ca.fill(16, 19, 34)
    ca.rect(0, 0, WIDTH, HEIGHT)


@ecs.system(group=("draw", "draw_particles"))
def draw_particles(particle: ecs.Query[Particle2D]) -> None:
    state = particle[Particle2D]
    pulse = _wave01(state.phase * 1.7)
    ca.fill(
        70 + state.bucket * 35,
        150 + pulse * 70,
        255 - state.bucket * 18,
        72 + state.energy * 160,
    )
    ca.circle(state.x, state.y, state.radius * (1.2 + state.energy))
    with ecs.conditional(), ecs.when(state.energy > HOT_ENERGY_THRESHOLD):
        ca.fill(255, 242, 166, 120)
        ca.circle(state.x, state.y, state.radius * 3.2)


@ecs.system(group=("draw", "draw_hud"))
def draw_hud(stats: ecs.Res[BranchStats]) -> None:
    ca.fill(230, 240, 255, 218)
    ca.text_size(15)
    ca.text("Rust ECS 2D branching: do/parallel/conditional/for_each/events/UDFs", 22, 30)
    ca.text("spark events", 22, HEIGHT - 42)
    ca.text(stats[BranchStats].spark_events, 122, HEIGHT - 42)
    ca.text("hot rows", 22, HEIGHT - 22)
    ca.text(stats[BranchStats].hot_rows, 122, HEIGHT - 22)


@ecs.system(python=True, group="export")
def save_frame() -> None:
    global SAVED_OUTPUT
    if SAVED_OUTPUT:
        return
    save_once(ARGS, 0, gs.save_canvas)
    SAVED_OUTPUT = True


def _seed_particles() -> None:
    rng = random.Random(1117)
    for index in range(PARTICLE_COUNT):
        angle = rng.random() * math.tau
        speed = rng.uniform(0.38, 1.85)
        radius = rng.uniform(2.0, 4.9)
        samples = [rng.random() for _ in range(3 + index % 5)]
        gs.add_entity(
            Particle2D(
                x=rng.uniform(0, WIDTH),
                y=rng.uniform(0, HEIGHT),
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                radius=radius,
                phase=rng.random() * math.tau,
                energy=0.4,
                bucket=index % 5,
            ),
            TrailSamples(samples),
        )


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT)
    gs.frame_rate(TARGET_FPS)
    gs.describe("Rust ECS branching, UDFs, events, and ECS canvas primitive drawing.")
    gs.configure_ecs(strict=False, warn_on_ambiguity=False)
    gs.set_resource(BranchStats(0, 0))
    gs.order(["simulation", "draw", "export"])
    gs.order(
        [
            "simulation_motion",
            "simulation_for_each",
            "simulation_branching",
            "simulation_events",
        ]
    )
    gs.order(["draw_background", "draw_particles", "draw_hud"])
    gs.add_system(integrate_particles)
    gs.add_system(fold_trail_samples)
    gs.add_system(branch_particle_state)
    gs.add_system(consume_sparks)
    gs.add_system(draw_background)
    gs.add_system(draw_particles)
    gs.add_system(draw_hud)
    gs.add_system(save_frame)
    _seed_particles()


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
