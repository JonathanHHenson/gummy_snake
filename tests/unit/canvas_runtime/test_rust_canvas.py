from __future__ import annotations

from struct import pack

import pytest

from gummysnake import Image
from gummysnake import constants as c
from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.backend.canvas_runtime.renderer.command_ingress import (
    EFFECT_RECORD,
    FRAME_COMMAND_ABI_VERSION,
    IMAGE_RECORD,
    TEXT_RECORD,
    pack_filter_effect,
    pack_matrix,
    pack_path,
    pack_primitive_style,
)
from gummysnake.core.state_facades import StyleState
from gummysnake.core.transform import Matrix2D
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
from tests.helpers.canvas_runtime.context import (
    install_fake_canvas_runtime,
    install_missing_canvas_runtime,
)
from tests.helpers.canvas_runtime.modules import (
    FakeCanvasModule,
    FakeCanvasModuleWithBadAbi,
    FakeCanvasModuleWithHealthFailure,
    FakeCanvasModuleWithoutAbi,
    FakeCanvasModuleWithoutGpu,
)


def _packed_test_style(fill: tuple[int, int, int, int] = (255, 0, 0, 255)) -> dict[str, object]:
    return {
        "fill": fill,
        "stroke": (255, 255, 255, 255),
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


def test_canvas_health_check_reports_required_runtime() -> None:
    assert canvas_health_check() == "rust-canvas"
    assert canvas_abi_version() == EXPECTED_CANVAS_ABI_VERSION
    provenance = require_canvas_runtime().benchmark_provenance()
    assert provenance["canvas_crate_version"]
    assert provenance["renderer"] == "wgpu-high-performance-adapter"
    assert provenance["ecs_crate_version"]
    assert provenance["synth_crate_version"]
    assert isinstance(provenance["features"], list)
    assert provenance["gpu_available"] in {True, False}
    assert canvas_native_window_available() in {True, False}
    assert canvas_gpu_available() in {True, False}
    assert canvas_gpu_status()
    assert is_canvas_runtime_available() is True
    assert canvas_import_error() is None
    runtime = require_canvas_runtime()
    assert runtime.frame_command_abi_version() == FRAME_COMMAND_ABI_VERSION
    assert runtime.FRAME_COMMAND_ABI_VERSION == FRAME_COMMAND_ABI_VERSION


def test_renderer_exposes_zero_copy_gpu_command_stream_counters() -> None:
    if not canvas_gpu_available():
        pytest.skip("GPU renderer is unavailable")
    renderer = CanvasRenderer(require_canvas_runtime())
    renderer.resize(8, 8)
    renderer.reset_performance_counters()

    counters = renderer.performance_counters()
    native = counters["native"]
    assert isinstance(native, dict)

    assert native["gpu_command_clone_count"] == 0
    assert native["gpu_command_clone_bytes"] == 0
    assert native["gpu_command_segment_allocation_count"] == 0


def test_canvas_image_batches_share_sources_and_upload_only_dirty_generations() -> None:
    if not canvas_gpu_available():
        pytest.skip("GPU renderer is unavailable")
    renderer = CanvasRenderer(require_canvas_runtime())
    renderer.resize(8, 8)
    image = Image(1, 1, bytes([255, 0, 0, 255]))
    style = StyleState(fill_color=None, stroke_color=None)
    transform = Matrix2D.identity()

    renderer.reset_performance_counters()
    renderer.draw_image(image, 0, 0, 1, 1, style, transform)
    renderer.draw_image(image, 1, 0, 1, 1, style, transform)
    renderer.end_frame()
    first = renderer.performance_counters()
    assert first["image_source_clones_avoided"] == 2
    assert first["image_source_clone_bytes_avoided"] == 8
    assert first["texture_uploads"] == 1
    assert first["texture_upload_bytes"] == 36
    assert first["texture_dirty_uploads"] == 0
    assert first["texture_resident_bytes"] >= 4
    assert first["image_atlas_resident_bytes"] == first["texture_resident_bytes"]

    renderer.reset_performance_counters()
    renderer.draw_image(image, 0, 0, 1, 1, style, transform)
    renderer.draw_image(image, 1, 0, 1, 1, style, transform)
    renderer.end_frame()
    unchanged = renderer.performance_counters()
    assert unchanged["image_source_clones_avoided"] == 2
    assert unchanged["image_source_clone_bytes_avoided"] == 8
    assert unchanged["texture_uploads"] == 0
    assert unchanged["texture_dirty_uploads"] == 0
    assert unchanged["texture_resident_bytes"] == first["texture_resident_bytes"]

    image.update_pixels(bytes([0, 0, 255, 255]))
    renderer.reset_performance_counters()
    renderer.draw_image(image, 0, 0, 1, 1, style, transform)
    renderer.end_frame()
    mutated = renderer.performance_counters()
    assert mutated["texture_uploads"] == 1
    assert mutated["texture_upload_bytes"] == 36
    assert mutated["texture_dirty_uploads"] == 1
    assert mutated["texture_destructions"] == 0
    assert mutated["image_atlas_destructions"] == 0
    assert mutated["texture_resident_bytes"] == first["texture_resident_bytes"]


def test_canvas_packed_primitive_protocol_reports_records_and_bytes() -> None:
    runtime = require_canvas_runtime()
    canvas = runtime.Canvas(16, 16, 1.0, "headless", "p2d")
    style = _packed_test_style()
    matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    primitive = pack("<B7x6d", 1, 1.0, 2.0, 3.0, 4.0, 0.0, 0.0)
    mixed = pack("<B7x6dII", 3, 8.0, 8.0, 2.0, 2.0, 0.0, 0.0, 0, 0)
    packed_style = pack_primitive_style(style)
    packed_matrix = pack_matrix(matrix)
    fill = pack("<B7x6d4B", 2, 1.0, 1.0, 4.0, 1.0, 1.0, 4.0, 0, 255, 0, 255)
    line = pack("<4d", 0.0, 0.0, 15.0, 15.0)
    canvas.set_current_style(style)

    canvas.batch_primitives_packed(primitive, style, matrix)
    canvas.batch_primitives_current_packed(primitive)
    canvas.batch_primitives_mixed_packed(mixed, packed_style, packed_matrix)
    canvas.batch_fill_primitives_packed(fill, matrix)
    canvas.batch_lines_packed(line, style, matrix)
    canvas.batch_lines_current_packed(line)

    counters = canvas.performance_counters()
    assert counters["packed_primitive_records"] == 6
    assert counters["packed_primitive_bytes"] == 372
    assert counters["typed_primitive_records"] == 6
    diagnostics = canvas.frame_command_diagnostics()
    assert diagnostics["abi_version"] == FRAME_COMMAND_ABI_VERSION
    assert diagnostics["records"] == 6
    assert diagnostics["families"] == ["primitive"] * 6


def test_canvas_typed_frame_commands_cover_ordered_path_image_text_and_effect_families() -> None:
    if not canvas_gpu_available():
        pytest.skip("GPU renderer is unavailable")
    runtime = require_canvas_runtime()
    canvas = runtime.Canvas(16, 16, 1.0, "headless", "p2d")
    style = _packed_test_style(fill=(255, 255, 255, 255))
    matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    points, contours = pack_path([(0.0, 0.0), (4.0, 0.0), (0.0, 4.0)])
    image = runtime.CanvasImage.from_rgba_bytes(1, 1, bytes([255, 0, 0, 255]))
    image_record = IMAGE_RECORD.pack(
        0,
        0,
        2.0,
        2.0,
        1.0,
        1.0,
        0,
        0,
        0,
        0,
        *matrix,
    )
    text_payload = b"typed"
    text_record = TEXT_RECORD.pack(0, len(text_payload), 1.0, 12.0)

    canvas.begin_frame()
    canvas.polygon_packed(points, contours, style, matrix, True)
    canvas.batch_canvas_images_packed(image_record, [image], style)
    canvas.text_batch_packed(text_record, text_payload, style, matrix)
    canvas.apply_effects_packed(pack_filter_effect(c.INVERT, None))

    counters = canvas.performance_counters()
    assert counters["typed_path_records"] == 3
    assert counters["typed_image_records"] == 1
    assert counters["typed_text_records"] == 1
    assert counters["typed_effect_records"] == 1
    assert counters["typed_order_barriers"] == 1
    diagnostics = canvas.frame_command_diagnostics()
    assert diagnostics["families"] == ["path", "image", "text", "effect", "barrier"]
    assert diagnostics["storage_bytes"] == diagnostics["segment_bytes"]


def test_canvas_typed_frame_commands_reject_malformed_family_records_transactionally() -> None:
    runtime = require_canvas_runtime()
    canvas = runtime.Canvas(16, 16, 1.0, "headless", "p2d")
    style = _packed_test_style()
    matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    image = runtime.CanvasImage.from_rgba_bytes(1, 1, bytes([255, 0, 0, 255]))
    model = runtime.create_box_model_handle(1.0, None, None)
    malformed_calls = (
        lambda: canvas.polygon_packed(b"bad", pack("<I", 0), style, matrix, True),
        lambda: canvas.batch_canvas_images_packed(b"bad", [image], style),
        lambda: canvas.text_batch_packed(TEXT_RECORD.pack(2, 4, 0.0, 0.0), b"x", style, matrix),
        lambda: canvas.apply_effects_packed(EFFECT_RECORD.pack(99, 0, 0, 0, 0, 0, 0.0)),
        lambda: canvas._draw_model_shaded_batch_packed(
            model,
            {},
            {},
            16.0,
            16.0,
            {},
            [],
            False,
            True,
            b"bad",
        ),
        lambda: canvas._draw_model_shaded_batch_translation_quaternion_packed(
            model,
            {},
            {},
            16.0,
            16.0,
            {},
            [],
            False,
            True,
            b"bad",
        ),
    )

    for malformed_call in malformed_calls:
        with pytest.raises(ValueError):
            malformed_call()

    counters = canvas.performance_counters()
    assert counters["typed_frame_command_records"] == 0
    assert canvas.frame_command_diagnostics()["segments"] == 0


def test_canvas_packed_protocol_rejects_malformed_batches_transactionally() -> None:
    runtime = require_canvas_runtime()
    canvas = runtime.Canvas(16, 16, 1.0, "headless", "p2d")
    style = _packed_test_style()
    matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    invalid_reserved = bytearray(pack("<B7x6d", 1, 1.0, 2.0, 3.0, 4.0, 0.0, 0.0))
    invalid_reserved[1] = 1
    invalid_fill_reserved = bytearray(
        pack("<B7x6d4B", 1, 1.0, 2.0, 3.0, 4.0, 0.0, 0.0, 255, 0, 0, 255)
    )
    invalid_fill_reserved[7] = 1
    invalid_mixed_reserved = bytearray(pack("<B7x6dII", 1, 1.0, 2.0, 3.0, 4.0, 0.0, 0.0, 0, 0))
    packed_style = pack_primitive_style(style)
    packed_matrix = pack_matrix(matrix)
    invalid_mixed_reserved[3] = 1

    invalid_calls = (
        lambda: canvas.batch_lines_packed(b"invalid", style, matrix),
        lambda: canvas.batch_primitives_packed(b"invalid", style, matrix),
        lambda: canvas.batch_primitives_packed(bytes(invalid_reserved), style, matrix),
        lambda: canvas.batch_primitives_packed(
            pack("<B7x6d", 99, 1.0, 2.0, 3.0, 4.0, 0.0, 0.0), style, matrix
        ),
        lambda: canvas.batch_fill_primitives_packed(b"invalid", matrix),
        lambda: canvas.batch_fill_primitives_packed(bytes(invalid_fill_reserved), matrix),
        lambda: canvas.batch_primitives_mixed_packed(b"invalid", packed_style, packed_matrix),
        lambda: canvas.batch_primitives_mixed_packed(
            bytes(invalid_mixed_reserved), packed_style, packed_matrix
        ),
        lambda: canvas.batch_primitives_mixed_packed(
            pack("<B7x6dII", 1, 1.0, 2.0, 3.0, 4.0, 0.0, 0.0, 1, 0),
            packed_style,
            packed_matrix,
        ),
        lambda: canvas.batch_primitives_mixed_packed(
            pack("<B7x6dII", 1, 1.0, 2.0, 3.0, 4.0, 0.0, 0.0, 0, 1),
            packed_style,
            packed_matrix,
        ),
    )
    for invalid_call in invalid_calls:
        with pytest.raises(ValueError):
            invalid_call()

    counters = canvas.performance_counters()
    assert counters["packed_primitive_records"] == 0
    assert counters["packed_primitive_bytes"] == 0
    assert counters["native_primitive_records"] == 0


def test_canvas_exposes_only_packed_batch_ingress() -> None:
    runtime = require_canvas_runtime()
    canvas = runtime.Canvas(8, 8, 1.0, "headless", "p2d")

    for removed_name in (
        "batch_lines",
        "batch_lines_current",
        "batch_primitives",
        "batch_primitives_current",
        "batch_primitives_mixed",
        "batch_fill_primitives",
    ):
        assert not hasattr(canvas, removed_name)


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


@pytest.mark.parametrize("marker", ["18", 18.0, True])
def test_canvas_wrapper_rejects_malformed_abi_markers(
    monkeypatch: pytest.MonkeyPatch, marker: object
) -> None:
    runtime = FakeCanvasModule()
    monkeypatch.setattr(runtime, "canvas_abi_version", lambda: marker)
    install_fake_canvas_runtime(monkeypatch, runtime)

    with pytest.raises(BackendCapabilityError, match="expected canvas ABI") as error:
        require_canvas_runtime()

    assert "maturin develop --release" in str(error.value)


@pytest.mark.parametrize("health", [None, "", "unavailable", 1])
def test_canvas_wrapper_rejects_malformed_health_status(
    monkeypatch: pytest.MonkeyPatch, health: object
) -> None:
    runtime = FakeCanvasModule()
    monkeypatch.setattr(runtime, "health_check", lambda: health)
    install_fake_canvas_runtime(monkeypatch, runtime)

    with pytest.raises(BackendCapabilityError, match="unhealthy runtime state"):
        require_canvas_runtime()


def test_canvas_gpu_status_explains_headless_compatibility_when_gpu_unavailable(
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


def test_canvas_shaded_faces_requires_retained_gpu_model_path() -> None:
    runtime = require_canvas_runtime()
    canvas = runtime.Canvas(64, 64, 1.0, "headless", "p2d")
    canvas.background((0, 0, 0, 255))

    with pytest.raises(ValueError, match="CPU projected-face payload drawing is disabled"):
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
