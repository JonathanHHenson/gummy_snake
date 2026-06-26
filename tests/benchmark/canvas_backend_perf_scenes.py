from __future__ import annotations

import math

from canvas_backend_perf_scene_core import (
    draw_blend_modes,
    draw_erasing,
    draw_image_field,
    draw_laser_field,
    draw_mixed_text_pixels,
    draw_pixel_readback_upload,
    draw_primitives,
    draw_starfield,
    draw_text_only,
    draw_transformed_images,
    reset_asteroids,
    sprite,
)
from canvas_backend_perf_scene_showcase import (
    draw_asteroids_scene,
    draw_contours_clipping_tint,
    draw_webgl_3d,
)
from canvas_backend_perf_scene_state import SceneState
from canvas_backend_perf_scene_stress import (
    draw_stress_primitives,
    draw_stress_sprite_text_overlay,
    draw_stress_sprites,
    draw_stress_text,
    stress_primitive_count,
)

import gummysnake as gs
from gummysnake.api.current import require_context

_STATE = SceneState()

sprites = _STATE.sprites
churn_pixels = _STATE.churn_pixels
shots = _STATE.shots
asteroids = _STATE.asteroids
stamp = _STATE.stamp
stress_primitive_records = _STATE.stress_primitive_records
stress_sprite_terms = _STATE.stress_sprite_terms
stress_sprite_payloads = _STATE.stress_sprite_payloads
stress_overlay_labels = _STATE.stress_overlay_labels


def _sync_state_from_exports() -> None:
    _STATE.sprites = sprites
    _STATE.churn_pixels = churn_pixels
    _STATE.shots = shots
    _STATE.asteroids = asteroids
    _STATE.stamp = stamp
    _STATE.stress_primitive_records = stress_primitive_records
    _STATE.stress_sprite_terms = stress_sprite_terms
    _STATE.stress_sprite_payloads = stress_sprite_payloads
    _STATE.stress_overlay_labels = stress_overlay_labels


def _sync_exports_from_state() -> None:
    global sprites, churn_pixels, shots, asteroids, stamp
    global \
        stress_primitive_records, \
        stress_sprite_terms, \
        stress_sprite_payloads, \
        stress_overlay_labels
    sprites = _STATE.sprites
    churn_pixels = _STATE.churn_pixels
    shots = _STATE.shots
    asteroids = _STATE.asteroids
    stamp = _STATE.stamp
    stress_primitive_records = _STATE.stress_primitive_records
    stress_sprite_terms = _STATE.stress_sprite_terms
    stress_sprite_payloads = _STATE.stress_sprite_payloads
    stress_overlay_labels = _STATE.stress_overlay_labels


def _sprite(width: int, height: int, seed: int):
    return sprite(gs, width, height, seed)


def _reset_asteroids() -> None:
    _sync_state_from_exports()
    reset_asteroids(_STATE)
    _sync_exports_from_state()


def _stress_primitive_count(variant: str) -> int | None:
    return stress_primitive_count(variant)


def setup_scene(variant: str) -> None:
    _sync_state_from_exports()
    renderer = gs.WEBGL if variant == "webgl_3d" else gs.P2D
    if variant == "contours_clipping_tint":
        gs.create_canvas(760, 430, renderer)
    else:
        gs.create_canvas(720, 480, renderer)
    gs.frame_rate(10_000)
    if variant == "webgl_3d":
        gs.no_stroke()
        gs.camera(0, -60, 470, 0, 20, 0, 0, 1, 0)
        gs.perspective(math.pi / 3, 720 / 480, 0.1, 4000)
    _STATE.sprites = [_sprite(48, 48, seed) for seed in range(5)]
    _STATE.churn_pixels = _sprite(48, 48, 99).to_rgba_bytes()
    _STATE.stamp = gs.create_image(42, 42)
    for y in range(_STATE.stamp.height):
        for x in range(_STATE.stamp.width):
            dx = x - _STATE.stamp.width / 2
            dy = y - _STATE.stamp.height / 2
            alpha = max(0, min(255, int(255 - math.hypot(dx, dy) * 9)))
            _STATE.stamp.set(x, y, (255, 255, 255, alpha))
    if variant == "cached_images_nearest":
        gs.no_smooth()
    _sync_exports_from_state()
    _reset_asteroids()
    if variant == "text_only":
        renderer = require_context().renderer
        renderer.begin_frame()
        draw_text_only(gs)
        renderer.end_frame()
    primitive_count = stress_primitive_count(variant)
    if primitive_count is not None:
        renderer = require_context().renderer
        renderer.begin_frame()
        draw_stress_primitives(gs, require_context, _STATE, primitive_count)
        renderer.end_frame()
        gs.reset_renderer_performance_counters()
    _sync_exports_from_state()


def draw_scene(variant: str) -> None:
    _sync_state_from_exports()
    gs.background(8, 13, 32)
    if variant == "dense_primitives":
        draw_starfield(gs, 72)
        draw_primitives(gs, 28)
        draw_laser_field(gs, 16)
    elif variant == "sparse_primitives":
        draw_starfield(gs, 12)
        draw_primitives(gs, 6)
        draw_laser_field(gs, 4)
    elif (primitive_count := stress_primitive_count(variant)) is not None:
        draw_stress_primitives(gs, require_context, _STATE, primitive_count)
    elif variant == "cached_images" or variant == "cached_images_nearest":
        draw_image_field(gs, _STATE, mutate=False)
    elif variant == "stress_sprites_10k":
        draw_stress_sprites(gs, require_context, _STATE, 10_000)
    elif variant == "stress_sprites_50k":
        draw_stress_sprites(gs, require_context, _STATE, 50_000)
    elif variant == "image_upload_churn":
        draw_image_field(gs, _STATE, mutate=True)
    elif variant == "blend_modes":
        draw_blend_modes(gs)
    elif variant == "erasing":
        draw_erasing(gs)
    elif variant == "transformed_images":
        draw_transformed_images(gs, _STATE)
    elif variant == "text_only":
        draw_text_only(gs)
    elif variant == "stress_text_1k":
        draw_stress_text(gs, 1_000)
    elif variant == "stress_sprite_text_overlay":
        draw_stress_sprite_text_overlay(gs, require_context, _STATE)
    elif variant == "pixel_readback_upload":
        draw_pixel_readback_upload(gs)
    elif variant == "mixed_text_pixels":
        draw_mixed_text_pixels(gs, require_context, _STATE)
    elif variant == "contours_clipping_tint":
        draw_contours_clipping_tint(gs, _STATE)
    elif variant == "asteroids_scene":
        draw_asteroids_scene(gs, _STATE)
    elif variant == "webgl_3d":
        draw_webgl_3d(gs, _STATE)
    else:
        raise ValueError(f"unknown benchmark variant: {variant}")
    _sync_exports_from_state()
