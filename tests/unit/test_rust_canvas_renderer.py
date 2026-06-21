from __future__ import annotations

from typing import cast

import pytest
from rust_canvas_context_helpers import make_canvas_context
from rust_canvas_modules import FakeCanvasModule

from gummysnake import constants as c
from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.context import SketchContext
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D
from gummysnake.exceptions import ArgumentValidationError


def test_canvas_renderer_allocates_and_mirrors_dimensions() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())

    renderer.resize(12, 6, pixel_density=1.5)

    assert renderer.width == 12
    assert renderer.height == 6
    assert renderer.physical_width == 18
    assert renderer.physical_height == 9
    assert renderer.pixel_density == 1.5
    assert renderer.runtime_canvas().gpu_available() is True
    assert renderer.runtime_canvas().gpu_status() == "available"


def test_canvas_renderer_pump_native_events_syncs_resized_canvas_dimensions() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(10, 10)
    canvas = renderer.runtime_canvas()

    def pump_native_events() -> bool:
        canvas.resize_canvas(20, 12, 1.5, c.P2D)
        return False

    canvas.pump_native_events = pump_native_events
    renderer._last_native_event_pump = 0.0

    renderer.background(Color(1, 2, 3, 255))

    assert renderer.width == 20
    assert renderer.height == 12
    assert renderer.physical_width == 30
    assert renderer.physical_height == 18
    assert renderer.pixel_density == 1.5


def test_canvas_renderer_present_pumps_native_events_and_skips_closed_window() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(10, 10)
    canvas = renderer.runtime_canvas()

    def pump_native_events() -> bool:
        canvas.closed = True
        return True

    canvas.pump_native_events = pump_native_events

    renderer.present()

    assert ("present",) not in canvas.calls


def test_canvas_renderer_converts_style_color_and_transform_payloads() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    style = StyleState(fill_color=Color(255, 0, 0, 128), stroke_color=Color(0, 0, 255, 255))
    style.stroke_weight = 3
    transform = Matrix2D(1, 2, 3, 4, 5, 6)

    renderer.polygon([(1, 2), (3, 4)], style, transform, close=False)

    canvas = renderer._canvas
    assert canvas is not None
    call = canvas.calls[-1]
    assert call[0] == "polygon"
    assert call[1] == [(1, 2), (3, 4)]
    style_payload = call[2]
    assert isinstance(style_payload, dict)
    assert {
        key: style_payload[key]
        for key in ("fill", "stroke", "stroke_weight", "blend_mode", "erasing", "image_sampling")
    } == {
        "fill": (255, 0, 0, 128),
        "stroke": (0, 0, 255, 255),
        "stroke_weight": 3.0,
        "blend_mode": c.BLEND,
        "erasing": False,
        "image_sampling": c.LINEAR,
    }
    assert style_payload["text_size"] == 12.0
    assert style_payload["text_align_x"] == c.LEFT
    assert style_payload["text_align_y"] == c.BASELINE
    assert call[3] == (1, 2, 3, 4, 5, 6)
    assert call[4] is False


def test_canvas_renderer_reuses_unchanged_style_and_transform_payloads() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    style = StyleState(fill_color=Color(255, 0, 0, 128), stroke_color=Color(0, 0, 255, 255))
    transform = Matrix2D.identity()

    renderer.line(0, 0, 1, 1, style, transform)
    renderer.line(2, 2, 3, 3, style, transform)
    renderer.ellipse(2, 2, 3, 3, style, transform)

    canvas = renderer._canvas
    assert canvas is not None
    line_call = canvas.calls[-2]
    ellipse_call = canvas.calls[-1]
    assert line_call[0] == "batch_lines"
    assert line_call[1] == [(0, 0, 1, 1), (2, 2, 3, 3)]
    assert line_call[2] is ellipse_call[5]
    assert line_call[3] is ellipse_call[6]

    style.fill_color = Color(0, 255, 0, 255)
    style.mark_changed()
    renderer.line(0, 0, 1, 1, style, transform)
    moved = Matrix2D.translation(4, 5)
    renderer.line(0, 0, 1, 1, style, moved)

    changed_call = canvas.calls[-1]
    assert changed_call[0] == "batch_lines"
    assert changed_call[2] is not line_call[2]
    assert changed_call[2]["fill"] == (0, 255, 0, 255)
    assert changed_call[3] is line_call[3]

    renderer.end_frame()

    transformed_call = canvas.calls[-2]
    assert transformed_call[0] == "batch_lines"
    assert transformed_call[2] is changed_call[2]
    assert transformed_call[3] is not changed_call[3]
    assert transformed_call[3] == (1.0, 0.0, 0.0, 1.0, 4, 5)


def test_canvas_context_style_cache_invalidation_respects_push_pop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)

    context.fill(255, 0, 0)
    context.line(0, 0, 1, 1)
    context.push()
    context.fill(0, 255, 0)
    context.translate(5, 6)
    context.line(0, 0, 1, 1)
    context.pop()
    context.line(0, 0, 1, 1)
    context.renderer.end_frame()

    canvas = backend.renderer._canvas
    assert canvas is not None
    batches = [call for call in canvas.calls if call[0] == "batch_lines"]
    first, second, third = batches[-3:]
    assert first[2]["fill"] == (255, 0, 0, 255)
    assert second[2]["fill"] == (0, 255, 0, 255)
    assert third[2]["fill"] == (255, 0, 0, 255)
    assert first[3] == third[3] == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    assert second[3] == (1.0, 0.0, 0.0, 1.0, 5.0, 6.0)


def test_canvas_context_rect_uses_direct_rectangle_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)

    context.fill(255, 0, 0)
    context.translate(3, 4)
    context.rect(10, 11, 12, 13)

    canvas = backend.renderer._canvas
    assert canvas is not None
    call = canvas.calls[-1]
    assert call[0] == "rect"
    assert call[1:5] == (10.0, 11.0, 12.0, 13.0)
    assert call[5]["fill"] == (255, 0, 0, 255)
    assert call[6] == (1.0, 0.0, 0.0, 1.0, 3.0, 4.0)


def test_canvas_context_triangle_and_quad_use_direct_shape_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)

    context.triangle(1, 2, 3, 4, 5, 6)
    context.quad(7, 8, 9, 10, 11, 12, 13, 14)

    canvas = backend.renderer._canvas
    assert canvas is not None
    triangle_call = canvas.calls[-2]
    quad_call = canvas.calls[-1]
    assert triangle_call[0] == "triangle"
    assert triangle_call[1:7] == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert quad_call[0] == "quad"
    assert quad_call[1:9] == (7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0)
    assert triangle_call[-2] is quad_call[-2]
    assert triangle_call[-1] is quad_call[-1]


def test_canvas_context_shape_context_manager_draws_on_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)

    with context.shape(c.CLOSE):
        context.vertex(1, 2)
        context.vertex(8, 2)
        context.vertex(8, 9)

    canvas = backend.renderer._canvas
    assert canvas is not None
    call = canvas.calls[-1]
    assert call[0] == "polygon"
    assert call[1] == [(1.0, 2.0), (8.0, 2.0), (8.0, 9.0)]
    assert call[4] is True
    assert context.state.shape.active is False


def test_canvas_context_contour_context_manager_adds_hole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)

    with context.shape(c.CLOSE):
        context.vertex(0, 0)
        context.vertex(20, 0)
        context.vertex(20, 20)
        context.vertex(0, 20)
        with context.contour():
            context.vertex(6, 6)
            context.vertex(14, 6)
            context.vertex(14, 14)
            context.vertex(6, 14)

    canvas = backend.renderer._canvas
    assert canvas is not None
    call = canvas.calls[-1]
    assert call[0] == "complex_polygon"
    assert call[1] == [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]
    assert call[2] == [[(6.0, 6.0), (14.0, 6.0), (14.0, 14.0), (6.0, 14.0)]]
    assert call[5] is True


def test_canvas_context_clip_path_context_manager_applies_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)

    with context.clip_path():
        context.vertex(0, 0)
        context.vertex(10, 0)
        context.vertex(10, 10)
    context.rect(0, 0, 20, 20)
    context.end_clip()

    canvas = backend.renderer._canvas
    assert canvas is not None
    calls = canvas.calls
    assert calls[-3][0] == "begin_clip"
    assert calls[-3][1] == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    assert calls[-2][0] == "rect"
    assert calls[-1] == ("end_clip",)


def test_canvas_context_shape_context_manager_cleans_up_after_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, _backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)

    with pytest.raises(RuntimeError, match="boom"), context.shape(c.CLOSE):
        context.vertex(1, 2)
        raise RuntimeError("boom")

    assert context.state.shape.active is False
    context.begin_shape()
    context.vertex(0, 0)
    context.vertex(1, 0)
    context.vertex(1, 1)
    context.end_shape(c.CLOSE)


def test_canvas_renderer_set_pixel_rgba_uses_fast_bridge() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(3, 2)

    renderer.set_pixel_rgba(1, 0, (300, 20, -1, 255))

    canvas = renderer._canvas
    assert canvas is not None
    assert canvas.calls[-1] == ("set_pixel_rgba", 1, 0, (255, 20, 0, 255))
    assert renderer.load_pixel_region(1, 0, 1, 1) == bytes([255, 20, 0, 255])


def test_canvas_renderer_set_pixel_rgba_falls_back_to_region_upload() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(3, 2)

    canvas = renderer._canvas
    assert canvas is not None
    canvas.set_pixel_rgba = None

    renderer.set_pixel_rgba(1, 0, (10, 20, 30, 255))
    assert canvas.calls[-1] == (
        "update_pixel_region",
        bytes([10, 20, 30, 255]),
        1,
        1,
        1,
        0,
        False,
    )


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


def test_canvas_renderer_maps_rust_value_errors() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())

    with pytest.raises(ArgumentValidationError, match="positive"):
        renderer.resize(0, 1)

    renderer.resize(1, 1)
    with pytest.raises(ArgumentValidationError, match="Pixel buffer length"):
        renderer.update_pixels([1, 2, 3])


def test_canvas_renderer_text_metrics_use_rust_canvas_and_text_draw_command() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(20, 20)
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None)

    assert renderer.text_width("hello", style) > 0
    assert renderer.text_ascent(style) > 0
    assert renderer.text_descent(style) >= 0
    renderer.text("hello", 0, 12, style, Matrix2D.identity())
    assert renderer._canvas is not None
    assert renderer._canvas.calls[-1][0] == "text"
    assert renderer._canvas.calls[-4][0] == "text_width"
    assert renderer._canvas.calls[-4][1] == "hello"


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
