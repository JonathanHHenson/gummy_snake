"""ECS crystal moths attracted to lanterns with grouped query joins."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake import ecs

OUTPUT = Path("examples/output/10_ecs/crystal_moths.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

WIDTH = 720
HEIGHT = 460
MOTH = "Moth"
LANTERN = "Lantern"


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Velocity:
    dx: float
    dy: float


@dataclass
class Spark:
    heat: float
    size: float


@dataclass
class Bounds:
    width: float
    height: float
    padding: float


@ecs.system
def flutter(moth: ecs.Query[ecs.Tag[MOTH], Position, Velocity, Spark]) -> ecs.Action:
    seconds = ecs.dt() / 1000.0
    return ecs.do_in_parallel(
        ecs.set(moth[Position].x, moth[Position].x + moth[Velocity].dx * seconds),
        ecs.set(moth[Position].y, moth[Position].y + moth[Velocity].dy * seconds),
        ecs.set(moth[Velocity].dy, moth[Velocity].dy * 0.996),
        ecs.set(moth[Spark].heat, moth[Spark].heat * 0.997),
    )


@ecs.system
def lantern_aura(
    moth: ecs.Query[ecs.Tag[MOTH], Position, Velocity, Spark],
    lantern: ecs.Query[ecs.Tag[LANTERN], Position],
) -> ecs.Action:
    seconds = ecs.dt() / 1000.0
    dx = lantern[Position].x - moth[Position].x
    dy = lantern[Position].y - moth[Position].y
    near_lantern = ((dx * dx + dy * dy) < 13_500).group_by(moth).any()
    return (
        ecs.when(near_lantern)
        .do_in_parallel(
            ecs.set(moth[Spark].heat, 1.0),
            ecs.set(moth[Velocity].dy, moth[Velocity].dy - 16.0 * seconds),
        )
        .otherwise()
        .do(ecs.set(moth[Spark].heat, moth[Spark].heat * 0.985))
    )


@ecs.system
def wrap_moths(moth: ecs.Query[ecs.Tag[MOTH], Position], bounds: ecs.Res[Bounds]) -> ecs.Action:
    left = -bounds[Bounds].padding
    right = bounds[Bounds].width + bounds[Bounds].padding
    top = -bounds[Bounds].padding
    bottom = bounds[Bounds].height + bounds[Bounds].padding
    return ecs.do_in_parallel(
        ecs.when(moth[Position].x < left)
        .do(ecs.set(moth[Position].x, right))
        .when(moth[Position].x > right)
        .do(ecs.set(moth[Position].x, left)),
        ecs.when(moth[Position].y < top)
        .do(ecs.set(moth[Position].y, bottom))
        .when(moth[Position].y > bottom)
        .do(ecs.set(moth[Position].y, top)),
    )


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT, pixel_density=2)
    gs.frame_rate(60)
    gs.describe("Crystal moths glow near lantern entities using ECS grouped joins.")
    gs.configure_ecs(strict=True)
    gs.set_resource(Bounds(float(WIDTH), float(HEIGHT), 32.0))
    gs.add_system(flutter, order=10)
    gs.add_system(lantern_aura, order=20)
    gs.add_system(wrap_moths, order=30)

    for x, y in ((160, 140), (360, 250), (570, 155), (500, 360)):
        gs.add_entity(Position(float(x), float(y)), tags=[LANTERN])

    for i in range(34):
        angle = i * 0.91
        lane = i % 6
        x = 70 + lane * 110 + math.sin(i * 1.7) * 28
        y = 95 + (i % 7) * 47 + math.cos(i * 0.83) * 22
        dx = math.cos(angle) * (13.0 + (i % 4) * 1.8)
        dy = math.sin(angle * 1.3) * 8.0 - 1.2
        heat = 0.22 + (i % 5) * 0.08
        size = 8.0 + (i % 4) * 1.7
        gs.add_entity(Position(x, y), Velocity(dx, dy), Spark(heat, size), tags=[MOTH])


@gs.draw
def draw() -> None:
    gs.background(19, 15, 38)

    # A simple painted cavern backdrop.
    with gs.style(stroke=None):
        for band in range(7):
            shade = 26 + band * 7
            gs.fill(shade, 20 + band * 5, 55 + band * 10, 170)
            gs.rect(0, HEIGHT - 48 - band * 36, WIDTH, 42)

    lanterns = list(gs.iter_entities(Position, tags=[LANTERN]))
    moths = list(gs.iter_entities(Position, Spark, tags=[MOTH]))

    with gs.style(stroke=None):
        for lantern in lanterns:
            x = lantern[Position].x
            y = lantern[Position].y
            gs.fill(123, 68, 255, 34)
            gs.circle(x, y, 238)
            gs.fill(95, 229, 255, 42)
            gs.circle(x, y, 150)
            gs.fill(46, 215, 255, 180)
            gs.triangle(gs.Vector(x, y - 28), gs.Vector(x - 24, y + 24), gs.Vector(x + 24, y + 24))
            gs.fill(255, 248, 190, 230)
            gs.circle(x, y, 22)
            gs.fill(255, 255, 255, 245)
            gs.circle(x, y, 8)

    with gs.style(stroke_weight=1):
        for moth in moths:
            pos = moth[Position]
            spark = moth[Spark]
            wing = spark.size * (1.0 + spark.heat * 0.35)
            glow = spark.size * (3.8 + spark.heat * 3.0)
            alpha = int(70 + spark.heat * 130)
            gs.fill(125, 210, 255, int(20 + spark.heat * 34))
            gs.stroke(149, 225, 255, int(60 + spark.heat * 100))
            gs.circle(pos.x, pos.y, glow)
            gs.fill(172, 106, 255, alpha)
            gs.ellipse(pos.x - wing * 0.45, pos.y, wing, wing * 0.62)
            gs.ellipse(pos.x + wing * 0.45, pos.y, wing, wing * 0.62)
            gs.fill(255, 244, 198, 220)
            gs.circle(pos.x, pos.y, max(3.0, wing * 0.28))

    with gs.style(fill=(221, 236, 255, 190), stroke=None):
        gs.text_size(16)
        gs.text("ECS grouped join: moth glow = any nearby lantern", 22, HEIGHT - 24)

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
