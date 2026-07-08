"""Temporary ECS perf sketch: spatial relations, events, and event for_each.

Signals move through beacon fields. Rust systems exercise 2D spatial neighbors,
query joins, AABB overlaps, aggregate expressions, event emission, and
``ecs.for_each`` over event readers.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake import ecs
from gummysnake.ecs import canvas as ca

WIDTH = 900
HEIGHT = 520
TARGET_FPS = 60
SIGNAL_COUNT = 1_200
BEACON_COUNT = 12
OUTPUT = Path("examples/output/11_temporary_perf_tests/spatial_events_for_each_stress.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

SIGNAL_TAG = "spatial_signal"
BEACON_TAG = "spatial_beacon"
SAVED_OUTPUT = False
WORLD_BOUNDS = ecs.spatial.Bounds2D(0.0, 0.0, float(WIDTH), float(HEIGHT))
SIGNAL_GRID = ecs.spatial.HashGrid(cell_size=34.0, dimensions=2)
BEACON_GRID = ecs.spatial.HashGrid(cell_size=160.0, dimensions=2)
OVERLAP_TREE = ecs.spatial.Quadtree(WORLD_BOUNDS, capacity=16)


@dataclass
class Signal2D:
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    pressure: float
    bucket: int


@dataclass
class Beacon2D:
    x: float
    y: float
    radius: float
    pulse: float


@dataclass
class ClusterPulse:
    amount: int


@dataclass
class BeaconPulse:
    amount: int


@dataclass
class SpatialStats:
    cluster_events: int
    beacon_events: int


@ecs.system(parallel=True, group=("simulation", "simulation_motion"))
def move_signals(signal: ecs.Query[ecs.Tag[SIGNAL_TAG], Signal2D]) -> None:
    state = signal[Signal2D]
    dt = ecs.dt() / (1000.0 / TARGET_FPS)
    with ecs.do(parallel=True):
        state.x.set_to((state.x + state.vx * dt + WIDTH) % WIDTH)
        state.y.set_to((state.y + state.vy * dt + HEIGHT) % HEIGHT)
        state.pressure.set_to((state.pressure * 0.72).clamp(0.0, 1.0))


@ecs.system(group=("simulation", "simulation_pull"))
def beacon_pull(
    signal: ecs.Query[ecs.Tag[SIGNAL_TAG], Signal2D],
    beacon: ecs.Query[ecs.Tag[BEACON_TAG], Beacon2D],
) -> None:
    state = signal[Signal2D]
    field = ecs.spatial.join(
        signal,
        beacon,
        origin_position=ecs.spatial.point2(state.x, state.y),
        target_position=ecs.spatial.point2(beacon[Beacon2D].x, beacon[Beacon2D].y),
        radius=170.0,
        algorithm=BEACON_GRID,
        allow_fallback=False,
        name="signal_beacon_join",
    )
    influence = field.count().clamp(0.0, 4.0)
    pull_x = (WIDTH * 0.5 - state.x) * 0.00045 * influence
    pull_y = (HEIGHT * 0.5 - state.y) * 0.00045 * influence
    state.vx.set_to((state.vx * 0.992 + pull_x).clamp(-2.7, 2.7))
    state.vy.set_to((state.vy * 0.992 + pull_y).clamp(-2.7, 2.7))


@ecs.system(group=("simulation", "simulation_neighbors"))
def neighbor_pressure(signal: ecs.Query[ecs.Tag[SIGNAL_TAG], Signal2D]) -> None:
    state = signal[Signal2D]
    neighbors = ecs.spatial.neighbors(
        signal,
        position=ecs.spatial.point2(state.x, state.y),
        radius=34.0,
        algorithm=SIGNAL_GRID,
        include_self=False,
        allow_fallback=False,
        name="signal_neighbors",
    )
    crowd = neighbors.count()
    state.pressure.set_to((state.pressure + crowd * 0.035).clamp(0.0, 1.0))


@ecs.system(group=("simulation", "simulation_overlaps"))
def overlap_beacons(
    signal: ecs.Query[ecs.Tag[SIGNAL_TAG], Signal2D],
    beacon: ecs.Query[ecs.Tag[BEACON_TAG], Beacon2D],
    writer: ecs.EventWriter[BeaconPulse],
) -> None:
    state = signal[Signal2D]
    hits = ecs.spatial.overlaps(
        signal,
        beacon,
        origin_bounds=ecs.spatial.aabb2(
            state.x - state.radius,
            state.y - state.radius,
            state.x + state.radius,
            state.y + state.radius,
        ),
        target_bounds=ecs.spatial.aabb2(
            beacon[Beacon2D].x - beacon[Beacon2D].radius,
            beacon[Beacon2D].y - beacon[Beacon2D].radius,
            beacon[Beacon2D].x + beacon[Beacon2D].radius,
            beacon[Beacon2D].y + beacon[Beacon2D].radius,
        ),
        algorithm=OVERLAP_TREE,
        include_self=False,
        allow_fallback=False,
        name="signal_beacon_overlaps",
    ).count()
    with ecs.conditional(), ecs.when(hits > 0):
        state.pressure.set_to((state.pressure + hits * 0.12).clamp(0.0, 1.0))
        writer.emit(BeaconPulse(1))


@ecs.system(group=("simulation", "simulation_event_emit"))
def emit_cluster_events(
    signal: ecs.Query[ecs.Tag[SIGNAL_TAG], Signal2D], writer: ecs.EventWriter[ClusterPulse]
) -> None:
    with ecs.conditional(), ecs.when(signal[Signal2D].pressure > 0.72):
        writer.emit(ClusterPulse(1))


@ecs.system(group=("simulation", "simulation_event_consume"))
def consume_spatial_events(
    cluster_reader: ecs.EventReader[ClusterPulse],
    beacon_reader: ecs.EventReader[BeaconPulse],
    stats: ecs.ResMut[SpatialStats],
) -> None:
    stats[SpatialStats].cluster_events.set_to(0)
    stats[SpatialStats].beacon_events.set_to(0)
    with ecs.for_each(cluster_reader) as event:
        stats[SpatialStats].cluster_events.increase_by(event.amount)
    with ecs.for_each(beacon_reader) as event:
        stats[SpatialStats].beacon_events.increase_by(event.amount)


@ecs.system(group=("draw", "draw_background"))
def draw_background() -> None:
    ca.background(6, 10, 20)
    ca.no_stroke()
    ca.fill(13, 18, 34)
    ca.rect(0, 0, WIDTH, HEIGHT)


@ecs.system(group=("draw", "draw_beacons"))
def draw_beacons(beacon: ecs.Query[ecs.Tag[BEACON_TAG], Beacon2D]) -> None:
    state = beacon[Beacon2D]
    ca.no_stroke()
    ca.fill(90, 84, 255, 32)
    ca.circle(state.x, state.y, state.radius * 2.0)
    ca.fill(116, 230, 255, 80)
    ca.circle(state.x, state.y, state.radius * 0.82)
    ca.fill(255, 240, 170, 210)
    ca.circle(state.x, state.y, 9 + state.pulse * 2.5)


@ecs.system(group=("draw", "draw_signals"))
def draw_signals(signal: ecs.Query[ecs.Tag[SIGNAL_TAG], Signal2D]) -> None:
    state = signal[Signal2D]
    ca.no_stroke()
    ca.fill(55 + state.bucket * 38, 170 + state.pressure * 70, 255, 58 + state.pressure * 150)
    ca.circle(state.x, state.y, state.radius * (1.15 + state.pressure * 1.8))


@ecs.system(group=("draw", "draw_hud"))
def draw_hud(stats: ecs.Res[SpatialStats]) -> None:
    ca.fill(235, 244, 255, 224)
    ca.text_size(15)
    ca.text("Spatial ECS: neighbors + join + overlaps + events + for_each readers", 22, 30)
    ca.text("cluster events", 22, HEIGHT - 42)
    ca.text(stats[SpatialStats].cluster_events, 128, HEIGHT - 42)
    ca.text("beacon overlaps", 22, HEIGHT - 22)
    ca.text(stats[SpatialStats].beacon_events, 140, HEIGHT - 22)


@ecs.system(python=True, group="export")
def save_frame() -> None:
    global SAVED_OUTPUT
    if SAVED_OUTPUT:
        return
    save_once(ARGS, 0, gs.save_canvas)
    SAVED_OUTPUT = True


def _seed_world() -> None:
    rng = random.Random(4221)
    for index in range(BEACON_COUNT):
        angle = index / BEACON_COUNT * math.tau
        x = WIDTH * 0.5 + math.cos(angle) * WIDTH * 0.34
        y = HEIGHT * 0.5 + math.sin(angle * 1.3) * HEIGHT * 0.28
        gs.add_entity(
            Beacon2D(x=x, y=y, radius=40.0 + (index % 4) * 8.0, pulse=index % 5),
            tags=[BEACON_TAG],
        )
    for index in range(SIGNAL_COUNT):
        angle = rng.random() * math.tau
        speed = rng.uniform(0.45, 2.15)
        gs.add_entity(
            Signal2D(
                x=rng.uniform(0, WIDTH),
                y=rng.uniform(0, HEIGHT),
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                radius=rng.uniform(3.0, 7.5),
                pressure=0.0,
                bucket=index % 5,
            ),
            tags=[SIGNAL_TAG],
        )


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT)
    gs.frame_rate(TARGET_FPS)
    gs.describe("Rust ECS spatial relations, events, and ECS canvas drawing.")
    gs.configure_ecs(strict=False, warn_on_ambiguity=False)
    gs.set_resource(SpatialStats(0, 0))
    gs.order(["simulation", "draw", "export"])
    gs.order(
        [
            "simulation_motion",
            "simulation_pull",
            "simulation_neighbors",
            "simulation_overlaps",
            "simulation_event_emit",
            "simulation_event_consume",
        ]
    )
    gs.order(["draw_background", "draw_beacons", "draw_signals", "draw_hud"])
    gs.add_system(move_signals)
    gs.add_system(beacon_pull)
    gs.add_system(neighbor_pressure)
    gs.add_system(overlap_beacons)
    gs.add_system(emit_cluster_events)
    gs.add_system(consume_spatial_events)
    gs.add_system(draw_background)
    gs.add_system(draw_beacons)
    gs.add_system(draw_signals)
    gs.add_system(draw_hud)
    gs.add_system(save_frame)
    _seed_world()


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
