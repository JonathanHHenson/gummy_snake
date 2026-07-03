"""ECS fireflies that drift, pulse, wrap, and draw a soft constellation."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake import ecs

OUTPUT = Path("examples/output/10_ecs/firefly_constellation.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

WIDTH = 720
HEIGHT = 460
FIREFLY_COUNT = 48


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Velocity:
    dx: float
    dy: float


@dataclass
class Glow:
    radius: float
    energy: float
    pulse: float


@dataclass
class Bounds:
    width: float
    height: float
    padding: float


@dataclass
class Wind:
    x: float
    y: float


@ecs.system
def drift(fly: ecs.Query[Position, Velocity, Glow], wind: ecs.Res[Wind]) -> None:
    seconds = ecs.dt() / 1000.0
    with ecs.do(parallel=True):
        fly[Position].x.set_to(fly[Position].x + (fly[Velocity].dx + wind[Wind].x) * seconds)
        fly[Position].y.set_to(fly[Position].y + (fly[Velocity].dy + wind[Wind].y) * seconds)
        fly[Glow].energy.set_to(fly[Glow].energy + fly[Glow].pulse * seconds)


@ecs.system
def pulse(fly: ecs.Query[Glow]) -> None:
    with ecs.conditional(parallel=True):
        with ecs.when(fly[Glow].energy > 1.0):
            fly[Glow].energy.set_to(1.0)
            fly[Glow].pulse.set_to(-0.65)
        with ecs.when(fly[Glow].energy < 0.25):
            fly[Glow].energy.set_to(0.25)
            fly[Glow].pulse.set_to(0.65)


@ecs.system
def wrap(fly: ecs.Query[Position], bounds: ecs.Res[Bounds]) -> None:
    left = -bounds[Bounds].padding
    right = bounds[Bounds].width + bounds[Bounds].padding
    top = -bounds[Bounds].padding
    bottom = bounds[Bounds].height + bounds[Bounds].padding
    with ecs.do(parallel=True):
        with ecs.conditional():
            with ecs.when(fly[Position].x < left):
                fly[Position].x.set_to(right)
            with ecs.when(fly[Position].x > right):
                fly[Position].x.set_to(left)
        with ecs.conditional():
            with ecs.when(fly[Position].y < top):
                fly[Position].y.set_to(bottom)
            with ecs.when(fly[Position].y > bottom):
                fly[Position].y.set_to(top)


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT, pixel_density=2)
    gs.frame_rate(60)
    gs.describe("A dark sky of ECS-driven fireflies connected into a soft constellation.")
    gs.set_resource(Bounds(float(WIDTH), float(HEIGHT), 36.0))
    gs.set_resource(Wind(5.5, -1.2))
    gs.configure_ecs(strict=True)
    gs.add_system(drift, order=10)
    gs.add_system(pulse, order=20)
    gs.add_system(wrap, order=30)

    center_x = WIDTH / 2
    center_y = HEIGHT / 2
    for i in range(FIREFLY_COUNT):
        angle = i * 2.399963229728653
        ring = 70 + (i % 9) * 23
        wobble = math.sin(i * 0.73) * 18
        x = center_x + math.cos(angle) * (ring + wobble)
        y = center_y + math.sin(angle) * (ring - wobble * 0.45)
        speed = 7.5 + (i % 5) * 1.6
        dx = math.cos(angle + math.pi / 2) * speed
        dy = math.sin(angle + math.pi / 2) * speed
        energy = 0.35 + (i % 7) * 0.08
        pulse_rate = 0.20 + (i % 4) * 0.035
        gs.add_entity(Position(x, y), Velocity(dx, dy), Glow(4.5 + (i % 4), energy, pulse_rate))


@gs.draw
def draw() -> None:
    gs.background(9, 13, 30)
    flies = list(gs.iter_entities(Position, Glow))

    with gs.style(fill=None, stroke_weight=1):
        for index, a in enumerate(flies):
            ax = a[Position].x
            ay = a[Position].y
            for b in flies[index + 1 :]:
                bx = b[Position].x
                by = b[Position].y
                distance_sq = (ax - bx) * (ax - bx) + (ay - by) * (ay - by)
                if distance_sq < 4_200:
                    alpha = int(52 * (1.0 - distance_sq / 4_200))
                    gs.stroke(126, 219, 255, alpha)
                    gs.line(ax, ay, bx, by)

    with gs.style(stroke=None):
        for fly in flies:
            glow = fly[Glow]
            x = fly[Position].x
            y = fly[Position].y
            halo = glow.radius * (4.5 + glow.energy * 2.5)
            core = glow.radius * (0.7 + glow.energy)
            gs.fill(85, 190, 255, int(24 + glow.energy * 24))
            gs.circle(x, y, halo)
            gs.fill(184, 245, 255, int(110 + glow.energy * 120))
            gs.circle(x, y, core)
            gs.fill(255, 250, 181, 230)
            gs.circle(x, y, max(2.2, core * 0.33))

    with gs.style(fill=(185, 231, 255, 190), stroke=None):
        gs.text_size(16)
        gs.text("ECS fireflies: dataclass components + ordered systems", 22, HEIGHT - 24)

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
