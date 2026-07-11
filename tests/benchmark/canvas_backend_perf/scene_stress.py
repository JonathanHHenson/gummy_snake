from __future__ import annotations

import struct
from collections.abc import Callable
from typing import Any

from .scene_state import SceneState


def draw_stress_primitives(
    gs: Any, require_context: Callable[[], Any], state: SceneState, count: int
) -> None:
    context = require_context()
    renderer = context.renderer
    matrix = renderer._matrix_payload(context.state.transform.matrix)
    records = state.stress_primitive_records.get(count)
    if records is None:
        records = []
        for index in range(count):
            x = 4 + (index * 37) % 712
            y = 4 + (index * 53 + index // 97) % 472
            red = 40 + index % 160
            green = 120 + (index * 3) % 90
            if index % 3 == 0:
                records.append(
                    (1, x, y, 3 + index % 5, 3 + (index // 7) % 5, 0.0, 0.0, red, green, 215, 180)
                )
            elif index % 3 == 1:
                diameter = 3 + index % 6
                records.append(
                    (
                        3,
                        x - diameter / 2,
                        y - diameter / 2,
                        diameter,
                        diameter,
                        0.0,
                        0.0,
                        red,
                        green,
                        215,
                        180,
                    )
                )
            else:
                records.append(
                    (2, x, y, x + 5, y + 1 + index % 4, x + 1, y + 5, red, green, 215, 180)
                )
        state.stress_primitive_records[count] = records
    renderer._count("gpu_draws", len(records))
    renderer._count("primitive_batch_records", len(records))
    renderer._count("primitive_batch_flushes")
    canvas = renderer._require_canvas()
    if renderer._call("cached fill primitive drawing", canvas.replay_fill_primitive_batch):
        return
    renderer._call("batched fill primitive drawing", canvas.batch_fill_primitives, records, matrix)


def stress_primitive_count(variant: str) -> int | None:
    if variant == "stress_primitives_10k":
        return 10_000
    if variant == "stress_primitives_50k":
        return 50_000
    if variant == "stress_primitives_100k":
        return 100_000
    return None


def draw_stress_sprites(
    gs: Any, require_context: Callable[[], Any], state: SceneState, count: int
) -> None:
    context = require_context()
    renderer = context.renderer
    style = renderer._style_payload(context.state.style)
    matrix = renderer._matrix_payload(context.state.transform.matrix)
    canvas = renderer._require_canvas()
    compact = getattr(canvas, "batch_canvas_image_motion_terms", None)
    if callable(compact):
        payload = state.stress_sprite_payloads.get(count)
        if payload is None:
            payload_buffer = bytearray(count * 16)
            for index in range(count):
                struct.pack_into(
                    "<Ifff",
                    payload_buffer,
                    index * 16,
                    index % len(state.sprites),
                    float(index * 29),
                    float(10 + (index * 47 + index // 131) % 460),
                    float(6 + index % 5),
                )
            payload = bytes(payload_buffer)
            state.stress_sprite_payloads[count] = payload
        renderer._count("gpu_draws", count)
        renderer._count("image_batch_records", count)
        renderer._count("image_batch_flushes")
        renderer._call(
            "compact batched image drawing",
            compact,
            payload,
            [sprite.rust_image._rust_image for sprite in state.sprites],
            gs.frame_count(),
            style,
            matrix,
        )
        return
    terms = state.stress_sprite_terms.get(count)
    if terms is None:
        terms = [
            (
                state.sprites[index % len(state.sprites)].rust_image._rust_image,
                index * 29,
                10 + (index * 47 + index // 131) % 460,
                6 + index % 5,
            )
            for index in range(count)
        ]
        state.stress_sprite_terms[count] = terms
    frame = gs.frame_count()
    records = [
        (image, 10 + (base_x + frame) % 700 - size / 2, y - size / 2, size, size, None)
        for image, base_x, y, size in terms
    ]
    renderer._count("gpu_draws", len(records))
    renderer._count("image_batch_records", len(records))
    renderer._count("image_batch_flushes")
    renderer._call("batched image drawing", canvas.batch_canvas_images, records, style, matrix)


def draw_stress_text(gs: Any, count: int) -> None:
    gs.fill(235)
    gs.no_stroke()
    gs.text_size(10)
    labels = [
        (f"L{index % 100}", 8 + (index % 40) * 18, 14 + (index // 40) * 18)
        for index in range(count)
    ]
    gs.text_batch(labels)


def draw_stress_sprite_text_overlay(
    gs: Any, require_context: Callable[[], Any], state: SceneState
) -> None:
    draw_stress_sprites(gs, require_context, state, 10_000)
    gs.fill(248)
    gs.no_stroke()
    gs.text_size(12)
    if state.stress_overlay_labels is None:
        state.stress_overlay_labels = [
            (f"{index:03d}", 12 + (index % 25) * 28, 18 + (index // 25) * 24)
            for index in range(500)
        ]
    gs.text_batch(state.stress_overlay_labels)
