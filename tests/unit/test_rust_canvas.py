from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from p5 import Image
from p5 import constants as c
from p5.assets.image import P5Image
from p5.backends.canvas import CanvasBackend
from p5.backends.canvas_renderer import CanvasRenderer
from p5.context import SketchContext
from p5.core.color import Color
from p5.core.state import StyleState
from p5.core.transform import Matrix2D
from p5.exceptions import ArgumentValidationError, BackendCapabilityError
from p5.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from p5.rust import canvas as canvas_bridge
from p5.rust.canvas import (
    EXPECTED_CANVAS_ABI_VERSION,
    canvas_abi_version,
    canvas_gpu_available,
    canvas_gpu_status,
    canvas_health_check,
    canvas_import_error,
    canvas_native_window_available,
    is_canvas_available,
    require_canvas_extension,
)
from p5.sketch import Sketch


class FakeCanvas:
    def __init__(
        self,
        width: int,
        height: int,
        pixel_density: float,
        mode: str,
        renderer: str,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Canvas width and height must be positive.")
        if pixel_density <= 0:
            raise ValueError("Pixel density must be positive.")
        self.width = width
        self.height = height
        self.pixel_density = pixel_density
        self.mode = mode
        self.renderer = renderer
        self.physical_width = round(width * pixel_density)
        self.physical_height = round(height * pixel_density)
        self.calls: list[tuple[object, ...]] = []
        self.events: list[dict[str, object]] = []
        self.closed = False
        self.window_open = False
        self.pixels = bytes([0] * self.physical_width * self.physical_height * 4)

    def resize(self, width: int, height: int, pixel_density: float, renderer: str) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Canvas width and height must be positive.")
        if pixel_density <= 0:
            raise ValueError("Pixel density must be positive.")
        self.width = width
        self.height = height
        self.pixel_density = pixel_density
        self.renderer = renderer
        self.physical_width = round(width * pixel_density)
        self.physical_height = round(height * pixel_density)
        self.pixels = bytes([0] * self.physical_width * self.physical_height * 4)
        self.calls.append(("resize", width, height, pixel_density, renderer))

    def dimensions(self) -> tuple[int, int, int, int, float]:
        return (
            self.width,
            self.height,
            self.physical_width,
            self.physical_height,
            self.pixel_density,
        )

    def display_density(self) -> float:
        return 1.0 if not self.window_open else max(1.0, self.pixel_density)

    def gpu_available(self) -> bool:
        return True

    def gpu_status(self) -> str:
        return "available"

    def native_window_available(self) -> bool:
        return True

    def open_window(self) -> None:
        self.mode = "interactive"
        self.window_open = True
        self.closed = False
        self.calls.append(("open_window",))

    def should_close(self) -> bool:
        return self.closed

    def poll_events(self) -> list[dict[str, object]]:
        events = self.events
        self.events = []
        return events

    def begin_frame(self) -> None:
        self.calls.append(("begin_frame",))

    def end_frame(self) -> None:
        self.calls.append(("end_frame",))

    def present(self) -> None:
        self.calls.append(("present",))

    def close(self) -> None:
        self.closed = True
        self.calls.append(("close",))

    def background(self, rgba: tuple[int, int, int, int]) -> None:
        self.calls.append(("background", rgba))
        self.pixels = bytes(rgba) * (self.physical_width * self.physical_height)

    def clear(self) -> None:
        self.calls.append(("clear",))
        self.pixels = bytes([0] * self.physical_width * self.physical_height * 4)

    def point(self, *args: object) -> None:
        self.calls.append(("point", *args))

    def line(self, *args: object) -> None:
        self.calls.append(("line", *args))

    def batch_lines(self, *args: object) -> None:
        self.calls.append(("batch_lines", *args))

    def polygon(self, *args: object) -> None:
        self.calls.append(("polygon", *args))

    def rect(self, *args: object) -> None:
        self.calls.append(("rect", *args))

    def triangle(self, *args: object) -> None:
        self.calls.append(("triangle", *args))

    def quad(self, *args: object) -> None:
        self.calls.append(("quad", *args))

    def ellipse(self, *args: object) -> None:
        self.calls.append(("ellipse", *args))

    def arc(self, *args: object) -> None:
        self.calls.append(("arc", *args))

    def draw_image(self, *args: object) -> None:
        self.calls.append(("draw_image", *args))

    def draw_cached_image(self, *args: object) -> None:
        self.calls.append(("draw_cached_image", *args))

    def draw_canvas_image(self, *args: object) -> None:
        self.calls.append(("draw_canvas_image", *args))

    def text(self, *args: object) -> None:
        self.calls.append(("text", *args))

    def text_width(self, value: str, style: dict[str, object]) -> float:
        self.calls.append(("text_width", value, style))
        text_size = cast(float, style["text_size"])
        return len(value) * float(text_size) * 0.5

    def text_ascent(self, style: dict[str, object]) -> float:
        self.calls.append(("text_ascent", style))
        text_size = cast(float, style["text_size"])
        return float(text_size) * 0.8

    def text_descent(self, style: dict[str, object]) -> float:
        self.calls.append(("text_descent", style))
        text_size = cast(float, style["text_size"])
        return float(text_size) * 0.2

    def load_pixels(self) -> bytes:
        return self.pixels

    def load_pixel_bytes(self) -> bytes:
        return self.pixels

    def update_pixels(self, pixels: bytes) -> None:
        expected = self.physical_width * self.physical_height * 4
        if len(pixels) != expected:
            raise ValueError(f"Pixel buffer length must be {expected}, got {len(pixels)}.")
        self.pixels = pixels

    def blend_region(self, *args: object) -> None:
        self.calls.append(("blend_region", *args))

    def save(self, path: str) -> None:
        self.calls.append(("save", path))
        Path(path).write_bytes(b"fake-png")


class FakeCanvasModule:
    CANVAS_ABI_VERSION = EXPECTED_CANVAS_ABI_VERSION
    Canvas = FakeCanvas

    def canvas_abi_version(self) -> int:
        return EXPECTED_CANVAS_ABI_VERSION

    def health_check(self) -> str:
        return "fake-canvas"

    def native_window_available(self) -> bool:
        return True

    def gpu_available(self) -> bool:
        return True


class FakeCanvasModuleWithoutNativeWindow(FakeCanvasModule):
    class Canvas(FakeCanvas):
        def native_window_available(self) -> bool:
            return False

    def native_window_available(self) -> bool:
        return False


class FakeCanvasModuleWithoutGpu(FakeCanvasModule):
    def gpu_available(self) -> bool:
        return False


class FakeCanvasModuleWithHealthFailure(FakeCanvasModule):
    def health_check(self) -> str:
        raise RuntimeError("boom")


class FakeCanvasModuleWithoutAbi(FakeCanvasModule):
    CANVAS_ABI_VERSION = None

    def canvas_abi_version(self) -> object:
        return None


class FakeCanvasModuleWithBadAbi(FakeCanvasModule):
    CANVAS_ABI_VERSION = EXPECTED_CANVAS_ABI_VERSION + 1

    def canvas_abi_version(self) -> int:
        return EXPECTED_CANVAS_ABI_VERSION + 1


class FakeRustImage:
    width = 2
    height = 1
    version = 0

    def save(self, path: str) -> None:
        Path(path).write_bytes(b"fake-image")

    def to_rgba_bytes(self) -> bytes:
        return bytes([255, 0, 0, 255, 0, 0, 255, 255])


class FakeSketch:
    def __init__(self) -> None:
        self.frames = 0
        self.context = None

    def _draw_frame(self) -> None:
        self.frames += 1


class EventSketch(Sketch):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[object, ...]] = []

    def mouse_pressed(self, event) -> None:
        self.events.append(("mouse_pressed", event.x, event.y, event.button))

    def mouse_dragged(self, event) -> None:
        self.events.append(("mouse_dragged", event.x, event.y, event.dx, event.dy))

    def mouse_wheel(self, event) -> None:
        self.events.append(("mouse_wheel", event.x, event.y, event.scroll_x, event.scroll_y))

    def key_pressed(self, event) -> None:
        self.events.append(("key_pressed", event.key, event.key_code))

    def key_released(self, event) -> None:
        self.events.append(("key_released", event.key, event.key_code))

    def key_typed(self, event) -> None:
        self.events.append(("key_typed", event.key, event.key_code))


def make_canvas_context(monkeypatch: pytest.MonkeyPatch) -> tuple[EventSketch, CanvasBackend]:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend()
    sketch = EventSketch()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    sketch._running = True
    context.create_canvas(100, 50, pixel_density=2)
    return sketch, backend


def test_canvas_health_check_reports_unavailable_or_extension() -> None:
    assert canvas_health_check() in {"unavailable", "rust-canvas"}
    assert canvas_abi_version() in {None, EXPECTED_CANVAS_ABI_VERSION}
    assert canvas_native_window_available() in {True, False}
    assert canvas_gpu_available() in {True, False}
    assert canvas_gpu_status()
    assert is_canvas_available() in {True, False}
    assert canvas_import_error() is None or isinstance(canvas_import_error(), ImportError)


def test_canvas_wrapper_uses_loaded_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCanvasModule()
    monkeypatch.setattr(canvas_bridge, "_canvas", fake)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    assert is_canvas_available()
    assert canvas_health_check() == "fake-canvas"
    assert canvas_abi_version() == EXPECTED_CANVAS_ABI_VERSION
    assert canvas_native_window_available() is True
    assert canvas_gpu_available() is True
    assert canvas_gpu_status() == "available"
    assert require_canvas_extension() is fake


def test_canvas_wrapper_raises_capability_error_when_extension_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", None)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", ImportError("missing _canvas"))

    with pytest.raises(BackendCapabilityError, match="p5.rust._canvas"):
        require_canvas_extension()


@pytest.mark.parametrize(
    ("module", "message"),
    [
        (FakeCanvasModuleWithoutAbi(), "expected canvas ABI"),
        (FakeCanvasModuleWithBadAbi(), "expected canvas ABI"),
        (FakeCanvasModuleWithHealthFailure(), "failed its health check"),
    ],
)
def test_canvas_wrapper_rejects_incompatible_or_unhealthy_extensions(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    message: str,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", module)
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    with pytest.raises(BackendCapabilityError, match=message):
        require_canvas_extension()


def test_canvas_gpu_status_explains_cpu_continuation_when_gpu_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModuleWithoutGpu())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    assert canvas_gpu_available() is False
    assert "headless rendering can continue" in canvas_gpu_status()


def test_canvas_backend_reports_implemented_capabilities() -> None:
    capabilities = CanvasBackend.capabilities

    assert capabilities.interactive is False
    assert capabilities.headless is True
    assert capabilities.text is True
    assert capabilities.images is True
    assert capabilities.pixels is True
    assert capabilities.pixel_readback is True
    assert capabilities.pixel_update is True
    assert capabilities.canvas_export is True
    assert capabilities.mouse is False
    assert capabilities.keyboard is False
    assert capabilities.touch is False
    assert capabilities.paths is True
    assert capabilities.transforms is True
    assert capabilities.blend_modes == frozenset(
        {
            c.BLEND,
            c.REPLACE,
            c.ADD,
            c.DARKEST,
            c.LIGHTEST,
            c.DIFFERENCE,
            c.EXCLUSION,
            c.MULTIPLY,
            c.SCREEN,
        }
    )
    assert capabilities.three_d is True
    assert capabilities.shaders is True
    assert capabilities.sound is True


def test_canvas_backend_enables_input_capabilities_when_native_runtime_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend()

    assert backend.capabilities.interactive is True
    assert backend.capabilities.mouse is True
    assert backend.capabilities.keyboard is True
    assert backend.capabilities.touch is True


def test_canvas_backend_rejects_interactive_without_native_window_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModuleWithoutNativeWindow())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend(headless=False)
    backend.create_canvas(10, 10)

    with pytest.raises(BackendCapabilityError, match="native window support"):
        backend.run(FakeSketch())  # type: ignore[arg-type]


def test_canvas_backend_gpu_status_uses_runtime_canvas_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModuleWithoutGpu())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend()
    assert "headless rendering can continue" in backend.gpu_status()


def test_canvas_backend_runs_headless_frames_and_accepts_webgl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)

    backend = CanvasBackend()
    backend.create_canvas(10, 5, pixel_density=2)

    assert backend.health_check() == "fake-canvas"
    assert backend.renderer.width == 10
    assert backend.renderer.physical_width == 20
    assert backend.display_density() == 1.0

    sketch = FakeSketch()
    backend.run(sketch, max_frames=2)  # type: ignore[arg-type]
    assert sketch.frames == 2

    backend.create_canvas(10, 10, renderer=c.WEBGL)
    assert backend.renderer.width == 10


def test_canvas_backend_repeated_create_canvas_preserves_existing_pixel_density(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend()
    backend.create_canvas(100, 50, pixel_density=2)

    backend.create_canvas(100, 50)

    assert backend.renderer.pixel_density == 2
    assert backend.renderer.physical_width == 200


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


def test_canvas_renderer_pixels_and_save_round_trip(tmp_path: Path) -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(2, 1)

    renderer.background(Color(10, 20, 30, 255))
    assert renderer.load_pixels() == [10, 20, 30, 255, 10, 20, 30, 255]

    renderer.update_pixels([255, 0, 0, 255, 0, 0, 255, 255])
    assert renderer.load_pixels() == [255, 0, 0, 255, 0, 0, 255, 255]
    assert renderer.load_pixel_bytes() == bytes([255, 0, 0, 255, 0, 0, 255, 255])

    output = tmp_path / "canvas.png"
    renderer.save(output)
    assert output.read_bytes() == b"fake-png"


def test_canvas_renderer_bridges_images_and_blend_regions() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 2)
    image = Image(2, 1, bytes([255, 0, 0, 255, 255, 0, 0, 255]))
    style = StyleState(fill_color=None, stroke_color=None)
    transform = Matrix2D.identity()

    renderer.draw_image(image, 1, 0, 2, 1, style, transform, source=(0, 0, 1, 1))
    renderer.blend_region(image, (0, 0, 1, 1), (0, 1, 1, 1), c.ADD)
    renderer.blend_region(None, (0, 0, 1, 1), (1, 1, 1, 1), c.BLEND)

    canvas = renderer._canvas
    assert canvas is not None
    assert canvas.calls[-3][0] == "draw_cached_image"
    assert canvas.calls[-3][1] == image.cache_key
    assert canvas.calls[-3][2] == image.version
    assert canvas.calls[-3][3] == image.to_rgba_bytes()
    assert canvas.calls[-3][4:6] == (2, 1)
    assert canvas.calls[-3][-1] == (0, 0, 1, 1)
    assert canvas.calls[-2] == (
        "blend_region",
        image.to_rgba_bytes(),
        2,
        1,
        (0, 0, 1, 1),
        (0, 1, 1, 1),
        c.ADD,
    )
    assert canvas.calls[-1] == (
        "blend_region",
        None,
        None,
        None,
        (0, 0, 1, 1),
        (1, 1, 1, 1),
        c.BLEND,
    )


def test_canvas_renderer_uses_stable_image_cache_keys_and_versions() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 2)
    style = StyleState(fill_color=None, stroke_color=None)
    transform = Matrix2D.identity()
    first = Image(1, 1, bytes([255, 0, 0, 255]))
    second = Image(1, 1, bytes([0, 255, 0, 255]))

    renderer.draw_image(first, 0, 0, 1, 1, style, transform)
    renderer.draw_image(second, 1, 0, 1, 1, style, transform)
    first.update_pixels(bytes([0, 0, 255, 255]))
    renderer.draw_image(first, 2, 0, 1, 1, style, transform)

    canvas = renderer._canvas
    assert canvas is not None
    draw_calls = [call for call in canvas.calls if call[0] == "draw_cached_image"]
    assert draw_calls[0][1] != draw_calls[1][1]
    assert draw_calls[0][1] == first.cache_key
    assert draw_calls[2][1] == first.cache_key
    assert draw_calls[2][2] == first.version
    assert draw_calls[2][3] == first.to_rgba_bytes()


def test_canvas_renderer_prefers_rust_managed_image_until_mutation() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 2)
    style = StyleState(fill_color=None, stroke_color=None)
    transform = Matrix2D.identity()
    image = Image.from_rust_image(P5Image(FakeRustImage()))

    renderer.draw_image(image, 0, 0, 2, 1, style, transform)
    image.set(0, 0, (0, 0, 255, 255))
    renderer.draw_image(image, 0, 1, 2, 1, style, transform)

    canvas = renderer._canvas
    assert canvas is not None
    assert [call[0] for call in canvas.calls][-2:] == ["draw_canvas_image", "draw_cached_image"]


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


def test_canvas_renderer_performance_counters_cover_representative_paths() -> None:
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(4, 2)
    style = StyleState(fill_color=Color(255, 255, 255, 255), stroke_color=Color(0, 0, 0, 255))
    image = Image(1, 1, bytes([255, 0, 0, 255]))
    transform = Matrix2D.identity()

    renderer.background(Color(0, 0, 0, 255))
    renderer.line(0, 0, 3, 1, style, transform)
    renderer.end_frame()
    renderer.draw_image(image, 0, 0, 1, 1, style, transform)
    renderer.draw_image(image, 1, 0, 1, 1, style, transform)
    renderer.text_width("cached", style)
    renderer.text_width("cached", style)
    renderer.load_pixels()
    renderer.update_pixels(bytes([0, 0, 0, 255] * 8))
    renderer.blend_region(None, (0, 0, 1, 1), (1, 0, 1, 1), c.BLEND)

    counters = cast(dict[str, int], renderer.performance_counters())

    assert counters["gpu_draws"] >= 4
    assert counters["image_cache_misses"] == 1
    assert counters["image_cache_hits"] == 1
    assert counters["texture_uploads"] == 1
    assert counters["texture_cache_hits"] == 1
    assert counters["text_cache_misses"] == 1
    assert counters["text_cache_hits"] == 1
    assert counters["text_cache_evictions"] == 0
    assert counters["pixel_readbacks"] >= 1
    assert counters["pixel_uploads"] >= 2
    assert counters["cpu_fallbacks"] >= 1
    assert counters["bridge_calls"] > 0

    renderer.reset_performance_counters()
    reset = renderer.performance_counters()
    assert reset["gpu_draws"] == 0
    assert reset["bridge_calls"] == 0
    assert reset["text_cache_evictions"] == 0


def test_canvas_backend_headless_run_defaults_to_requested_frame_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend()
    backend.create_canvas(8, 8)
    sketch = FakeSketch()

    backend.run(sketch, max_frames=0)  # type: ignore[arg-type]
    assert sketch.frames == 0

    backend.run(sketch)  # type: ignore[arg-type]
    assert sketch.frames == 1

    backend.run(sketch, max_frames=3)  # type: ignore[arg-type]
    assert sketch.frames == 4
    canvas = backend.renderer.runtime_canvas()
    assert ("present",) in canvas.calls


def test_canvas_backend_frame_pacing_diagnostics_are_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    assert sketch.context is not None
    sketch.context.enable_frame_pacing_diagnostics()

    backend.run(sketch, max_frames=2)

    report = cast(dict[str, bool | float | int | None], sketch.context.frame_pacing_diagnostics())
    assert report["enabled"] is True
    assert report["frames"] == 2
    assert report["last_draw_duration_ms"] is not None
    assert report["last_present_duration_ms"] is not None
    assert report["mean_draw_duration_ms"] is not None
    assert report["mean_present_duration_ms"] is not None
    assert report["mean_draw_duration_ms"] >= 0.0
    assert report["mean_present_duration_ms"] >= 0.0

    sketch.context.reset_frame_pacing_diagnostics()
    reset = cast(dict[str, bool | float | int | None], sketch.context.frame_pacing_diagnostics())
    assert reset["frames"] == 0


def test_canvas_backend_opens_interactive_window_and_reports_display_density(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    canvas = backend.renderer.runtime_canvas()

    canvas.events.append({"type": "close"})
    backend._run_interactive(sketch)

    assert ("open_window",) in canvas.calls
    assert backend.display_density() == 2.0
    assert canvas.closed is True


def test_canvas_backend_interactive_max_frames_stops_after_requested_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._run_interactive(sketch, max_frames=1)

    assert sketch.context is not None
    assert sketch.context.frame_count == 1


def test_canvas_backend_interactive_max_frames_exits_when_paused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    assert sketch.context is not None
    sketch.context.no_loop()

    backend._run_interactive(sketch, max_frames=1)

    assert sketch.context.frame_count == 0


def test_canvas_backend_unbounded_interactive_respects_no_loop_from_draw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    assert sketch.context is not None
    context = sketch.context
    canvas = backend.renderer.runtime_canvas()
    polls = 0

    def poll_events() -> list[dict[str, object]]:
        nonlocal polls
        polls += 1
        if polls >= 5:
            canvas.closed = True
        return []

    def draw_frame() -> None:
        context.state.timing.frame_count += 1
        context.no_loop()

    canvas.poll_events = poll_events  # type: ignore[method-assign]
    sketch._draw_frame = draw_frame  # type: ignore[method-assign]
    monkeypatch.setattr("p5.backends.canvas.time.sleep", lambda _delay: None)

    backend._run_interactive(sketch)

    assert sketch.context.frame_count == 1
    assert polls >= 5


def test_canvas_backend_unbounded_context_run_uses_interactive_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)
    canvas = backend.renderer.runtime_canvas()
    canvas.events.append({"type": "close"})

    backend.run(sketch)

    assert ("open_window",) in canvas.calls


def test_canvas_backend_explicit_headless_suppresses_unbounded_interactive_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canvas_bridge, "_canvas", FakeCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend(headless=True)
    sketch = EventSketch()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    sketch._running = True
    context.create_canvas(100, 50, pixel_density=2)
    canvas = backend.renderer.runtime_canvas()

    backend.run(sketch)

    assert ("open_window",) not in canvas.calls
    assert sketch.context.frame_count == 1


def test_canvas_backend_dispatches_mouse_events_with_logical_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._dispatch_canvas_event(
        sketch,
        {"type": "mouse_pressed", "x": 20, "y": 10, "button": 1, "modifiers": 4},
    )
    backend._dispatch_canvas_event(
        sketch,
        {"type": "mouse_dragged", "x": 24, "y": 6, "dx": 4, "dy": -8, "button": "left"},
    )
    backend._dispatch_canvas_event(
        sketch,
        {"type": "mouse_wheel", "x": 24, "y": 6, "scroll_x": 1, "scroll_y": -2},
    )

    assert sketch.context is not None
    assert sketch.context.mouse_x == 12
    assert sketch.context.mouse_y == 3
    assert sketch.context.mouse_is_pressed is True
    assert sketch.context.mouse_button == c.LEFT_BUTTON
    assert sketch.events == [
        ("mouse_pressed", 10, 5, c.LEFT_BUTTON),
        ("mouse_dragged", 12, 3, 2, -4),
        ("mouse_wheel", 12, 3, 1, -2),
    ]


def test_canvas_backend_dispatches_keyboard_events_and_pressed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._dispatch_canvas_event(sketch, {"type": "key_pressed", "key": "a"})
    backend._dispatch_canvas_event(sketch, {"type": "key_released", "key": "a"})
    backend._dispatch_canvas_event(sketch, {"type": "key_pressed", "code": "ArrowLeft"})
    backend._dispatch_canvas_event(sketch, {"type": "key_typed", "text": "é"})

    assert sketch.context is not None
    assert sketch.context.key_is_down(ord("a")) is False
    assert sketch.context.key_is_down(c.LEFT_ARROW) is True
    assert sketch.events == [
        ("key_pressed", "a", ord("a")),
        ("key_released", "a", ord("a")),
        ("key_pressed", None, c.LEFT_ARROW),
        ("key_typed", "é", ord("é")),
    ]


def test_canvas_backend_dispatches_touch_events_with_logical_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._dispatch_canvas_event(
        sketch,
        {
            "type": "touch_started",
            "id": 7,
            "x": 20,
            "y": 10,
            "pressure": 0.5,
            "phase": "started",
            "timestamp": 1.25,
            "device": "screen",
        },
    )
    backend._dispatch_canvas_event(
        sketch,
        {"type": "touch_moved", "id": 7, "x": 24, "y": 6, "pressure": 0.75},
    )

    assert sketch.context is not None
    touch = sketch.context.touches[0]
    assert touch.id == 7
    assert (touch.x, touch.y) == (12, 3)
    assert (touch.previous_x, touch.previous_y) == (10, 5)
    assert touch.pressure == 0.75

    backend._dispatch_canvas_event(sketch, {"type": "touch_ended", "id": 7, "x": 24, "y": 6})
    assert sketch.context.touches == []


def test_canvas_backend_handles_resize_events(monkeypatch: pytest.MonkeyPatch) -> None:
    sketch, backend = make_canvas_context(monkeypatch)

    backend._dispatch_canvas_event(
        sketch,
        {"type": "resized", "width": 120, "height": 80, "pixel_density": 1.5},
    )

    assert backend.renderer.width == 120
    assert backend.renderer.height == 80
    assert backend.renderer.physical_width == 180
    assert backend.renderer.physical_height == 120
    assert sketch.context is not None
    assert sketch.context.width == 120
    assert sketch.context.height == 80


def test_canvas_backend_caps_oversized_interactive_resize_density(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LimitedTextureCanvas(FakeCanvas):
        def resize(self, width: int, height: int, pixel_density: float, renderer: str) -> None:
            physical_width = round(width * pixel_density)
            if physical_width > 2048:
                raise ValueError(
                    "Canvas physical width "
                    f"{physical_width} exceeds the GPU texture limit of 2048. "
                    "Reduce create_canvas() width or pixel_density()."
                )
            super().resize(width, height, pixel_density, renderer)

    class LimitedTextureCanvasModule(FakeCanvasModule):
        Canvas = LimitedTextureCanvas

    monkeypatch.setattr(canvas_bridge, "_canvas", LimitedTextureCanvasModule())
    monkeypatch.setattr(canvas_bridge, "_CANVAS_IMPORT_ERROR", None)
    backend = CanvasBackend()
    sketch = EventSketch()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    sketch._running = True
    context.create_canvas(100, 50, pixel_density=2)

    backend._dispatch_canvas_event(
        sketch,
        {"type": "resized", "width": 1200, "height": 800, "pixel_density": 2},
    )

    assert backend.renderer.width == 1200
    assert backend.renderer.height == 800
    assert backend.renderer.physical_width <= 2048
    assert backend.renderer.pixel_density < 2
    assert context.width == 1200
    assert context.height == 800
    assert context.pixel_density() < 2


def test_canvas_next_frame_delay_skips_missed_frames() -> None:
    backend = CanvasBackend.__new__(CanvasBackend)
    backend._next_frame_time = 0.0
    interval = 1.0 / 60.0

    first_delay = backend._next_frame_delay(0.002, interval)
    delayed = backend._next_frame_delay(0.250, interval)

    assert first_delay == interval - 0.002
    assert 0.0 < delayed <= interval
    assert backend._next_frame_time > 0.250
