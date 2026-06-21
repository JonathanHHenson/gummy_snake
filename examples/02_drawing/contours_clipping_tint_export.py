"""Contours, clipping, image tint, save_frames, and optional GIF export."""

from __future__ import annotations

import math
import sys
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, should_save

OUTPUT = Path("examples/output/02_drawing/contours_clipping_tint_export.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
STAMP = gs.create_image(42, 42)


def setup() -> None:
    gs.create_canvas(760, 430)
    gs.frame_rate(24)
    for y in range(STAMP.height):
        for x in range(STAMP.width):
            dx = x - STAMP.width / 2
            dy = y - STAMP.height / 2
            distance = math.hypot(dx, dy)
            alpha = max(0, min(255, int(255 - distance * 9)))
            STAMP.set(x, y, (255, 255, 255, alpha))


def star(cx: float, cy: float, outer: float, inner: float, points: int) -> None:
    for i in range(points * 2):
        radius = outer if i % 2 == 0 else inner
        angle = -math.pi / 2 + i * math.pi / points
        gs.vertex(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)


def draw_cutout_badge() -> None:
    gs.no_stroke()
    gs.fill(244, 188, 67)
    gs.circle(150, 180, 82)

    gs.no_stroke()
    gs.fill(42, 87, 143)
    gs.begin_shape()
    star(150, 180, 112, 54, 7)
    gs.begin_contour()
    for i in range(28):
        angle = -math.tau * i / 28
        gs.vertex(150 + math.cos(angle) * 38, 180 + math.sin(angle) * 38)
    gs.end_contour()
    gs.end_shape(gs.CLOSE)


def draw_clipped_field() -> None:
    gs.begin_clip()
    for i in range(36):
        angle = math.tau * i / 36
        wave = 18 * math.sin(angle * 3 + gs.frame_count() * 0.08)
        gs.vertex(430 + math.cos(angle) * (142 + wave), 186 + math.sin(angle) * (96 + wave))
    gs.clip()

    gs.background(238, 242, 232)
    gs.no_stroke()
    for row in range(8):
        for col in range(11):
            x = 294 + col * 29
            y = 82 + row * 29
            gs.fill(40 + col * 16, 104 + row * 10, 174, 210)
            gs.rect(x, y, 22, 22)

    gs.end_clip()
    gs.no_fill()
    gs.stroke(32, 45, 63)
    gs.stroke_weight(3)
    gs.begin_shape()
    for i in range(36):
        angle = math.tau * i / 36
        gs.vertex(430 + math.cos(angle) * 142, 186 + math.sin(angle) * 96)
    gs.end_shape(gs.CLOSE)


def draw_tinted_images() -> None:
    gs.image_mode(gs.CENTER)
    colors = [(227, 88, 75, 230), (45, 150, 112, 220), (247, 183, 60, 210)]
    for i, color in enumerate(colors):
        gs.tint(*color)
        gs.image(STAMP, 610, 128 + i * 58, 62, 62)
    gs.no_tint()
    gs.image(STAMP, 690, 186, 72, 72)
    gs.image_mode(gs.CORNER)


def export_examples() -> None:
    if not should_save(ARGS) or gs.frame_count() != 0:
        return
    ARGS.output.parent.mkdir(parents=True, exist_ok=True)
    gs.save_canvas(ARGS.output, overwrite=True)
    gs.save_frames(
        ARGS.output.with_name("contours_clipping_tint_frame"),
        count=3,
        overwrite=True,
    )
    with suppress(gs.BackendCapabilityError):
        gs.save_gif(ARGS.output.with_suffix(".gif"), count=3, duration=0.5, overwrite=True)


def draw() -> None:
    gs.background(250, 248, 242)
    draw_cutout_badge()
    draw_clipped_field()
    draw_tinted_images()

    gs.no_stroke()
    gs.fill(30, 34, 44)
    gs.text_size(16)
    gs.text("contour hole", 92, 330)
    gs.text("path clipping", 378, 330)
    gs.text("image tint", 598, 330)

    export_examples()


if __name__ == "__main__":
    gs.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
