from __future__ import annotations

import pytest

from gummysnake import constants as c
from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D
from gummysnake.exceptions import ArgumentValidationError
from tests.helpers.canvas_runtime.modules import FakeCanvasModule


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


def test_text_metrics_do_not_use_stale_current_style_after_native_sync() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    style = StyleState()
    renderer.set_current_style(style)
    style.text_size = 18.0
    style.mark_changed()
    renderer._rust_style_synced = True

    width = renderer.text_width("bounds", style)
    ascent = renderer.text_ascent(style)
    descent = renderer.text_descent(style)

    canvas = renderer._canvas
    assert canvas is not None
    assert width == 54.0
    assert ascent == 14.4
    assert descent == 3.6
    assert ("text_width_current", "bounds") not in canvas.calls
    assert ("text_ascent_current",) not in canvas.calls
    assert ("text_descent_current",) not in canvas.calls
    assert canvas.calls[-3][0] == "text_width"
    assert canvas.calls[-3][2]["text_size"] == 18.0
    assert canvas.calls[-2][0] == "text_ascent"
    assert canvas.calls[-2][1]["text_size"] == 18.0
    assert canvas.calls[-1][0] == "text_descent"
    assert canvas.calls[-1][1]["text_size"] == 18.0


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
    renderer.end_frame()
    primitive_call = canvas.calls[-2]
    assert primitive_call[0] == "batch_primitives"
    assert primitive_call[1] == [
        (4, 0, 0, 1, 1, 0.0, 0.0),
        (4, 2, 2, 3, 3, 0.0, 0.0),
        (3, 2, 2, 3, 3, 0.0, 0.0),
    ]

    style.fill_color = Color(0, 255, 0, 255)
    style.mark_changed()
    renderer.line(0, 0, 1, 1, style, transform)
    moved = Matrix2D.translation(4, 5)
    renderer.line(0, 0, 1, 1, style, moved)

    changed_call = canvas.calls[-1]
    assert changed_call[0] == "batch_primitives"
    assert changed_call[2] is not primitive_call[2]
    assert changed_call[2]["fill"] == (0, 255, 0, 255)
    assert changed_call[3] is primitive_call[3]

    renderer.end_frame()

    transformed_call = canvas.calls[-2]
    assert transformed_call[0] == "batch_primitives"
    assert transformed_call[2] is changed_call[2]
    assert transformed_call[3] is not changed_call[3]
    assert transformed_call[3] == (1.0, 0.0, 0.0, 1.0, 4, 5)


def test_canvas_renderer_maps_rust_value_errors() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())

    with pytest.raises(ArgumentValidationError, match="positive"):
        renderer.resize(0, 1)

    renderer.resize(1, 1)
    with pytest.raises(ArgumentValidationError, match="Pixel buffer length"):
        renderer.update_pixels([1, 2, 3])
