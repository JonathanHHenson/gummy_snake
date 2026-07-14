"""ECS performance scenario: Python systems, Python UDFs, and 2D sprites.

This sketch deliberately uses explicit Python ECS runtime boundaries. The Python
simulation system mutates materialized entity views, a Python UDF mutates the
same component type from a Rust-authored system plan, a Python iterable UDF feeds
``ecs.for_each``, and drawing is done from a Python ECS system with normal
``gs.*`` sprite APIs.
"""

from __future__ import annotations

import math
import random
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake import ecs
from gummysnake.ecs.logical_plan.actions import UdfIterableSource

WIDTH = 900
HEIGHT = 520
TARGET_FPS = 60
SPRITE_COUNT = 900
OUTPUT = Path("examples/output/09_performance/ecs_scenarios/python_systems_udfs_sprites.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

SPRITE_TAG = "sprite_agent"
SPRITE_SIZE = 18
SAVED_OUTPUT = False
SPRITE_IMAGE: Any | None = None
FPS_LAST_TIME: float | None = None
FPS_VALUE = float(TARGET_FPS)


@dataclass
class SpriteAgent:
    x: float
    y: float
    vx: float
    vy: float
    phase: float
    spin: float
    scale: float
    bucket: int


@dataclass
class SpriteStats:
    offset_sum: float


@ecs.udf(mutations={"items": {ecs.EntityMutation[SpriteAgent](update=True)}})
def python_boost_sprites(items: Iterable[ecs.Entity[SpriteAgent]]) -> None:
    """Explicit Python UDF action boundary used for materialized mutations."""

    for index, entity in enumerate(items):
        sprite = entity[SpriteAgent]
        pulse = 0.5 + 0.5 * math.sin(sprite.phase * 1.7 + index * 0.013)
        sprite.scale = 0.68 + pulse * 0.54
        if index % 37 == 0:
            sprite.vx += math.cos(sprite.phase) * 0.018
            sprite.vy += math.sin(sprite.phase) * 0.018


@ecs.udf
def python_wave_offsets() -> Iterable[float]:
    """Iterable Python UDF source consumed by a Rust ``ecs.for_each`` plan."""

    return (-0.35, 0.1, 0.45, 0.8)


@ecs.system(group="python_simulation")
def update_sprites(sprites: ecs.Query[SpriteAgent]) -> None:
    dt = 1.0
    for entity in sprites:
        sprite = entity[SpriteAgent]
        sprite.x += sprite.vx * dt
        sprite.y += sprite.vy * dt
        sprite.phase += 0.024 + sprite.spin * 0.002
        if sprite.x < 10.0 or sprite.x > WIDTH - 10.0:
            sprite.vx *= -1.0
            sprite.x = min(max(sprite.x, 10.0), WIDTH - 10.0)
        if sprite.y < 10.0 or sprite.y > HEIGHT - 10.0:
            sprite.vy *= -1.0
            sprite.y = min(max(sprite.y, 10.0), HEIGHT - 10.0)


@ecs.system_plan(group="python_udf_action")
def run_python_udf(sprite: ecs.Query[ecs.Tag[SPRITE_TAG], SpriteAgent]) -> None:
    python_boost_sprites(sprite)


@ecs.system_plan(group="python_udf_iterable")
def fold_python_iterable(stats: ecs.ResMut[SpriteStats]) -> None:
    stats[SpriteStats].offset_sum.set_to(0.0)
    with ecs.for_each(cast(UdfIterableSource, python_wave_offsets())) as offset:
        stats[SpriteStats].offset_sum.increase_by(offset)


@ecs.system(group=("draw", "draw_background"))
def draw_background() -> None:
    gs.background(10, 12, 24)
    gs.no_stroke()
    for band in range(7):
        shade = 16 + band * 7
        gs.fill(shade, 20 + band * 4, 44 + band * 10, 165)
        gs.rect(0, HEIGHT - 42 - band * 42, WIDTH, 44)


@ecs.system(group=("draw", "draw_sprites"))
def draw_sprites() -> None:
    if SPRITE_IMAGE is None:
        return
    draw_image = gs.fast().image
    for x, y, scale in gs.iter_component_fields(SpriteAgent, "x", "y", "scale"):
        size = SPRITE_SIZE * scale
        draw_image(SPRITE_IMAGE, x, y, size, size)


@ecs.system(group=("draw", "draw_hud"))
def draw_hud(stats: ecs.Res[SpriteStats]) -> None:
    global FPS_LAST_TIME, FPS_VALUE
    now = perf_counter()
    if FPS_LAST_TIME is not None:
        elapsed = now - FPS_LAST_TIME
        if elapsed > 0.0:
            FPS_VALUE += (1.0 / elapsed - FPS_VALUE) * 0.12
    FPS_LAST_TIME = now
    diagnostics = gs.ecs_diagnostics()
    stats_view = cast(Any, stats)
    gs.fill(232, 241, 255, 224)
    gs.text_size(15)
    gs.text("Python ECS systems + Python UDFs + normal gs.image sprite drawing", 22, 30)
    gs.text(
        f"fps {FPS_VALUE:5.1f} | python systems {diagnostics.get('ecs_python_system_calls', 0)} "
        f"| udf calls {diagnostics.get('ecs_udf_calls', 0)} "
        f"| iterable sum {stats_view.offset_sum:.2f}",
        22,
        HEIGHT - 24,
    )


@ecs.system(group="export")
def save_frame() -> None:
    global SAVED_OUTPUT
    if SAVED_OUTPUT:
        return
    save_once(ARGS, 0, gs.save_canvas)
    SAVED_OUTPUT = True


def _make_sprite_image() -> Any:
    image = gs.create_image(SPRITE_SIZE, SPRITE_SIZE)
    center = (SPRITE_SIZE - 1) * 0.5
    for y in range(SPRITE_SIZE):
        for x in range(SPRITE_SIZE):
            dx = x - center
            dy = y - center
            distance = math.hypot(dx, dy) / center
            if distance > 1.0:
                image.set(x, y, (0, 0, 0, 0))
                continue
            alpha = int((1.0 - distance) ** 0.7 * 255)
            image.set(x, y, (126, 226, 255, alpha))
    return image


def _seed_sprites() -> None:
    rng = random.Random(2129)
    for index in range(SPRITE_COUNT):
        angle = rng.random() * math.tau
        speed = rng.uniform(0.35, 1.85)
        gs.add_entity(
            SpriteAgent(
                x=rng.uniform(18, WIDTH - 18),
                y=rng.uniform(18, HEIGHT - 18),
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                phase=rng.random() * math.tau,
                spin=rng.uniform(-1.4, 1.4),
                scale=1.0,
                bucket=index % 6,
            ),
            tags=[SPRITE_TAG],
        )


@gs.setup
def setup() -> None:
    global SPRITE_IMAGE
    gs.create_canvas(WIDTH, HEIGHT)
    gs.frame_rate(TARGET_FPS)
    gs.describe("Explicit Python ECS systems/UDFs drawing many in-memory sprites.")
    gs.image_mode(gs.CENTER)
    gs.configure_ecs(strict=False, warn_on_ambiguity=False)
    gs.set_resource(SpriteStats(0.0))
    gs.order(
        [
            "python_simulation",
            "python_udf_action",
            "python_udf_iterable",
            "draw",
            "export",
        ]
    )
    gs.order(["draw_background", "draw_sprites", "draw_hud"])
    gs.add_system(update_sprites)
    gs.add_system(run_python_udf)
    gs.add_system(fold_python_iterable)
    gs.add_system(draw_background)
    gs.add_system(draw_sprites)
    gs.add_system(draw_hud)
    gs.add_system(save_frame)
    SPRITE_IMAGE = _make_sprite_image()
    _seed_sprites()


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
