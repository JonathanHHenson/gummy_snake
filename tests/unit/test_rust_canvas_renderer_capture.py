from __future__ import annotations

from rust_canvas_modules import FakeCanvasModule

from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D


def test_canvas_renderer_forwards_captured_shape_without_python_extraction() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(10, 10)
    canvas = renderer._canvas
    assert canvas is not None

    class CapturedState:
        def shape_vertices(self) -> list[tuple[float, float]]:
            raise AssertionError("shape vertices should stay in Rust")

        def shape_contours(self) -> list[list[tuple[float, float]]]:
            raise AssertionError("shape contours should stay in Rust")

    def draw_captured_shape(
        state: object,
        style: dict[str, object],
        matrix: tuple[float, float, float, float, float, float],
        close: bool = True,
    ) -> None:
        canvas.calls.append(("draw_captured_shape", state, style, matrix, close))

    canvas.draw_captured_shape = draw_captured_shape
    style = StyleState(fill_color=Color(10, 20, 30, 255), stroke_color=None)
    transform = Matrix2D.translation(3, 4)
    state = CapturedState()

    renderer.draw_captured_shape(state, style, transform, close=False)

    call = canvas.calls[-1]
    assert call[0] == "draw_captured_shape"
    assert call[1] is state
    assert call[2]["fill"] == (10, 20, 30, 255)
    assert call[3] == (1.0, 0.0, 0.0, 1.0, 3, 4)
    assert call[4] is False
    counters = renderer.performance_counters()
    assert counters["direct_shape_finalizations"] == 1
    assert counters["shape_buffer_extractions"] == 0


def test_canvas_renderer_forwards_captured_clip_without_python_extraction() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(10, 10)
    canvas = renderer._canvas
    assert canvas is not None

    class CapturedState:
        def shape_vertices(self) -> list[tuple[float, float]]:
            raise AssertionError("clip vertices should stay in Rust")

        def shape_contours(self) -> list[list[tuple[float, float]]]:
            raise AssertionError("clip contours should stay in Rust")

    def begin_clip_captured(
        state: object,
        matrix: tuple[float, float, float, float, float, float],
    ) -> None:
        canvas.calls.append(("begin_clip_captured", state, matrix))

    canvas.begin_clip_captured = begin_clip_captured
    transform = Matrix2D.translation(5, 6)
    state = CapturedState()

    renderer.begin_clip_captured_shape(state, transform)

    assert canvas.calls[-1] == ("begin_clip_captured", state, (1.0, 0.0, 0.0, 1.0, 5, 6))
    counters = renderer.performance_counters()
    assert counters["direct_shape_finalizations"] == 1
    assert counters["shape_buffer_extractions"] == 0


def test_canvas_renderer_batches_lines_with_mixed_primitives() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(20, 20)
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=Color(0, 0, 0, 255))
    transform = Matrix2D.identity()

    renderer.triangle(1, 2, 3, 4, 5, 6, style, transform)
    renderer.line(7, 8, 9, 10, style, transform)
    renderer.ellipse(11, 12, 13, 14, style, transform)
    renderer.end_frame()

    canvas = renderer._canvas
    assert canvas is not None
    batch = next(call for call in canvas.calls if call[0] == "batch_primitives")
    assert batch[1] == [
        (2, 1, 2, 3, 4, 5, 6),
        (4, 7, 8, 9, 10, 0.0, 0.0),
        (3, 11, 12, 13, 14, 0.0, 0.0),
    ]
