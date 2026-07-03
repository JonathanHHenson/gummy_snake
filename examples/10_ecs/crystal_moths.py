"""ECS crystal moths orbiting lanterns with spatial light-field joins."""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence
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
TARGET_FPS = 60
MOTH_COUNT = 48
MOTH = "Moth"
LANTERN = "Lantern"
LIGHT_RADIUS = 245.0
ORBIT_RADIUS = 54.0
MAX_SPEED = 150.0


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
class Navigation:
    phase: float
    orbit: float
    curiosity: float


@dataclass
class Bounds:
    width: float
    height: float
    padding: float


def _expr_length(x: ecs.Expression, y: ecs.Expression) -> ecs.Expression:
    return (x * x + y * y).sqrt()


def _expr_limit_vector(
    x: ecs.Expression, y: ecs.Expression, maximum: float
) -> tuple[ecs.Expression, ecs.Expression]:
    speed = _expr_length(x, y)
    scale = maximum / speed.clamp_min(maximum)
    return x * scale, y * scale


@ecs.system
def lantern_navigation(
    moth: ecs.Query[ecs.Tag[MOTH], Position, Velocity, Spark, Navigation],
    lantern: ecs.Query[ecs.Tag[LANTERN], Position],
) -> None:
    """Steer moths using a spatial light field.

    The attraction term pulls each moth toward nearby lanterns, while the
    tangential term mimics constant-bearing navigation and makes moths spiral
    around lights instead of flying straight into them.
    """

    seconds = ecs.dt() / 1000.0
    light = ecs.spatial.join(
        moth,
        lantern,
        origin_position=ecs.spatial.point2(moth[Position].x, moth[Position].y),
        target_position=ecs.spatial.point2(lantern[Position].x, lantern[Position].y),
        radius=LIGHT_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=LIGHT_RADIUS, dimensions=2),
        allow_fallback=False,
        name="moth_lantern_light_field",
    )

    close_light = ecs.spatial.join(
        moth,
        lantern,
        origin_position=ecs.spatial.point2(moth[Position].x, moth[Position].y),
        target_position=ecs.spatial.point2(lantern[Position].x, lantern[Position].y),
        radius=ORBIT_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=ORBIT_RADIUS, dimensions=2),
        allow_fallback=False,
        name="moth_lantern_close_field",
    )

    away_x = light.sum(-light.delta.x / light.distance.clamp_min(16.0))
    away_y = light.sum(-light.delta.y / light.distance.clamp_min(16.0))
    repel_x = close_light.sum(-close_light.delta.x / close_light.distance.clamp_min(16.0))
    repel_y = close_light.sum(-close_light.delta.y / close_light.distance.clamp_min(16.0))
    glow = (light.count() * 0.24 + close_light.count() * 0.56).clamp(0.0, 1.0)

    pull_x = -away_x
    pull_y = -away_y
    tangent_x = away_y
    tangent_y = -away_x

    phase = moth[Navigation].phase
    curiosity = moth[Navigation].curiosity
    wing_jitter_x = (phase.sin() * 0.72 + (phase * 0.41).cos() * 0.38) * (30.0 + curiosity * 18.0)
    wing_jitter_y = ((phase * 1.33).cos() * 0.68 - (phase * 0.57).sin() * 0.42) * (
        28.0 + curiosity * 14.0
    )

    acceleration_x = (
        pull_x * (58.0 + curiosity * 28.0)
        + tangent_x * moth[Navigation].orbit * (104.0 + glow * 64.0)
        + repel_x * 145.0
        + wing_jitter_x
    )
    acceleration_y = (
        pull_y * (58.0 + curiosity * 28.0)
        + tangent_y * moth[Navigation].orbit * (104.0 + glow * 64.0)
        + repel_y * 145.0
        + wing_jitter_y
    )

    next_dx, next_dy = _expr_limit_vector(
        (moth[Velocity].dx + acceleration_x * seconds) * 0.991,
        (moth[Velocity].dy + acceleration_y * seconds) * 0.991,
        MAX_SPEED,
    )

    with ecs.do(parallel=True):
        moth[Velocity].dx.set_to(next_dx)
        moth[Velocity].dy.set_to(next_dy)
        moth[Spark].heat.set_to((moth[Spark].heat * 0.90 + glow * 0.24).clamp(0.06, 1.0))


@ecs.system
def flutter(moth: ecs.Query[ecs.Tag[MOTH], Position, Velocity, Spark, Navigation]) -> None:
    seconds = ecs.dt() / 1000.0
    wing_speed = 7.0 + moth[Navigation].curiosity * 3.4 + moth[Spark].heat * 8.0
    with ecs.do(parallel=True):
        moth[Position].x.set_to(moth[Position].x + moth[Velocity].dx * seconds)
        moth[Position].y.set_to(moth[Position].y + moth[Velocity].dy * seconds)
        moth[Navigation].phase.set_to(moth[Navigation].phase + wing_speed * seconds)


@ecs.system
def wrap_moths(moth: ecs.Query[ecs.Tag[MOTH], Position], bounds: ecs.Res[Bounds]) -> None:
    left = -bounds[Bounds].padding
    right = bounds[Bounds].width + bounds[Bounds].padding
    top = -bounds[Bounds].padding
    bottom = bounds[Bounds].height + bounds[Bounds].padding
    with ecs.do(parallel=True):
        with ecs.conditional():
            with ecs.when(moth[Position].x < left):
                moth[Position].x.set_to(right)
            with ecs.when(moth[Position].x > right):
                moth[Position].x.set_to(left)
        with ecs.conditional():
            with ecs.when(moth[Position].y < top):
                moth[Position].y.set_to(bottom)
            with ecs.when(moth[Position].y > bottom):
                moth[Position].y.set_to(top)


def _seed_moth(index: int) -> tuple[Position, Velocity, Spark, Navigation]:
    angle = index * 0.79
    lane = index % 8
    radius_x = 180.0 + (lane % 4) * 38.0
    radius_y = 92.0 + (lane // 2) * 20.0
    x = WIDTH * 0.5 + math.cos(angle) * radius_x + math.sin(index * 1.7) * 18.0
    y = HEIGHT * 0.52 + math.sin(angle * 1.18) * radius_y + math.cos(index * 0.9) * 16.0
    speed = 36.0 + (index % 7) * 7.0
    dx = math.cos(angle + math.pi * 0.5) * speed
    dy = math.sin(angle + math.pi * 0.5) * speed * 0.76
    heat = 0.16 + (index % 6) * 0.045
    size = 6.8 + (index % 5) * 1.15
    orbit = -1.0 if index % 2 else 1.0
    curiosity = 0.62 + (index % 9) * 0.085
    phase = index * 0.73
    return Position(x, y), Velocity(dx, dy), Spark(heat, size), Navigation(phase, orbit, curiosity)


def _draw_backdrop(frame: int) -> None:
    gs.background(16, 12, 34)
    with gs.style(stroke=None):
        for band in range(8):
            shade = 20 + band * 6
            gs.fill(shade, 17 + band * 5, 48 + band * 10, 176)
            gs.rect(0, HEIGHT - 38 - band * 34, WIDTH, 38)

        # Slow, crystalline parallax glints in the cavern walls.
        for shard in range(18):
            x = (shard * 47 + 18) % WIDTH
            y = 46 + (shard * 71) % (HEIGHT - 90)
            shimmer = 0.5 + 0.5 * math.sin(frame * 0.035 + shard * 0.9)
            gs.fill(88, 92, 170, int(24 + shimmer * 34))
            gs.triangle(x, y - 18, x - 10, y + 20, x + 13, y + 12)


def _draw_lanterns(lanterns: Sequence[ecs.EntityView], frame: int) -> None:
    with gs.style(stroke=None):
        for index, lantern in enumerate(lanterns):
            pos = lantern[Position]
            pulse = 0.5 + 0.5 * math.sin(frame * 0.045 + index * 1.3)
            gs.fill(123, 68, 255, 24 + int(pulse * 16))
            gs.circle(pos.x, pos.y, 282 + pulse * 18)
            gs.fill(75, 229, 255, 32 + int(pulse * 18))
            gs.circle(pos.x, pos.y, 178 + pulse * 14)
            gs.fill(255, 228, 145, 36 + int(pulse * 20))
            gs.circle(pos.x, pos.y, 94 + pulse * 8)

            gs.fill(34, 43, 92, 220)
            gs.rect(pos.x - 18, pos.y + 24, 36, 12)
            gs.fill(47, 219, 255, 188)
            gs.triangle(pos.x, pos.y - 31, pos.x - 25, pos.y + 24, pos.x + 25, pos.y + 24)
            gs.fill(156, 104, 255, 150)
            gs.triangle(pos.x, pos.y - 25, pos.x - 9, pos.y + 19, pos.x + 8, pos.y + 19)
            gs.fill(255, 248, 190, 232)
            gs.circle(pos.x, pos.y, 22 + pulse * 3)
            gs.fill(255, 255, 255, 248)
            gs.circle(pos.x, pos.y, 8 + pulse * 1.5)


def _draw_moths(moths: Sequence[ecs.EntityView]) -> None:
    with gs.style(stroke=None):
        for moth in moths:
            pos = moth[Position]
            vel = moth[Velocity]
            spark = moth[Spark]
            nav = moth[Navigation]
            speed = math.hypot(vel.dx, vel.dy)
            heading = math.atan2(vel.dy, vel.dx) if speed > 1.0 else 0.0
            wingbeat = math.sin(nav.phase * 2.4)
            wing = spark.size * (1.2 + spark.heat * 0.48)
            body = max(4.4, spark.size * 0.78)
            glow = spark.size * (4.0 + spark.heat * 4.0)
            alpha = int(88 + spark.heat * 142)

            if speed > 1.0:
                trail = min(32.0, speed * 0.13) * (0.72 + spark.heat * 0.45)
                gs.stroke(69, 219, 255, int(28 + spark.heat * 54))
                gs.line(
                    pos.x - vel.dx / speed * trail, pos.y - vel.dy / speed * trail, pos.x, pos.y
                )

            with gs.pushed():
                gs.translate(pos.x, pos.y)
                gs.rotate(heading)
                gs.fill(78, 206, 255, int(14 + spark.heat * 34))
                gs.no_stroke()
                gs.circle(0, 0, glow)

                left_open = 0.76 + wingbeat * 0.20
                right_open = 0.76 - wingbeat * 0.20
                gs.fill(156, 111, 255, alpha)
                gs.ellipse(-body * 0.12, -wing * 0.38, wing * 1.08, wing * left_open)
                gs.ellipse(-body * 0.12, wing * 0.38, wing * 1.08, wing * right_open)
                gs.fill(112, 232, 255, int(62 + spark.heat * 85))
                gs.ellipse(-body * 0.06, -wing * 0.35, wing * 0.42, wing * 0.24)
                gs.ellipse(-body * 0.06, wing * 0.35, wing * 0.42, wing * 0.24)

                gs.fill(255, 244, 198, 226)
                gs.ellipse(0, 0, body * 1.3, body * 0.58)
                gs.fill(255, 255, 255, 238)
                gs.circle(body * 0.56, 0, max(2.5, body * 0.38))
                gs.stroke(210, 238, 255, 128)
                gs.line(body * 0.52, -1.0, body * 0.98, -body * 0.34)
                gs.line(body * 0.52, 1.0, body * 0.98, body * 0.34)


def _draw_hud() -> None:
    with gs.style(fill=(221, 236, 255, 194), stroke=None):
        gs.text_size(16)
        gs.text(
            "ECS spatial joins: moths steer by light gradient + constant-bearing orbit",
            22,
            HEIGHT - 24,
        )


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT, pixel_density=2)
    gs.frame_rate(TARGET_FPS)
    gs.describe("Crystal moths spiral around lantern entities using ECS spatial light fields.")
    gs.configure_ecs(strict=True)
    gs.set_resource(Bounds(float(WIDTH), float(HEIGHT), 38.0))
    gs.add_system(lantern_navigation, order=10)
    gs.add_system(flutter, order=20)
    gs.add_system(wrap_moths, order=30)

    for x, y in ((128, 135), (326, 246), (560, 136), (514, 350), (230, 356)):
        gs.add_entity(Position(float(x), float(y)), tags=[LANTERN])

    for index in range(MOTH_COUNT):
        gs.add_entity(*_seed_moth(index), tags=[MOTH])


@gs.draw
def draw() -> None:
    frame = gs.current.frame_count
    _draw_backdrop(frame)

    lanterns = list(gs.iter_entities(Position, tags=[LANTERN]))
    moths = list(gs.iter_entities(Position, Velocity, Spark, Navigation, tags=[MOTH]))

    _draw_lanterns(lanterns, frame)
    _draw_moths(moths)
    _draw_hud()

    save_once(ARGS, frame, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
