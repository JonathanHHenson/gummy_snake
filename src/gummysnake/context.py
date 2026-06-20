"""Sketch context containing mutable runtime state."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from gummysnake import constants as c
from gummysnake._context_3d import ThreeDContextMixin
from gummysnake._context_helpers import image_draw_args
from gummysnake._context_input import InputContextMixin
from gummysnake._context_pixels import PixelContextMixin
from gummysnake._fast_draw import FastDrawScope
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.assets.text import Font
from gummysnake.core import math as gs_math
from gummysnake.core.color import Color, lerp_color
from gummysnake.core.geometry import (
    flatten_cubic,
    flatten_quadratic,
    flatten_spline,
    resolve_ellipse,
    resolve_rect,
)
from gummysnake.core.geometry import (
    spline_point as geometry_spline_point,
)
from gummysnake.core.geometry import (
    spline_tangent as geometry_spline_tangent,
)
from gummysnake.core.state import SketchState, StateStackEntry
from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    OrthographicProjection,
    PerspectiveProjection,
    Shader3D,
    Texture3D,
)
from gummysnake.exceptions import (
    ArgumentValidationError,
    BackendCapabilityError,
)

if TYPE_CHECKING:
    from gummysnake.plugins.registry import PluginRegistry

_MATERIAL_UNSET = object()
_PERFORMANCE_DIAGNOSTIC_MESSAGE_LIMIT = 64

_PERFORMANCE_DIAGNOSTIC_MESSAGES = {
    "cpu_compositing_fallback": (
        "CPU compositing fallback: this operation reads the canvas into a Python Image "
        "and writes pixels back. Prefer renderer-native drawing APIs in animation loops."
    ),
    "pixel_list_conversion": (
        "Pixel list conversion: this path materializes RGBA bytes as a Python list. "
        "Use load_pixel_bytes() when a bytes-like buffer is enough."
    ),
    "pixel_readback": (
        "Pixel readback: this operation reads the current canvas pixels back to Python. "
        "Avoid it per frame unless the sketch really needs pixel data."
    ),
    "pixel_upload": (
        "Pixel upload: this operation sends a full RGBA buffer back to the canvas. "
        "Use bytes-like inputs for lower Python overhead."
    ),
    "texture_cache_hit": "Image texture cache hit: the image version was already seen.",
    "texture_upload": (
        "Texture upload/cache miss: the image was new or mutated since the last draw. "
        "Reuse Image objects and avoid update_pixels() on images drawn every frame."
    ),
}


class SketchContext(PixelContextMixin, InputContextMixin, ThreeDContextMixin):
    """Mutable state and operations for one running sketch."""

    def __init__(self, sketch, backend, *, plugins: PluginRegistry) -> None:
        self.sketch = sketch
        self.backend = backend
        self.renderer = backend.renderer
        self.plugins = plugins
        self.state = SketchState()
        self.state.input.touch_supported = bool(backend.capabilities.touch)
        self.pixels: Sequence[int] = []
        self._camera3d = Camera3D()
        self._projection3d: PerspectiveProjection | OrthographicProjection = PerspectiveProjection()
        self._lights3d: list[Light3D] = []
        self._material3d: Material3D | None = None
        self._normal_material3d = False
        self._material3d_style_stack: list[tuple[Material3D | None, bool]] = []
        self._frame_mouse_dx = 0.0
        self._frame_mouse_dy = 0.0
        self._frame_scroll_x = 0.0
        self._frame_scroll_y = 0.0
        self._shader3d: Shader3D | None = None
        self._spline_tightness = 0.0
        self._text_direction = "ltr"
        self._text_wrap = "word"
        self._text_weight = 400
        self._accessibility_descriptions: list[dict[str, str]] = []
        self._performance_diagnostics_enabled = False
        self._performance_diagnostic_counts: dict[str, int] = {}
        self._performance_diagnostic_messages: list[str] = []
        self._performance_diagnostic_image_versions: dict[int, int] = {}

    @property
    def width(self) -> int:
        return self.state.canvas.width

    @property
    def height(self) -> int:
        return self.state.canvas.height

    @property
    def frame_count(self) -> int:
        return self.state.timing.frame_count

    @property
    def delta_time(self) -> float:
        return self.state.timing.delta_time

    @property
    def mouse_x(self) -> float:
        return self.state.input.mouse_x

    @property
    def mouse_y(self) -> float:
        return self.state.input.mouse_y

    def _mark_style_changed(self) -> None:
        self.state.style.mark_changed()

    def _set_transform_matrix(self, matrix: Matrix2D) -> None:
        self.state.transform.set_matrix(matrix)

    def create_canvas(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode = c.P2D,
        *,
        pixel_density: float | None = None,
    ) -> None:
        if renderer not in {c.P2D, c.WEBGL}:
            raise ArgumentValidationError(f"Unsupported renderer {renderer!r}.")
        if renderer == c.WEBGL and not self.backend.capabilities.three_d:
            raise BackendCapabilityError(
                f"Backend {self.backend.name!r} does not support renderer={c.WEBGL!r}."
            )
        self.backend.create_canvas(
            int(width),
            int(height),
            pixel_density,
            renderer=renderer,
        )
        self.renderer = self.backend.renderer
        self.state.canvas.renderer = renderer
        if renderer == c.WEBGL:
            self._reset_3d_state()
        self._sync_canvas_state()
        self.state.canvas.created = True

    def resize_canvas(self, width: int, height: int, *, pixel_density: float | None = None) -> None:
        density = self.state.canvas.pixel_density if pixel_density is None else pixel_density
        self.backend.resize_canvas(
            int(width),
            int(height),
            float(density),
            renderer=self.state.canvas.renderer,
        )
        self.renderer = self.backend.renderer
        self._sync_canvas_state()
        self.state.canvas.created = True

    def ensure_canvas(self) -> None:
        if not self.state.canvas.created:
            self.create_canvas(
                self.state.canvas.width,
                self.state.canvas.height,
                renderer=self.state.canvas.renderer,
            )

    def pixel_density(self, value: float | None = None) -> float:
        if value is None:
            return self.state.canvas.pixel_density
        if value <= 0:
            raise ArgumentValidationError("pixel_density() must be positive.")
        self.resize_canvas(self.state.canvas.width, self.state.canvas.height, pixel_density=value)
        return self.state.canvas.pixel_density

    def display_density(self) -> float:
        return self.backend.display_density()

    def fast(self) -> FastDrawScope:
        return FastDrawScope(self)

    def enable_performance_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        self._performance_diagnostics_enabled = bool(enabled)
        if reset:
            self.reset_performance_diagnostics()

    def reset_performance_diagnostics(self) -> None:
        self._performance_diagnostic_counts.clear()
        self._performance_diagnostic_messages.clear()
        self._performance_diagnostic_image_versions.clear()

    def performance_diagnostics(self) -> dict[str, object]:
        return {
            "enabled": self._performance_diagnostics_enabled,
            "counters": dict(self._performance_diagnostic_counts),
            "messages": list(self._performance_diagnostic_messages),
            "renderer": self.renderer_performance_counters(),
        }

    def renderer_performance_counters(self) -> dict[str, object]:
        callback = getattr(self.renderer, "performance_counters", None)
        if callable(callback):
            counters = callback()
            if isinstance(counters, dict):
                return counters
        return {}

    def reset_renderer_performance_counters(self) -> None:
        callback = getattr(self.renderer, "reset_performance_counters", None)
        if callable(callback):
            callback()

    def enable_frame_pacing_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        callback = getattr(self.backend, "enable_frame_pacing_diagnostics", None)
        if callable(callback):
            callback(enabled, reset=reset)

    def frame_pacing_diagnostics(self) -> dict[str, object]:
        callback = getattr(self.backend, "frame_pacing_diagnostics", None)
        if callable(callback):
            report = callback()
            if isinstance(report, dict):
                return report
        return {}

    def reset_frame_pacing_diagnostics(self) -> None:
        callback = getattr(self.backend, "reset_frame_pacing_diagnostics", None)
        if callable(callback):
            callback()

    def _record_performance_diagnostic(self, name: str) -> None:
        if not self._performance_diagnostics_enabled:
            return
        self._performance_diagnostic_counts[name] = (
            self._performance_diagnostic_counts.get(name, 0) + 1
        )
        message = _PERFORMANCE_DIAGNOSTIC_MESSAGES.get(name)
        if (
            message is not None
            and message not in self._performance_diagnostic_messages
            and len(self._performance_diagnostic_messages) < _PERFORMANCE_DIAGNOSTIC_MESSAGE_LIMIT
        ):
            self._performance_diagnostic_messages.append(message)

    def begin_frame(self) -> None:
        if self.state.canvas.renderer == c.WEBGL:
            self._lights3d = []

    def end_frame(self) -> None:
        self._frame_mouse_dx = 0.0
        self._frame_mouse_dy = 0.0
        self._frame_scroll_x = 0.0
        self._frame_scroll_y = 0.0

    def _sync_canvas_state(self) -> None:
        self.state.canvas.width = self.renderer.width
        self.state.canvas.height = self.renderer.height
        self.state.canvas.physical_width = self.renderer.physical_width
        self.state.canvas.physical_height = self.renderer.physical_height
        self.state.canvas.pixel_density = self.renderer.pixel_density

    def color(self, *args: object) -> Color:
        return Color.from_args(
            args,
            mode=self.state.color_mode.mode,
            ranges=self.state.color_mode.ranges,
        )

    def color_mode(
        self,
        mode: c.ColorMode,
        max1: float | None = None,
        max2: float | None = None,
        max3: float | None = None,
        max_alpha: float | None = None,
    ) -> None:
        if mode not in {c.RGB, c.HSB, c.HSL}:
            raise ArgumentValidationError(f"Unsupported color mode {mode!r}.")
        if max1 is None:
            ranges = (255.0, 255.0, 255.0, 255.0) if mode == c.RGB else (360.0, 100.0, 100.0, 1.0)
        else:
            ranges = (
                float(max1),
                float(max1 if max2 is None else max2),
                float(max1 if max3 is None else max3),
                float(max1 if max_alpha is None else max_alpha),
            )
        self.state.color_mode.mode = mode
        self.state.color_mode.ranges = ranges

    def lerp_color(self, start: Color, stop: Color, amount: float) -> Color:
        return lerp_color(start, stop, amount)

    def background(self, *args: object) -> None:
        self.renderer.background(self.color(*args))

    def clear(self) -> None:
        self.renderer.clear()

    def fill(self, *args: object) -> None:
        self.state.style.fill_color = self.color(*args)
        self._mark_style_changed()

    def no_fill(self) -> None:
        self.state.style.fill_color = None
        self._mark_style_changed()

    def stroke(self, *args: object) -> None:
        self.state.style.stroke_color = self.color(*args)
        self._mark_style_changed()

    def no_stroke(self) -> None:
        self.state.style.stroke_color = None
        self._mark_style_changed()

    def stroke_weight(self, weight: float) -> None:
        if weight < 0:
            raise ArgumentValidationError("stroke_weight() cannot be negative.")
        self.state.style.stroke_weight = float(weight)
        self._mark_style_changed()

    def stroke_cap(self, cap: c.StrokeCap) -> None:
        if cap not in {c.ROUND, c.SQUARE, c.PROJECT}:
            raise ArgumentValidationError(f"Unsupported stroke cap {cap!r}.")
        self.state.style.stroke_cap = cap
        self._mark_style_changed()

    def stroke_join(self, join: c.StrokeJoin) -> None:
        if join not in {c.MITER, c.BEVEL, c.ROUND}:
            raise ArgumentValidationError(f"Unsupported stroke join {join!r}.")
        self.state.style.stroke_join = join
        self._mark_style_changed()

    def rect_mode(self, mode: c.ShapeMode) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported rect mode {mode!r}.")
        self.state.style.rect_mode = mode
        self._mark_style_changed()

    def ellipse_mode(self, mode: c.ShapeMode) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported ellipse mode {mode!r}.")
        self.state.style.ellipse_mode = mode
        self._mark_style_changed()

    def image_mode(self, mode: c.ShapeMode) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER}:
            raise ArgumentValidationError(f"Unsupported image mode {mode!r}.")
        self.state.style.image_mode = mode
        self._mark_style_changed()

    def image_sampling(self, mode: c.ImageSampling | None = None) -> c.ImageSampling:
        if mode is not None:
            if mode not in {c.LINEAR, c.NEAREST}:
                raise ArgumentValidationError(f"Unsupported image sampling mode {mode!r}.")
            self.state.style.image_sampling = mode
            self._mark_style_changed()
        return self.state.style.image_sampling

    def smooth(self) -> None:
        self.state.style.image_sampling = c.LINEAR
        self._mark_style_changed()

    def no_smooth(self) -> None:
        self.state.style.image_sampling = c.NEAREST
        self._mark_style_changed()

    def point(self, x: float, y: float) -> None:
        self.renderer.point(float(x), float(y), self.state.style, self.state.transform.matrix)

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.renderer.line(
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            self.state.style,
            self.state.transform.matrix,
        )

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None:
        h = width if height is None else height
        rx, ry, rw, rh = resolve_rect(
            self.state.style.rect_mode,
            float(x),
            float(y),
            float(width),
            float(h),
        )
        self.renderer.rect(rx, ry, rw, rh, self.state.style, self.state.transform.matrix)

    def square(self, x: float, y: float, size: float) -> None:
        self.rect(x, y, size, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        h = width if height is None else height
        ex, ey, ew, eh = resolve_ellipse(
            self.state.style.ellipse_mode,
            float(x),
            float(y),
            float(width),
            float(h),
        )
        self.renderer.ellipse(ex, ey, ew, eh, self.state.style, self.state.transform.matrix)

    def circle(self, x: float, y: float, diameter: float) -> None:
        self.ellipse(x, y, diameter, diameter)

    def triangle(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        self.renderer.triangle(
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            float(x3),
            float(y3),
            self.state.style,
            self.state.transform.matrix,
        )

    def quad(self, *coords: float) -> None:
        if len(coords) != 8:
            raise ArgumentValidationError("quad() requires eight coordinate values.")
        self.renderer.quad(
            float(coords[0]),
            float(coords[1]),
            float(coords[2]),
            float(coords[3]),
            float(coords[4]),
            float(coords[5]),
            float(coords[6]),
            float(coords[7]),
            self.state.style,
            self.state.transform.matrix,
        )

    def arc(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        start: float,
        stop: float,
        mode: c.ArcMode = c.OPEN,
    ) -> None:
        ex, ey, ew, eh = resolve_ellipse(
            self.state.style.ellipse_mode,
            float(x),
            float(y),
            float(width),
            float(height),
        )
        self.renderer.arc(
            ex,
            ey,
            ew,
            eh,
            self._angle(start),
            self._angle(stop),
            mode,
            self.state.style,
            self.state.transform.matrix,
        )

    def begin_shape(self, kind: c.ShapeKind | None = None) -> None:
        self.state.shape.active = True
        self.state.shape.vertices.clear()
        self.state.shape.kind = kind

    def vertex(self, x: float, y: float) -> None:
        if not self.state.shape.active:
            raise ArgumentValidationError(
                "vertex() must be called between begin_shape() and end_shape()."
            )
        self.state.shape.vertices.append((float(x), float(y)))

    def bezier_vertex(
        self,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        x4: float,
        y4: float,
    ) -> None:
        if not self.state.shape.vertices:
            raise ArgumentValidationError("bezier_vertex() requires an initial vertex().")
        p0 = self.state.shape.vertices[-1]
        self.state.shape.vertices.extend(flatten_cubic(p0, (x2, y2), (x3, y3), (x4, y4)))

    def quadratic_vertex(self, cx: float, cy: float, x3: float, y3: float) -> None:
        if not self.state.shape.vertices:
            raise ArgumentValidationError("quadratic_vertex() requires an initial vertex().")
        p0 = self.state.shape.vertices[-1]
        self.state.shape.vertices.extend(flatten_quadratic(p0, (cx, cy), (x3, y3)))

    def spline_vertex(self, x: float, y: float) -> None:
        if not self.state.shape.active:
            raise ArgumentValidationError(
                "spline_vertex() must be called between begin_shape() and end_shape()."
            )
        vertices = self.state.shape.vertices
        point = (float(x), float(y))
        if not vertices:
            vertices.append(point)
            return
        if len(vertices) == 1:
            vertices.append(point)
            return
        p0 = vertices[-2]
        p1 = vertices[-1]
        p2 = point
        p3 = point
        vertices.extend(flatten_spline(p0, p1, p2, p3, tightness=self._spline_tightness))

    def spline(self, *coords: float) -> None:
        if len(coords) != 8:
            raise ArgumentValidationError("spline() requires eight coordinate values.")
        p0 = (float(coords[0]), float(coords[1]))
        p1 = (float(coords[2]), float(coords[3]))
        p2 = (float(coords[4]), float(coords[5]))
        p3 = (float(coords[6]), float(coords[7]))
        previous_fill = self.state.style.fill_color
        self.state.style.fill_color = None
        self._mark_style_changed()
        self.renderer.polygon(
            [p1, *flatten_spline(p0, p1, p2, p3, tightness=self._spline_tightness)],
            self.state.style,
            self.state.transform.matrix,
            close=False,
        )
        self.state.style.fill_color = previous_fill
        self._mark_style_changed()

    def spline_point(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return geometry_spline_point(
            float(a), float(b), float(cc), float(d), float(t), self._spline_tightness
        )

    def spline_tangent(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return geometry_spline_tangent(
            float(a), float(b), float(cc), float(d), float(t), self._spline_tightness
        )

    def spline_property(self, name: str, value: float | None = None) -> float:
        if name != "tightness":
            raise ArgumentValidationError("Only spline_property('tightness') is supported.")
        if value is not None:
            self._spline_tightness = float(value)
        return self._spline_tightness

    def spline_properties(self, **properties: float) -> dict[str, float]:
        for name, value in properties.items():
            self.spline_property(name, value)
        return {"tightness": self._spline_tightness}

    def end_shape(self, mode: c.ArcMode = c.OPEN) -> None:
        if not self.state.shape.active:
            raise ArgumentValidationError("end_shape() requires begin_shape().")
        close = mode == c.CLOSE
        self.renderer.polygon(
            list(self.state.shape.vertices),
            self.state.style,
            self.state.transform.matrix,
            close=close,
        )
        self.state.shape.active = False
        self.state.shape.vertices.clear()
        self.state.shape.kind = None

    def bezier(self, *coords: float) -> None:
        if len(coords) != 8:
            raise ArgumentValidationError("bezier() requires eight coordinate values.")
        p0 = (float(coords[0]), float(coords[1]))
        p1 = (float(coords[2]), float(coords[3]))
        p2 = (float(coords[4]), float(coords[5]))
        p3 = (float(coords[6]), float(coords[7]))
        previous_fill = self.state.style.fill_color
        self.state.style.fill_color = None
        self._mark_style_changed()
        self.renderer.polygon(
            [p0, *flatten_cubic(p0, p1, p2, p3)],
            self.state.style,
            self.state.transform.matrix,
            close=False,
        )
        self.state.style.fill_color = previous_fill
        self._mark_style_changed()

    def push(self) -> None:
        self.state.stack.append(
            StateStackEntry(self.state.style.copy(), self.state.transform.matrix)
        )
        self._material3d_style_stack.append((self._material3d, self._normal_material3d))

    def pop(self) -> None:
        if not self.state.stack:
            raise ArgumentValidationError("pop() called without matching push().")
        entry = self.state.stack.pop()
        self.state.style = entry.style
        self.state.transform.set_matrix(entry.matrix)
        self._material3d, self._normal_material3d = self._material3d_style_stack.pop()

    def translate(self, x: float, y: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.translation(float(x), float(y)))
        )

    def rotate(self, angle: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.rotation(self._angle(angle)))
        )

    def scale(self, x: float, y: float | None = None) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(
                Matrix2D.scaling(float(x), None if y is None else float(y))
            )
        )

    def shear_x(self, angle: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.shear_x(self._angle(angle)))
        )

    def shear_y(self, angle: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.shear_y(self._angle(angle)))
        )

    def apply_matrix(self, a: float, b: float, cc: float, d: float, e: float, f: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D(a, b, cc, d, e, f))
        )

    def reset_matrix(self) -> None:
        self._set_transform_matrix(Matrix2D.identity())

    def angle_mode(self, mode: c.AngleMode) -> None:
        if mode not in {c.RADIANS, c.DEGREES}:
            raise ArgumentValidationError(f"Unsupported angle mode {mode!r}.")
        self.angle_mode_value = mode
        gs_math.set_angle_mode(mode)

    def frame_rate(self, value: float | None = None) -> float:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("frame_rate() must be positive.")
            self.state.timing.target_frame_rate = float(value)
        return self.state.timing.target_frame_rate

    def millis(self) -> float:
        return self.state.timing.millis()

    def no_loop(self) -> None:
        self.state.looping = False

    def loop(self) -> None:
        self.state.looping = True

    def redraw(self) -> None:
        self.state.redraw_requested = True

    def is_looping(self) -> bool:
        return self.state.looping

    def image(self, image: Image | CanvasImage, x: float, y: float, *args: float) -> None:
        self._draw_image_fast(image, x, y, *args)

    def _draw_image_fast(
        self, image: Image | CanvasImage, x: float, y: float, *args: float
    ) -> None:
        draw_args = image_draw_args(
            image,
            x,
            y,
            args,
            image_mode=self.state.style.image_mode,
        )
        self._record_image_diagnostics(image)
        self.renderer.draw_image(
            image,
            draw_args.dx,
            draw_args.dy,
            draw_args.dw,
            draw_args.dh,
            self.state.style,
            self.state.transform.matrix,
            source=draw_args.source,
        )

    def _record_image_diagnostics(self, image: Image | CanvasImage) -> None:
        if not self._performance_diagnostics_enabled or not isinstance(image, Image):
            return
        cached_version = self._performance_diagnostic_image_versions.get(image.cache_key)
        if cached_version == image.version:
            self._record_performance_diagnostic("texture_cache_hit")
        else:
            self._record_performance_diagnostic("texture_upload")
            self._performance_diagnostic_image_versions[image.cache_key] = image.version

    def text(self, value: object, x: float, y: float) -> None:
        self.renderer.text(
            str(value), float(x), float(y), self.state.style, self.state.transform.matrix
        )

    def text_size(self, size: float | None = None) -> float:
        if size is not None:
            if size <= 0:
                raise ArgumentValidationError("text_size() must be positive.")
            self.state.style.text_size = float(size)
            self._mark_style_changed()
        return self.state.style.text_size

    def text_font(self, font: Font | str | None = None) -> Font:
        if font is not None:
            if isinstance(font, str):
                font = Font(name=font)
            self.state.style.text_font = font
            self._mark_style_changed()
        return self.state.style.text_font

    def text_style(self, style: c.TextStyle | None = None) -> c.TextStyle:
        if style is not None:
            if style not in {c.NORMAL, c.ITALIC, c.BOLD, c.BOLDITALIC}:
                raise ArgumentValidationError(f"Unsupported text style {style!r}.")
            self.state.style.text_style = style
            self._mark_style_changed()
        return self.state.style.text_style

    def text_align(self, horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
        if horizontal not in {c.LEFT, c.CENTER, c.RIGHT}:
            raise ArgumentValidationError(f"Unsupported horizontal text alignment {horizontal!r}.")
        if vertical is not None and vertical not in {c.TOP, c.CENTER, c.BOTTOM, c.BASELINE}:
            raise ArgumentValidationError(f"Unsupported vertical text alignment {vertical!r}.")
        self.state.style.text_align_x = horizontal
        self._mark_style_changed()
        if vertical is not None:
            self.state.style.text_align_y = vertical
            self._mark_style_changed()

    def text_leading(self, value: float | None = None) -> float:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("text_leading() must be positive.")
            self.state.style.text_leading = float(value)
            self._mark_style_changed()
        return self.state.style.text_leading

    def text_width(self, value: object) -> float:
        return self.renderer.text_width(str(value), self.state.style)

    def text_ascent(self) -> float:
        return self.renderer.text_ascent(self.state.style)

    def text_descent(self) -> float:
        return self.renderer.text_descent(self.state.style)

    def font_ascent(self, font: Font | str | None = None) -> float:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        value = self.text_ascent()
        self.state.style.text_font = previous
        self._mark_style_changed()
        return value

    def font_descent(self, font: Font | str | None = None) -> float:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        value = self.text_descent()
        self.state.style.text_font = previous
        self._mark_style_changed()
        return value

    def font_width(self, value: object, font: Font | str | None = None) -> float:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        width = self.text_width(value)
        self.state.style.text_font = previous
        self._mark_style_changed()
        return width

    def text_bounds(self, value: object, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
        width = self.text_width(value)
        ascent = self.text_ascent()
        descent = self.text_descent()
        return {
            "x": float(x),
            "y": float(y) - ascent,
            "width": width,
            "height": ascent + descent,
        }

    def font_bounds(
        self, value: object, x: float = 0.0, y: float = 0.0, font: Font | str | None = None
    ) -> dict[str, float]:
        previous = self.state.style.text_font
        if font is not None:
            self.text_font(font)
        bounds = self.text_bounds(value, x, y)
        self.state.style.text_font = previous
        self._mark_style_changed()
        return bounds

    def text_direction(self, value: str | None = None) -> str:
        if value is not None:
            if value not in {"ltr", "rtl"}:
                raise ArgumentValidationError("text_direction() supports 'ltr' and 'rtl'.")
            self._text_direction = value
        return self._text_direction

    def text_wrap(self, value: str | None = None) -> str:
        if value is not None:
            if value not in {"word", "char"}:
                raise ArgumentValidationError("text_wrap() supports 'word' and 'char'.")
            self._text_wrap = value
        return self._text_wrap

    def text_weight(self, value: int | None = None) -> int:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("text_weight() must be positive.")
            self._text_weight = int(value)
            if self._text_weight >= 600 and self.state.style.text_style == c.NORMAL:
                self.state.style.text_style = c.BOLD
                self._mark_style_changed()
        return self._text_weight

    def text_property(self, name: str, value: object | None = None) -> object:
        if name == "direction":
            return self.text_direction(None if value is None else str(value))
        if name == "wrap":
            return self.text_wrap(None if value is None else str(value))
        if name == "weight":
            return self.text_weight(None if value is None else int(cast(Any, value)))
        raise ArgumentValidationError("Unsupported text property.")

    def text_properties(self, **properties: object) -> dict[str, object]:
        for name, value in properties.items():
            self.text_property(name, value)
        return {
            "direction": self._text_direction,
            "wrap": self._text_wrap,
            "weight": self._text_weight,
            "size": self.state.style.text_size,
            "style": self.state.style.text_style,
            "leading": self.state.style.text_leading,
        }

    def describe(self, description: object, *, label: str = "canvas") -> dict[str, str]:
        entry = {"label": str(label), "description": str(description)}
        self._accessibility_descriptions.append(entry)
        return entry

    def describe_element(self, name: object, description: object) -> dict[str, str]:
        return self.describe(description, label=str(name))

    def text_output(self) -> list[dict[str, str]]:
        return list(self._accessibility_descriptions)

    def grid_output(self) -> list[dict[str, str]]:
        return self.text_output()

    def _require_webgl_mode(self, api_name: str) -> None:
        if self.state.canvas.renderer != c.WEBGL:
            raise BackendCapabilityError(
                f"{api_name}() requires create_canvas(..., renderer={c.WEBGL!r})."
            )

    def _reset_3d_state(self) -> None:
        self._camera3d = Camera3D()
        self._projection3d = PerspectiveProjection()
        self._lights3d = []
        self._material3d = None
        self._normal_material3d = False
        self._material3d_style_stack = []
        self._frame_mouse_dx = 0.0
        self._frame_mouse_dy = 0.0
        self._frame_scroll_x = 0.0
        self._frame_scroll_y = 0.0
        self._shader3d = None

    def _effective_3d_material(self) -> Material3D:
        if self._material3d is not None:
            return self._material3d
        fill = self.state.style.fill_color or Color(255, 255, 255, 255)
        return Material3D(base_color=self._color_to_rgba(fill))

    def _replace_material(
        self,
        *,
        base_color: tuple[float, float, float, float] | None = None,
        specular_color: tuple[float, float, float, float] | None = None,
        shininess: float | None = None,
        texture: Texture3D | None | object = _MATERIAL_UNSET,
    ) -> Material3D:
        current = self._effective_3d_material()
        return Material3D(
            base_color=current.base_color if base_color is None else base_color,
            emissive_color=current.emissive_color,
            specular_color=current.specular_color if specular_color is None else specular_color,
            shininess=current.shininess if shininess is None else shininess,
            texture=(
                current.texture if texture is _MATERIAL_UNSET else cast(Texture3D | None, texture)
            ),
        )

    def _split_color_args(
        self,
        args: Sequence[object],
        *,
        tail_count: int,
    ) -> tuple[Color, tuple[float, ...]]:
        for color_count in (4, 3, 2, 1):
            if len(args) != color_count + tail_count:
                continue
            color = self.color(*args[:color_count])
            tail = args[color_count:]
            if all(isinstance(value, int | float) for value in tail):
                numeric_tail = self._numeric_values(tail)
                return color, numeric_tail
        raise ArgumentValidationError(
            "Light APIs require one to four color values followed by the expected coordinates."
        )

    def _numeric_values(self, values: Sequence[object]) -> tuple[float, ...]:
        numeric: list[float] = []
        for value in values:
            if not isinstance(value, int | float):
                raise ArgumentValidationError("Expected numeric values.")
            numeric.append(float(value))
        return tuple(numeric)

    def _color_to_rgba(self, color: Color) -> tuple[float, float, float, float]:
        return (
            color.r / 255.0,
            color.g / 255.0,
            color.b / 255.0,
            color.a / 255.0,
        )

    def _rgba_float_to_color(self, rgba: tuple[float, float, float, float]) -> Color:
        return Color(*(int(round(max(0.0, min(1.0, channel)) * 255.0)) for channel in rgba))

    def _angle(self, value: float) -> float:
        mode = getattr(self, "angle_mode_value", c.RADIANS)
        return math.radians(value) if mode == c.DEGREES else float(value)
