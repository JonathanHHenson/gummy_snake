from __future__ import annotations

from typing import cast

import pytest

from gummysnake import constants as c
from gummysnake.context import SketchContext
from tests.helpers.rust_canvas_context import make_canvas_context


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
    assert backend.renderer._current_style is context.state.style
    assert backend.renderer._current_matrix_payload == (
        1.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
    )
    context.line(0, 0, 1, 1)
    context.renderer.end_frame()

    canvas = backend.renderer._canvas
    assert canvas is not None
    batches = [call for call in canvas.calls if call[0] == "batch_primitives"]
    first, second, third = batches[-3:]
    assert first[2]["fill"] == (255, 0, 0, 255)
    assert second[2]["fill"] == (0, 255, 0, 255)
    assert third[2]["fill"] == (255, 0, 0, 255)
    assert first[3] == third[3] == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    assert second[3] == (1.0, 0.0, 0.0, 1.0, 5.0, 6.0)


def test_canvas_context_rect_uses_primitive_batch_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)

    context.fill(255, 0, 0)
    context.translate(3, 4)
    context.rect(10, 11, 12, 13)

    canvas = backend.renderer._canvas
    assert canvas is not None
    context.renderer.end_frame()

    call = canvas.calls[-2]
    assert call[0] == "batch_primitives"
    assert call[1] == [(1, 10.0, 11.0, 12.0, 13.0, 0.0, 0.0)]
    assert call[2]["fill"] == (255, 0, 0, 255)
    assert call[3] == (1.0, 0.0, 0.0, 1.0, 3.0, 4.0)


def test_canvas_context_triangle_batches_before_quad_direct_shape_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    context = cast(SketchContext, sketch.context)

    context.triangle(1, 2, 3, 4, 5, 6)
    context.quad(7, 8, 9, 10, 11, 12, 13, 14)

    canvas = backend.renderer._canvas
    assert canvas is not None
    context.renderer.end_frame()

    triangle_call = canvas.calls[-3]
    quad_call = canvas.calls[-2]
    assert triangle_call[0] == "batch_primitives"
    assert triangle_call[1] == [(2, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)]
    assert quad_call[0] == "quad"
    assert quad_call[1:9] == (7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0)
    assert triangle_call[-2] is quad_call[-2]
    assert triangle_call[-1] is quad_call[-1]


def test_canvas_renderer_batches_simple_primitives_until_order_boundary() -> None:
    from gummysnake.backend.canvas_renderer import CanvasRenderer
    from gummysnake.core.color import Color
    from gummysnake.core.state import StyleState
    from gummysnake.core.transform import Matrix2D
    from tests.helpers.rust_canvas_modules import FakeCanvasModule

    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(20, 20)
    style = StyleState(fill_color=Color(255, 0, 0, 255), stroke_color=None)
    transform = Matrix2D.identity()

    renderer.rect(1, 2, 3, 4, style, transform)
    renderer.triangle(1, 1, 5, 1, 3, 6, style, transform)
    renderer.ellipse(10, 10, 4, 6, style, transform)
    renderer.text("label", 0, 10, style, transform)
    renderer.end_frame()

    canvas = renderer._canvas
    assert canvas is not None
    primitive_call = next(call for call in canvas.calls if call[0] == "batch_fill_primitives")
    text_call = next(call for call in canvas.calls if call[0] == "text_batch_frame")
    assert canvas.calls.index(primitive_call) < canvas.calls.index(text_call)
    assert primitive_call[1] == [
        (1, 1, 2, 3, 4, 0.0, 0.0, 255, 0, 0, 255),
        (2, 1, 1, 5, 1, 3, 6, 255, 0, 0, 255),
        (3, 10, 10, 4, 6, 0.0, 0.0, 255, 0, 0, 255),
    ]
    assert renderer.performance_counters()["primitive_batch_records"] == 3


def test_canvas_renderer_flushes_primitive_batch_before_image_pixel_and_background() -> None:
    from gummysnake.assets.image import Image
    from gummysnake.backend.canvas_renderer import CanvasRenderer
    from gummysnake.core.color import Color
    from gummysnake.core.state import StyleState
    from gummysnake.core.transform import Matrix2D
    from tests.helpers.rust_canvas_modules import FakeCanvasModule

    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(20, 20)
    style = StyleState(fill_color=Color(255, 0, 0, 255), stroke_color=None)
    image_style = StyleState(fill_color=None, stroke_color=None)
    transform = Matrix2D.identity()
    image = Image(1, 1, bytes([255, 255, 255, 255]))

    renderer.rect(1, 2, 3, 4, style, transform)
    renderer.draw_image(image, 0, 0, 1, 1, image_style, transform)
    renderer.rect(5, 6, 7, 8, style, transform)
    renderer.load_pixel_region(0, 0, 1, 1)
    renderer.rect(9, 10, 2, 2, style, transform)
    renderer.background(Color(0, 0, 0, 255))
    renderer.end_frame()

    canvas = renderer._canvas
    assert canvas is not None
    calls = canvas.calls
    first_primitive = next(call for call in calls if call[0] == "batch_fill_primitives")
    image_batch = next(call for call in calls if call[0] == "batch_canvas_images")
    readback = next(call for call in calls if call[0] == "load_pixel_region")
    background_call = next(call for call in calls if call[0] == "background")
    assert calls.index(first_primitive) < calls.index(image_batch)
    assert calls.index(image_batch) < calls.index(readback)
    assert calls.index(readback) < calls.index(background_call)
    assert [call[0] for call in calls].count("batch_fill_primitives") == 3


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
    assert calls[-2][0] == "batch_primitives"
    assert calls[-2][1] == [(1, 0.0, 0.0, 20.0, 20.0, 0.0, 0.0)]
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
