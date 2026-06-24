"""Nature of Code-style gravitational attractor performance sketch.

Inspired by Daniel Shiffman's Nature of Code attractor example: many movers feel
an inverse-square pull from a heavier attractor. This version keeps the public
Gummy Snake API hot path busy with thousands of batched circles while preserving
plain Python sketch code.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

WIDTH = 960
HEIGHT = 540
TARGET_FPS = 60
MOVER_COUNT = 2_400
ATTRACTOR_MASS = 100.0
MIN_DISTANCE = 18.0
MAX_DISTANCE = 230.0
MAX_SPEED = 7.5
EDGE_MARGIN = 36.0
FPS_SMOOTHING = 0.12

OUTPUT = Path("examples/output/09_performance/nature_of_code_attractor.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

positions_x: list[float] = []
positions_y: list[float] = []
velocities_x: list[float] = []
velocities_y: list[float] = []
masses: list[float] = []
diameters: list[float] = []
bucket_indices: list[list[int]] = []
fps_last_time: float | None = None
fps_value = float(TARGET_FPS)

palette = [
    (100, 180, 255, 112),
    (110, 235, 190, 108),
    (255, 215, 122, 104),
    (255, 132, 132, 100),
    (180, 140, 255, 106),
    (230, 246, 255, 96),
]


def _update_fps() -> float:
    global fps_last_time, fps_value
    now = perf_counter()
    if fps_last_time is None:
        fps_last_time = now
        return fps_value
    elapsed = now - fps_last_time
    fps_last_time = now
    if elapsed <= 0.0:
        return fps_value
    instant_fps = 1.0 / elapsed
    fps_value += (instant_fps - fps_value) * FPS_SMOOTHING
    return fps_value


def _prepare_movers() -> None:
    global bucket_indices
    rng = random.Random(20240624)
    positions_x.clear()
    positions_y.clear()
    velocities_x.clear()
    velocities_y.clear()
    masses.clear()
    diameters.clear()
    bucket_indices = [[] for _ in palette]

    for index in range(MOVER_COUNT):
        angle = rng.random() * math.tau
        radius = 70.0 + rng.random() * 360.0
        x = WIDTH * 0.5 + math.cos(angle) * radius * 1.45
        y = HEIGHT * 0.5 + math.sin(angle) * radius * 0.75
        tangent = angle + math.pi * 0.5
        speed = 0.55 + rng.random() * 2.2
        mass = 0.6 + rng.random() * 2.6
        bucket = index % len(palette)

        positions_x.append(x % WIDTH)
        positions_y.append(y % HEIGHT)
        velocities_x.append(math.cos(tangent) * speed)
        velocities_y.append(math.sin(tangent) * speed)
        masses.append(mass)
        diameters.append(1.8 + mass * 1.45)
        bucket_indices[bucket].append(index)


def _attractor_position(frame: int) -> tuple[float, float]:
    if gs.mouse_is_pressed() and gs.mouse_is_inside_window():
        return (gs.mouse_x(), gs.mouse_y())
    t = frame * 0.018
    return (
        WIDTH * 0.5 + math.cos(t * 0.91) * WIDTH * 0.23,
        HEIGHT * 0.5 + math.sin(t * 1.37) * HEIGHT * 0.24,
    )


def _update_mover(index: int, attractor_x: float, attractor_y: float) -> None:
    x = positions_x[index]
    y = positions_y[index]
    dx = attractor_x - x
    dy = attractor_y - y
    distance_squared = dx * dx + dy * dy
    if distance_squared <= 1e-9:
        return

    distance = math.sqrt(distance_squared)
    constrained_distance = min(max(distance, MIN_DISTANCE), MAX_DISTANCE)
    strength = ATTRACTOR_MASS / (constrained_distance * constrained_distance)
    nx = dx / distance
    ny = dy / distance

    vx = (velocities_x[index] + nx * strength) * 0.997
    vy = (velocities_y[index] + ny * strength) * 0.997
    speed_squared = vx * vx + vy * vy
    max_speed_squared = MAX_SPEED * MAX_SPEED
    if speed_squared > max_speed_squared:
        scale = MAX_SPEED / math.sqrt(speed_squared)
        vx *= scale
        vy *= scale

    x += vx
    y += vy
    if x < -EDGE_MARGIN:
        x = WIDTH + EDGE_MARGIN
    elif x > WIDTH + EDGE_MARGIN:
        x = -EDGE_MARGIN
    if y < -EDGE_MARGIN:
        y = HEIGHT + EDGE_MARGIN
    elif y > HEIGHT + EDGE_MARGIN:
        y = -EDGE_MARGIN

    positions_x[index] = x
    positions_y[index] = y
    velocities_x[index] = vx
    velocities_y[index] = vy


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT)
    gs.frame_rate(TARGET_FPS)
    gs.no_stroke()
    gs.describe(
        "A Nature of Code-inspired gravitational attractor pulling thousands of batched movers."
    )
    _prepare_movers()
    gs.background(3, 5, 13)


@gs.draw
def draw() -> None:
    frame = gs.frame_count()
    fps = _update_fps()
    attractor_x, attractor_y = _attractor_position(frame)
    draw_fast = gs.fast()

    gs.fill(3, 5, 13, 42)
    draw_fast.rect(0, 0, WIDTH, HEIGHT)

    for index in range(MOVER_COUNT):
        _update_mover(index, attractor_x, attractor_y)

    for bucket, indices in enumerate(bucket_indices):
        gs.fill(*palette[bucket])
        for index in indices:
            draw_fast.circle(positions_x[index], positions_y[index], diameters[index])

    gs.fill(255, 238, 170, 46)
    draw_fast.circle(attractor_x, attractor_y, 82)
    gs.fill(255, 236, 142, 160)
    draw_fast.circle(attractor_x, attractor_y, 34)
    gs.fill(255, 248, 220, 240)
    draw_fast.circle(attractor_x, attractor_y, 12)

    gs.fill(238, 244, 255, 235)
    gs.text_size(15)
    gs.text(
        f"Nature of Code attractor | {MOVER_COUNT:,} movers | drag the mouse to steer",
        24,
        32,
    )
    gs.text(f"fps {fps:5.1f} | inverse-square gravity + batched circles", 24, HEIGHT - 24)
    save_once(ARGS, frame, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
