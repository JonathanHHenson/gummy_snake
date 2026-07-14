from __future__ import annotations

from typing import Any, cast

import pytest

from gummysnake import constants as c
from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.backend.canvas_runtime.renderer.renderer_state.batch_state import ModelBatchKey
from gummysnake.core.color import Color
from gummysnake.core.state_facades import StyleState
from gummysnake.core.transform import Matrix2D
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError
from tests.helpers.canvas_runtime.modules import FakeCanvasModule


def test_canvas_renderer_rejects_mismatched_frame_command_abi() -> None:
    class StaleFrameCommandModule(FakeCanvasModule):
        def frame_command_abi_version(self) -> int:
            return 0

    with pytest.raises(BackendCapabilityError, match="frame-command ABI 1"):
        CanvasRenderer(StaleFrameCommandModule())


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


def test_canvas_renderer_draw_and_present_do_not_expose_an_event_pump() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(10, 10)
    canvas = renderer.runtime_canvas()

    assert not hasattr(canvas, "pump_native_events")

    renderer.begin_frame()
    renderer.background(Color(1, 2, 3, 255))
    renderer.end_frame()
    renderer.present()

    assert ("present",) in canvas.calls


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


def test_canvas_renderer_records_packed_style_and_transform_payloads() -> None:
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
    primitive_calls = [call for call in canvas.calls if call[0] == "batch_primitives_mixed"]
    assert [record[:7] for call in primitive_calls for record in call[1]] == [
        (4, 0, 0, 1, 1, 0.0, 0.0),
        (4, 2, 2, 3, 3, 0.0, 0.0),
        (3, 2, 2, 3, 3, 0.0, 0.0),
    ]
    assert all(call[2][0][2:6] == (255, 0, 0, 128) for call in primitive_calls)
    assert all(call[2][0][6:10] == (0, 0, 255, 255) for call in primitive_calls)
    assert all(call[3] == [(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)] for call in primitive_calls)

    style.fill_color = Color(0, 255, 0, 255)
    style.mark_changed()
    renderer.line(0, 0, 1, 1, style, transform)
    moved = Matrix2D.translation(4, 5)
    renderer.line(0, 0, 1, 1, style, moved)

    changed_call, transformed_call = [
        call for call in canvas.calls if call[0] == "batch_primitives_mixed"
    ][-2:]
    assert changed_call[2][0][2:6] == (0, 255, 0, 255)
    assert changed_call[3] == [(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)]
    assert transformed_call[2] == changed_call[2]
    assert transformed_call[3] == [(1.0, 0.0, 0.0, 1.0, 4.0, 5.0)]


def _model_batch_key(
    *,
    model_handle: object | None = None,
    material: dict[str, object] | None = None,
    source_signature: tuple[int, int, int, int, int, int, bool] | None = None,
) -> ModelBatchKey:
    return ModelBatchKey(
        model_handle=object() if model_handle is None else model_handle,
        camera={},
        projection={},
        viewport_width=8.0,
        viewport_height=8.0,
        material={} if material is None else material,
        lights=[],
        normal_material=False,
        cull_backfaces=True,
        source_signature=source_signature,
    )


def test_canvas_renderer_model_batch_normalizes_and_submits_one_run() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    key = _model_batch_key()
    flat_transform = tuple(float(index) for index in range(16))
    nested_transform = (
        (1.0, 2.0, 3.0, 4.0),
        (5.0, 6.0, 7.0, 8.0),
        (9.0, 10.0, 11.0, 12.0),
        (13.0, 14.0, 15.0, 16.0),
    )

    assert renderer._queue_model_batch(key, flat_transform)
    assert renderer._queue_model_batch(key, nested_transform)

    canvas = renderer._canvas
    assert canvas is not None
    assert not [call for call in canvas.calls if call[0] == "draw_model_shaded_batch"]

    renderer.end_frame()

    calls = [call for call in canvas.calls if call[0] == "draw_model_shaded_batch"]
    assert len(calls) == 1
    assert [transform for call in calls for transform in call[-1]] == [
        flat_transform,
        (1.0, 5.0, 9.0, 13.0, 2.0, 6.0, 10.0, 14.0, 3.0, 7.0, 11.0, 15.0, 4.0, 8.0, 12.0, 16.0),
    ]
    counters = renderer.performance_counters()
    assert counters["model_batch_records"] == 2
    assert counters["model_batch_flushes"] == 1
    assert counters["model_batch_max_records"] == 2


def test_canvas_renderer_model_batch_packs_n_flat_transforms_into_one_native_call() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    key = _model_batch_key()
    model_count = 128
    transforms = [
        tuple(float(value + model_index) for value in range(16))
        for model_index in range(model_count)
    ]

    assert (
        renderer._queue_model_batch_many(key, (transform for transform in transforms))
        == model_count
    )

    canvas = renderer.runtime_canvas()
    assert not [call for call in canvas.calls if call[0] == "draw_model_shaded_batch"]

    renderer.end_frame()

    model_calls = [call for call in canvas.calls if call[0] == "draw_model_shaded_batch"]
    assert len(model_calls) == 1
    assert model_calls[0][-1] == transforms
    counters = renderer.performance_counters()
    assert counters["direct_model_draws"] == model_count
    assert counters["model_batch_records"] == model_count
    assert counters["model_batch_flushes"] == 1
    assert counters["model_batch_max_records"] == model_count


def test_canvas_renderer_model_batch_flushes_between_compact_and_arbitrary_transforms() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    key = _model_batch_key()
    arbitrary = tuple(float(index) for index in range(16))

    assert renderer._queue_model_batch_translation_quaternion(
        key, 4.0, 5.0, 6.0, 0.5, 0.5, 0.5, 0.5
    )
    assert renderer._queue_model_batch_translation_quaternion(
        key, -4.0, -5.0, -6.0, 1.0, 0.0, 0.0, 0.0
    )
    assert renderer._queue_model_batch(key, arbitrary)
    renderer.end_frame()

    canvas = renderer.runtime_canvas()
    calls = [call for call in canvas.calls if call[0] == "draw_model_shaded_batch"]
    assert [len(call[-1]) for call in calls] == [2, 1]
    assert calls[0][-1] == [
        (0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 4.0, 5.0, 6.0, 1.0),
        (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -4.0, -5.0, -6.0, 1.0),
    ]
    assert calls[1][-1] == [arbitrary]
    counters = renderer.performance_counters()
    assert counters["model_batch_records"] == 3
    assert counters["model_batch_flushes"] == 2
    assert counters["model_batch_max_records"] == 2


def test_canvas_renderer_model_batch_many_accepts_matrices_and_rolls_back_invalid_input() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    key = _model_batch_key()
    flat_transform = tuple(float(index) for index in range(16))
    nested_transform = (
        (1.0, 0.0, 0.0, 7.0),
        (0.0, 1.0, 0.0, 8.0),
        (0.0, 0.0, 1.0, 9.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    assert renderer._queue_model_batch(key, flat_transform)

    with pytest.raises(ValueError, match=r"transform at index 1 is invalid:.*16 matrix values"):
        renderer._queue_model_batch_many(
            key,
            (nested_transform, (1.0, 2.0, 3.0)),
        )

    assert renderer._model_batch_state.record_count == 1
    assert renderer._queue_model_batch_many(key, (nested_transform,)) == 1
    renderer.end_frame()

    canvas = renderer.runtime_canvas()
    model_calls = [call for call in canvas.calls if call[0] == "draw_model_shaded_batch"]
    assert len(model_calls) == 1
    assert model_calls[0][-1] == [
        flat_transform,
        (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 7.0, 8.0, 9.0, 1.0),
    ]
    counters = renderer.performance_counters()
    assert counters["model_batch_records"] == 2
    assert counters["model_batch_flushes"] == 1
    assert counters["model_batch_max_records"] == 2


def test_canvas_renderer_model_batch_many_rejects_a_non_iterable_clearly() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)

    with pytest.raises(ValueError, match="transforms must be an iterable of matrices"):
        renderer._queue_model_batch_many(_model_batch_key(), cast(Any, None))

    assert not renderer._model_batch_state.has_records()


def test_canvas_renderer_model_batch_preserves_source_equivalence_and_order_boundaries() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(8, 8)
    model_handle = object()
    signature = (1, 2, 3, 4, 5, 0, False)
    first_key = _model_batch_key(
        model_handle=model_handle,
        material={"base_color": "first"},
        source_signature=signature,
    )
    equivalent_key = _model_batch_key(
        model_handle=model_handle,
        material={"base_color": "rebuilt"},
        source_signature=signature,
    )
    incompatible_key = _model_batch_key(model_handle=object())
    transform = tuple(float(index) for index in range(16))
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=None)

    for _ in range(8):
        assert renderer._queue_model_batch(first_key, transform)
    assert renderer._queue_model_batch(equivalent_key, transform)
    renderer.rect(0, 0, 1, 1, style, Matrix2D.identity())
    assert renderer._queue_model_batch(incompatible_key, transform)
    renderer.end_frame()

    canvas = renderer.runtime_canvas()
    ordered_calls = [
        call[0]
        for call in canvas.calls
        if call[0] in {"draw_model_shaded_batch", "batch_fill_primitives"}
    ]
    assert ordered_calls == [
        "draw_model_shaded_batch",
        "batch_fill_primitives",
        "draw_model_shaded_batch",
    ]
    model_calls = [call for call in canvas.calls if call[0] == "draw_model_shaded_batch"]
    assert [len(call[-1]) for call in model_calls] == [9, 1]
    assert model_calls[0][6] == {"base_color": "first"}
    counters = renderer.performance_counters()
    assert counters["model_batch_records"] == 10
    assert counters["model_batch_flushes"] == 2
    assert counters["model_batch_max_records"] == 9


def test_canvas_renderer_maps_rust_value_errors() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())

    with pytest.raises(ArgumentValidationError, match="positive"):
        renderer.resize(0, 1)

    renderer.resize(1, 1)
    with pytest.raises(ArgumentValidationError, match="Pixel buffer length"):
        renderer.update_pixels([1, 2, 3])
