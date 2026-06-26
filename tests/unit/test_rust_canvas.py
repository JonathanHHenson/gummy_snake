from __future__ import annotations

import pytest

from gummysnake.exceptions import BackendCapabilityError
from gummysnake.rust.canvas import (
    EXPECTED_CANVAS_ABI_VERSION,
    canvas_abi_version,
    canvas_gpu_available,
    canvas_gpu_status,
    canvas_health_check,
    canvas_import_error,
    canvas_native_window_available,
    is_canvas_runtime_available,
    require_canvas_runtime,
)
from tests.helpers.rust_canvas_context import (
    install_fake_canvas_runtime,
    install_missing_canvas_runtime,
)
from tests.helpers.rust_canvas_modules import (
    FakeCanvasModule,
    FakeCanvasModuleWithBadAbi,
    FakeCanvasModuleWithHealthFailure,
    FakeCanvasModuleWithoutAbi,
    FakeCanvasModuleWithoutGpu,
)


def test_canvas_health_check_reports_required_runtime() -> None:
    assert canvas_health_check() == "rust-canvas"
    assert canvas_abi_version() == EXPECTED_CANVAS_ABI_VERSION
    assert canvas_native_window_available() in {True, False}
    assert canvas_gpu_available() in {True, False}
    assert canvas_gpu_status()
    assert is_canvas_runtime_available() is True
    assert canvas_import_error() is None


def test_canvas_wrapper_uses_loaded_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_canvas_runtime(monkeypatch)

    assert is_canvas_runtime_available()
    assert canvas_health_check() == "fake-canvas"
    assert canvas_abi_version() == EXPECTED_CANVAS_ABI_VERSION
    assert canvas_native_window_available() is True
    assert canvas_gpu_available() is True
    assert canvas_gpu_status() == "available"
    assert require_canvas_runtime() is fake


def test_canvas_wrapper_raises_capability_error_when_runtime_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_missing_canvas_runtime(monkeypatch)

    with pytest.raises(BackendCapabilityError, match="gummysnake.rust._canvas"):
        require_canvas_runtime()


def test_canvas_wrapper_rejects_runtime_missing_asset_classes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingAssetClasses(FakeCanvasModule):
        CanvasSound = None

    install_fake_canvas_runtime(monkeypatch, MissingAssetClasses())

    with pytest.raises(BackendCapabilityError, match="CanvasSound"):
        require_canvas_runtime()


def test_canvas_wrapper_rejects_runtime_missing_asset_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeCanvasModule()
    monkeypatch.setattr(runtime, "parse_obj_model_handle", None)

    install_fake_canvas_runtime(monkeypatch, runtime)

    with pytest.raises(BackendCapabilityError, match="parse_obj_model_handle"):
        require_canvas_runtime()


@pytest.mark.parametrize(
    ("module", "message"),
    [
        (FakeCanvasModuleWithoutAbi(), "expected canvas ABI"),
        (FakeCanvasModuleWithBadAbi(), "expected canvas ABI"),
        (FakeCanvasModuleWithHealthFailure(), "failed its health check"),
    ],
)
def test_canvas_wrapper_rejects_incompatible_or_unhealthy_runtimes(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    message: str,
) -> None:
    install_fake_canvas_runtime(monkeypatch, module)

    with pytest.raises(BackendCapabilityError, match=message):
        require_canvas_runtime()


def test_canvas_gpu_status_explains_cpu_continuation_when_gpu_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_canvas_runtime(monkeypatch, FakeCanvasModuleWithoutGpu())

    assert canvas_gpu_available() is False
    assert "headless rendering can continue" in canvas_gpu_status()


def test_canvas_runtime_owns_current_style_and_transform_stack() -> None:
    runtime = require_canvas_runtime()
    canvas = runtime.Canvas(12, 12, 1.0, "headless", "p2d")

    canvas.set_current_style(
        {
            "fill": (255, 0, 0, 255),
            "stroke": None,
            "stroke_weight": 1.0,
            "image_tint": None,
            "blend_mode": "blend",
            "erasing": False,
            "image_sampling": "linear",
            "text_font_path": None,
            "text_font_name": "default",
            "text_size": 12.0,
            "text_align_x": "left",
            "text_align_y": "baseline",
            "text_leading": 14.0,
        }
    )
    canvas.translate(2.0, 3.0)
    canvas.push_canvas_state()
    canvas.set_current_style(
        {
            "fill": (0, 255, 0, 255),
            "stroke": None,
            "stroke_weight": 1.0,
            "image_tint": None,
            "blend_mode": "blend",
            "erasing": False,
            "image_sampling": "linear",
            "text_font_path": None,
            "text_font_name": "default",
            "text_size": 12.0,
            "text_align_x": "left",
            "text_align_y": "baseline",
            "text_leading": 14.0,
        }
    )
    canvas.translate(5.0, 0.0)

    assert canvas.current_matrix() == (1.0, 0.0, 0.0, 1.0, 7.0, 3.0)
    assert canvas.current_style()["fill"] == (0, 255, 0, 255)

    canvas.pop_canvas_state()

    assert canvas.current_matrix() == (1.0, 0.0, 0.0, 1.0, 2.0, 3.0)
    assert canvas.current_style()["fill"] == (255, 0, 0, 255)

    canvas.rect_current(0.0, 0.0, 2.0, 2.0)
    pixels = canvas.load_pixels()
    offset = ((3 * 12) + 2) * 4
    assert tuple(pixels[offset : offset + 4]) == (255, 0, 0, 255)


def test_canvas_current_draws_do_not_reuse_stale_temporary_style_payloads() -> None:
    runtime = require_canvas_runtime()
    canvas = runtime.Canvas(16, 6, 1.0, "headless", "p2d")

    def style(fill: tuple[int, int, int, int]) -> dict[str, object]:
        return {
            "fill": fill,
            "stroke": None,
            "stroke_weight": 1.0,
            "image_tint": None,
            "blend_mode": "blend",
            "erasing": False,
            "image_sampling": "linear",
            "text_font_path": None,
            "text_font_name": "default",
            "text_size": 12.0,
            "text_align_x": "left",
            "text_align_y": "baseline",
            "text_leading": 14.0,
        }

    canvas.set_current_style(style((255, 0, 0, 255)))
    canvas.rect_current(0.0, 0.0, 4.0, 4.0)
    canvas.set_current_style(style((0, 255, 0, 255)))
    canvas.rect_current(4.0, 0.0, 4.0, 4.0)
    canvas.set_current_style(style((0, 0, 255, 255)))
    canvas.rect_current(8.0, 0.0, 4.0, 4.0)

    pixels = canvas.load_pixels()
    assert tuple(pixels[((1 * 16) + 1) * 4 : ((1 * 16) + 1) * 4 + 4]) == (255, 0, 0, 255)
    assert tuple(pixels[((1 * 16) + 5) * 4 : ((1 * 16) + 5) * 4 + 4]) == (0, 255, 0, 255)
    assert tuple(pixels[((1 * 16) + 9) * 4 : ((1 * 16) + 9) * 4 + 4]) == (0, 0, 255, 255)


def test_canvas_shaded_faces_preserve_logical_size_at_pixel_density_two() -> None:
    runtime = require_canvas_runtime()

    def logical_occupied_bounds(density: float) -> tuple[float, float, float, float]:
        canvas = runtime.Canvas(64, 64, density, "headless", "p2d")
        canvas.background((0, 0, 0, 255))
        canvas.shaded_faces(
            [
                {
                    "points": [(10.0, 10.0), (30.0, 10.0), (10.0, 30.0)],
                    "color": (1.0, 0.0, 0.0, 1.0),
                    "depth": 0.0,
                    "texture": None,
                }
            ]
        )
        pixels = canvas.load_pixels()
        physical_width = int(64 * density)
        occupied = []
        for y in range(int(64 * density)):
            row = y * physical_width * 4
            for x in range(physical_width):
                offset = row + x * 4
                if tuple(pixels[offset : offset + 3]) == (255, 0, 0):
                    occupied.append((x / density, y / density))
        assert occupied
        return (
            min(x for x, _ in occupied),
            min(y for _, y in occupied),
            max(x for x, _ in occupied),
            max(y for _, y in occupied),
        )

    density_one = logical_occupied_bounds(1.0)
    density_two = logical_occupied_bounds(2.0)

    assert density_two[0] == pytest.approx(density_one[0], abs=0.75)
    assert density_two[1] == pytest.approx(density_one[1], abs=0.75)
    assert density_two[2] == pytest.approx(density_one[2], abs=0.75)
    assert density_two[3] == pytest.approx(density_one[3], abs=0.75)


def test_sketch_context_state_owns_lifecycle_input_and_shape_buffers() -> None:
    runtime = require_canvas_runtime()
    state = runtime.SketchContextState()

    state.sync_canvas(320, 240, 640, 480, 2.0, "webgl", True)
    assert state.width == 320
    assert state.height == 240
    assert state.physical_width == 640
    assert state.physical_height == 480
    assert state.pixel_density == 2.0
    assert state.renderer == "webgl"
    assert state.created is True

    state.looping = False
    state.redraw_requested = True
    state.target_frame_rate = 30.0
    state.begin_frame_timing()
    state.increment_frame_count()
    assert state.looping is False
    assert state.redraw_requested is True
    assert state.target_frame_rate == 30.0
    assert state.frame_count == 1
    assert state.delta_time >= 0.0
    assert state.millis() >= 0.0

    state.update_mouse(12.0, 20.0)
    state.update_mouse(15.0, 24.0, 3.0, 4.0)
    assert state.mouse_x == 15.0
    assert state.mouse_y == 24.0
    assert state.previous_mouse_x == 12.0
    assert state.previous_mouse_y == 20.0
    assert state.moved_x == 3.0
    assert state.moved_y == 4.0
    state.set_key_down(65, True)
    state.set_code_down("KeyA", True)
    assert state.key_is_down(65) is True
    assert state.code_is_down("KeyA") is True

    state.begin_shape_capture()
    state.add_vertex(0.0, 0.0)
    state.add_vertex(10.0, 0.0)
    state.add_vertex(10.0, 10.0)
    state.begin_contour_capture()
    state.add_vertex(2.0, 2.0)
    state.add_vertex(4.0, 2.0)
    state.add_vertex(4.0, 4.0)
    state.end_contour_capture()
    assert state.shape_vertices() == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    assert state.shape_contours() == [[(2.0, 2.0), (4.0, 2.0), (4.0, 4.0)]]
    state.reset_shape_capture()
    assert state.shape_active is False
