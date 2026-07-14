from __future__ import annotations

from typing import cast

import pytest

from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.context import SketchContext
from gummysnake.core.color import Color
from gummysnake.core.pixels import PixelBuffer
from gummysnake.core.state_facades import StyleState
from gummysnake.core.transform import Matrix2D
from tests.helpers.canvas_runtime.context import make_canvas_context
from tests.helpers.canvas_runtime.modules import FakeCanvasModule


def test_canvas_renderer_set_pixel_rgba_uses_fast_bridge() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(3, 2)

    renderer.set_pixel_rgba(1, 0, (300, 20, -1, 255))

    canvas = renderer._canvas
    assert canvas is not None
    assert canvas.calls[-1] == ("set_pixel_rgba", 1, 0, (255, 20, 0, 255))
    assert renderer.load_pixel_region(1, 0, 1, 1) == bytes([255, 20, 0, 255])


def test_canvas_context_set_color_uses_renderer_fast_pixel_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)
    context.create_canvas(3, 2, pixel_density=1)

    context.set(2, 1, (1, 2, 3, 4))

    canvas = backend.renderer._canvas
    assert canvas is not None
    assert canvas.calls[-1] == ("set_pixel_rgba", 2, 1, (1, 2, 3, 4))


def test_canvas_renderer_text_metrics_use_rust_canvas_and_text_draw_command() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(20, 20)
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None)

    assert renderer.text_width("hello", style) > 0
    assert renderer.text_ascent(style) > 0
    assert renderer.text_descent(style) >= 0
    renderer.text("hello", 0, 12, style, Matrix2D.identity())
    assert renderer._canvas is not None
    assert renderer._canvas.calls[-1][0] == "text_batch"
    assert renderer._canvas.calls[-1][1] == [("hello", 0, 12)]
    renderer.end_frame()
    assert any(call[0] == "text_width" and call[1] == "hello" for call in renderer._canvas.calls)


def test_canvas_renderer_caches_text_metrics_by_style() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(20, 20)
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None)

    assert renderer.text_width("hello", style) == renderer.text_width("hello", style)
    assert renderer.text_ascent(style) == renderer.text_ascent(style)
    assert renderer.text_descent(style) == renderer.text_descent(style)

    canvas = renderer._canvas
    assert canvas is not None
    assert [call[0] for call in canvas.calls].count("text_width") == 1
    assert [call[0] for call in canvas.calls].count("text_ascent") == 1
    assert [call[0] for call in canvas.calls].count("text_descent") == 1

    larger_style = style.copy()
    larger_style.text_size = 24.0
    assert renderer.text_width("hello", larger_style) != renderer.text_width("hello", style)
    assert [call[0] for call in canvas.calls].count("text_width") == 2


def test_canvas_renderer_skips_noop_update_after_load_pixel_bytes() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(2, 2)

    payload = renderer.load_pixel_bytes()
    renderer.update_pixels(payload)
    renderer.update_pixels(memoryview(payload))

    canvas = renderer._canvas
    assert canvas is not None
    assert [call[0] for call in canvas.calls].count("update_pixels") == 0
    assert renderer.performance_counters()["pixel_noop_upload_skips"] == 2


def test_canvas_renderer_dirty_pixel_buffer_uploads_full_dirty_rows() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 3)
    canvas = renderer._canvas
    assert canvas is not None

    def update_pixel_region_buffer(
        pixels: memoryview,
        width: int,
        height: int,
        x: int,
        y: int,
        alpha_composite: bool = True,
    ) -> None:
        canvas.calls.append(
            (
                "update_pixel_region_buffer",
                bytes(pixels),
                width,
                height,
                x,
                y,
                alpha_composite,
            )
        )

    canvas.update_pixel_region_buffer = update_pixel_region_buffer
    pixels = PixelBuffer(bytes(renderer.physical_width * renderer.physical_height * 4))
    pixels[8:24] = bytes(range(16))

    renderer.update_pixels(pixels)

    assert canvas.calls[-1] == (
        "update_pixel_region_buffer",
        bytes(pixels[:32]),
        4,
        2,
        0,
        0,
        False,
    )
    assert pixels.dirty_range() is None
