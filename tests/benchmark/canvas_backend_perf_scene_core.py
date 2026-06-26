from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from canvas_backend_perf_scene_state import SceneState


def sprite(gs: Any, width: int, height: int, seed: int):
    pixels = bytearray(width * height * 4)
    cx = (width - 1) / 2
    cy = (height - 1) / 2
    radius = min(width, height) / 2
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 4
            distance = math.hypot(x - cx, y - cy)
            if distance > radius:
                pixels[offset : offset + 4] = b"\x00\x00\x00\x00"
                continue
            pixels[offset] = (seed * 41 + x * 5) % 256
            pixels[offset + 1] = (seed * 67 + y * 7) % 256
            pixels[offset + 2] = 160 + (x + y + seed) % 80
            pixels[offset + 3] = 255
    return gs.Image(width, height, bytes(pixels))


def reset_asteroids(state: SceneState) -> None:
    state.shots = [
        [360.0, 240.0, math.cos(index * 0.62) * 8.5, math.sin(index * 0.62) * 8.5, index]
        for index in range(14)
    ]
    state.asteroids = [
        [
            60.0 + (index * 101) % 610,
            50.0 + (index * 71) % 380,
            math.cos(index * 1.7) * (0.8 + index % 3 * 0.22),
            math.sin(index * 1.7) * (0.8 + index % 3 * 0.22),
            24.0 + (index % 4) * 9.0,
            index * 0.37,
        ]
        for index in range(18)
    ]


def draw_starfield(gs: Any, count: int) -> None:
    gs.no_stroke()
    for index in range(count):
        x = (index * 97 + gs.frame_count() * (index % 4 + 1)) % 720
        y = (index * 53 + index * index) % 480
        alpha = 110 + (index % 4) * 35
        gs.fill(190, 220, 255, alpha)
        gs.circle(x, y, 1 + index % 3)


def draw_primitives(gs: Any, count: int) -> None:
    for index in range(count):
        x = 90 + (index * 83) % 520
        y = 80 + (index * 59) % 280
        with gs.pushed():
            gs.translate(x, y)
            gs.rotate(index * 0.18 + gs.frame_count() * 0.01)
            gs.no_fill()
            gs.stroke(180, 190, 210)
            gs.stroke_weight(2.5)
            gs.ellipse(-18, -14, 52, 64)
            gs.stroke(170, 225, 255, 255)
            gs.fill(36, 116, 220, 245)
            gs.triangle(0, -24, -20, 20, 0, 6)
            gs.triangle(0, -24, 0, 6, 20, 20)


def draw_laser_field(gs: Any, count: int) -> None:
    gs.no_fill()
    gs.stroke(100, 200, 255, 240)
    gs.stroke_weight(3)
    for index in range(count):
        sx = 80 + (index * 41) % 560
        sy = 60 + (index * 67) % 360
        with gs.pushed():
            gs.translate(sx, sy)
            gs.rotate(math.pi / 4 + index * 0.1)
            gs.line(0, -18, 0, 18)


def draw_image_field(gs: Any, state: SceneState, *, mutate: bool) -> None:
    gs.image_mode(gs.CENTER)
    for index in range(96):
        image = state.sprites[index % len(state.sprites)]
        if mutate and index == 0:
            image.update_pixels(state.churn_pixels)
        x = 34 + (index * 61 + gs.frame_count() * 3) % 660
        y = 34 + (index * 43 + index * index) % 410
        size = 20 + index % 5 * 5
        with gs.pushed():
            gs.translate(x, y)
            gs.rotate(index * 0.13 + gs.frame_count() * 0.012)
            gs.image(image, 0, 0, size, size)


def draw_mixed_text_pixels(gs: Any, require_context: Callable[[], Any], state: SceneState) -> None:
    gs.background(11, 18, 28)
    draw_starfield(gs, 24)
    draw_primitives(gs, 8)
    draw_image_field(gs, state, mutate=False)
    require_context().renderer.adjust_pixel_prefix(1024, 16, 3, 7)
    gs.fill(240)
    gs.no_stroke()
    gs.text_size(16)
    frame = gs.frame_count()
    width_labels = [f"score {index} frame {frame}" for index in range(18)]
    gs.text_widths(width_labels)
    gs.text_batch([(f"score {index * 125}", 28, 36 + index * 22) for index in range(18)])


def draw_blend_modes(gs: Any) -> None:
    modes = [gs.BLEND, gs.ADD, gs.MULTIPLY, gs.SCREEN, gs.DIFFERENCE, gs.EXCLUSION]
    gs.no_stroke()
    for index in range(72):
        gs.blend_mode(modes[index % len(modes)])
        gs.fill(50 + index % 120, 120 + index % 80, 220, 180)
        x = 30 + (index * 53 + gs.frame_count() * 2) % 660
        y = 30 + (index * 47 + index * index) % 420
        gs.circle(x, y, 28 + index % 4 * 6)
    gs.blend_mode(gs.BLEND)


def draw_erasing(gs: Any) -> None:
    gs.no_stroke()
    gs.fill(80, 150, 240, 230)
    for index in range(80):
        x = 28 + (index * 41) % 670
        y = 32 + (index * 67) % 410
        gs.circle(x, y, 30)
    gs.erase()
    gs.fill(255)
    for index in range(34):
        x = 30 + (index * 71 + gs.frame_count() * 3) % 660
        y = 30 + (index * 43) % 410
        gs.rect(x, y, 26, 18)
    gs.no_erase()


def draw_transformed_images(gs: Any, state: SceneState) -> None:
    gs.image_mode(gs.CENTER)
    for index in range(96):
        image = state.sprites[index % len(state.sprites)]
        x = 34 + (index * 61 + gs.frame_count() * 3) % 660
        y = 34 + (index * 43 + index * index) % 410
        with gs.pushed():
            gs.translate(x, y)
            gs.rotate(index * 0.17 + gs.frame_count() * 0.014)
            gs.scale(0.7 + (index % 5) * 0.18)
            gs.image(image, 0, 0, 34, 34)


def draw_text_only(gs: Any) -> None:
    gs.fill(235)
    gs.no_stroke()
    gs.text_size(15)
    gs.text_widths([f"label {index}" for index in range(12)])
    gs.text_batch(
        [(f"label {index}", 24 + (index % 5) * 136, 28 + (index // 5) * 27) for index in range(80)]
    )


def draw_pixel_readback_upload(gs: Any) -> None:
    draw_starfield(gs, 24)
    pixels = gs.load_pixel_bytes()
    gs.update_pixels(memoryview(pixels))
