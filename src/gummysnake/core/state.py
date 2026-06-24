"""Sketch state dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gummysnake import constants as c
from gummysnake.assets.text import DEFAULT_FONT, Font
from gummysnake.core.color import Color
from gummysnake.core.transform import Matrix2D
from gummysnake.events.input_state import TouchPoint
from gummysnake.rust.canvas import require_canvas_runtime


class CanvasState:
    """Compatibility facade for Rust-owned canvas lifecycle state."""

    __slots__ = ("_rust",)

    def __init__(self, rust_state: Any) -> None:
        self._rust = rust_state

    @property
    def width(self) -> int:
        return int(self._rust.width)

    @width.setter
    def width(self, value: int) -> None:
        self._rust.width = int(value)

    @property
    def height(self) -> int:
        return int(self._rust.height)

    @height.setter
    def height(self, value: int) -> None:
        self._rust.height = int(value)

    @property
    def physical_width(self) -> int:
        return int(self._rust.physical_width)

    @physical_width.setter
    def physical_width(self, value: int) -> None:
        self._rust.physical_width = int(value)

    @property
    def physical_height(self) -> int:
        return int(self._rust.physical_height)

    @physical_height.setter
    def physical_height(self, value: int) -> None:
        self._rust.physical_height = int(value)

    @property
    def pixel_density(self) -> float:
        return float(self._rust.pixel_density)

    @pixel_density.setter
    def pixel_density(self, value: float) -> None:
        self._rust.pixel_density = float(value)

    @property
    def renderer(self) -> c.RendererMode:
        return c.RendererMode(str(self._rust.renderer))

    @renderer.setter
    def renderer(self, value: c.RendererMode | str) -> None:
        self._rust.renderer = c.RendererMode(str(value)).value

    @property
    def created(self) -> bool:
        return bool(self._rust.created)

    @created.setter
    def created(self, value: bool) -> None:
        self._rust.created = bool(value)


@dataclass(slots=True)
class ColorModeState:
    mode: c.ColorMode = c.RGB
    ranges: tuple[float, float, float, float] = (255.0, 255.0, 255.0, 255.0)


@dataclass(slots=True)
class StyleState:
    fill_color: Color | None = field(default_factory=lambda: Color(255, 255, 255, 255))
    stroke_color: Color | None = field(default_factory=lambda: Color(0, 0, 0, 255))
    stroke_weight: float = 1.0
    stroke_cap: c.StrokeCap = c.ROUND
    stroke_join: c.StrokeJoin = c.MITER
    rect_mode: c.ShapeMode = c.CORNER
    ellipse_mode: c.ShapeMode = c.CENTER
    image_mode: c.ShapeMode = c.CORNER
    image_sampling: c.ImageSampling = c.LINEAR
    image_tint: Color | None = None
    blend_mode: c.BlendMode = c.BLEND
    erasing: bool = False
    text_font: Font = field(default_factory=lambda: DEFAULT_FONT)
    text_size: float = 12.0
    text_style: c.TextStyle = c.NORMAL
    text_align_x: c.TextAlign = c.LEFT
    text_align_y: c.TextAlign = c.BASELINE
    text_leading: float = 14.0
    revision: int = 0

    def copy(self) -> StyleState:
        return StyleState(
            fill_color=self.fill_color,
            stroke_color=self.stroke_color,
            stroke_weight=self.stroke_weight,
            stroke_cap=self.stroke_cap,
            stroke_join=self.stroke_join,
            rect_mode=self.rect_mode,
            ellipse_mode=self.ellipse_mode,
            image_mode=self.image_mode,
            image_sampling=self.image_sampling,
            image_tint=self.image_tint,
            blend_mode=self.blend_mode,
            erasing=self.erasing,
            text_font=self.text_font,
            text_size=self.text_size,
            text_style=self.text_style,
            text_align_x=self.text_align_x,
            text_align_y=self.text_align_y,
            text_leading=self.text_leading,
            revision=self.revision,
        )

    def mark_changed(self) -> None:
        self.revision += 1


@dataclass(slots=True)
class TransformState:
    matrix: Matrix2D = field(default_factory=Matrix2D.identity)
    revision: int = 0

    def set_matrix(self, matrix: Matrix2D) -> None:
        self.matrix = matrix
        self.revision += 1


class ShapeState:
    """Compatibility facade for Rust-owned begin_shape capture buffers."""

    __slots__ = ("_rust",)

    def __init__(self, rust_state: Any) -> None:
        self._rust = rust_state

    @property
    def active(self) -> bool:
        return bool(self._rust.shape_active)

    @active.setter
    def active(self, value: bool) -> None:
        if not value:
            self._rust.reset_shape_capture()

    @property
    def vertices(self) -> list[tuple[float, float]]:
        return [tuple(point) for point in self._rust.shape_vertices()]

    @property
    def contours(self) -> list[list[tuple[float, float]]]:
        return [[tuple(point) for point in contour] for contour in self._rust.shape_contours()]

    @property
    def contour_active(self) -> bool:
        return bool(self._rust.contour_active)

    @contour_active.setter
    def contour_active(self, value: bool) -> None:
        if not value:
            self._rust.reset_contour_capture()

    @property
    def contour_vertices(self) -> list[tuple[float, float]]:
        if not self.contour_active:
            return []
        return [tuple(point) for point in self._rust.active_vertices()]

    @property
    def kind(self) -> c.ShapeKind | None:
        value = self._rust.shape_kind
        return None if value is None else c.ShapeKind(value)


class TimingState:
    """Compatibility facade for Rust-owned timing and frame counters."""

    __slots__ = ("_rust",)

    def __init__(self, rust_state: Any) -> None:
        self._rust = rust_state

    @property
    def delta_time(self) -> float:
        return float(self._rust.delta_time)

    @property
    def frame_count(self) -> int:
        return int(self._rust.frame_count)

    @frame_count.setter
    def frame_count(self, value: int) -> None:
        self._rust.frame_count = int(value)

    @property
    def target_frame_rate(self) -> float:
        return float(self._rust.target_frame_rate)

    @target_frame_rate.setter
    def target_frame_rate(self, value: float) -> None:
        self._rust.target_frame_rate = float(value)

    def begin_frame(self) -> None:
        self._rust.begin_frame_timing()

    def millis(self) -> float:
        return float(self._rust.millis())


class InputState:
    """Compatibility facade for Rust-owned input snapshots."""

    __slots__ = ("_rust",)

    def __init__(self, rust_state: Any) -> None:
        self._rust = rust_state

    @property
    def mouse_x(self) -> float:
        return float(self._rust.mouse_x)

    @property
    def mouse_y(self) -> float:
        return float(self._rust.mouse_y)

    @property
    def previous_mouse_x(self) -> float:
        return float(self._rust.previous_mouse_x)

    @previous_mouse_x.setter
    def previous_mouse_x(self, value: float) -> None:
        self._rust.previous_mouse_x = float(value)

    @property
    def previous_mouse_y(self) -> float:
        return float(self._rust.previous_mouse_y)

    @previous_mouse_y.setter
    def previous_mouse_y(self, value: float) -> None:
        self._rust.previous_mouse_y = float(value)

    @property
    def moved_x(self) -> float:
        return float(self._rust.moved_x)

    @property
    def moved_y(self) -> float:
        return float(self._rust.moved_y)

    @property
    def mouse_is_pressed(self) -> bool:
        return bool(self._rust.mouse_is_pressed)

    @mouse_is_pressed.setter
    def mouse_is_pressed(self, value: bool) -> None:
        self._rust.mouse_is_pressed = bool(value)

    @property
    def mouse_inside_window(self) -> bool:
        return bool(self._rust.mouse_inside_window)

    @mouse_inside_window.setter
    def mouse_inside_window(self, value: bool) -> None:
        self._rust.mouse_inside_window = bool(value)

    @property
    def mouse_button(self) -> str | None:
        return self._rust.mouse_button

    @mouse_button.setter
    def mouse_button(self, value: str | None) -> None:
        self._rust.mouse_button = value

    @property
    def key(self) -> str | None:
        return self._rust.key

    @key.setter
    def key(self, value: str | None) -> None:
        self._rust.key = value

    @property
    def key_code(self) -> int | None:
        value = self._rust.key_code
        return None if value is None else int(value)

    @key_code.setter
    def key_code(self, value: int | None) -> None:
        self._rust.key_code = None if value is None else int(value)

    @property
    def code(self) -> str | None:
        return self._rust.code

    @code.setter
    def code(self, value: str | None) -> None:
        self._rust.code = value

    @property
    def text(self) -> str | None:
        return self._rust.text

    @text.setter
    def text(self, value: str | None) -> None:
        self._rust.text = value

    @property
    def text_input_active(self) -> bool:
        return bool(self._rust.text_input_active)

    @text_input_active.setter
    def text_input_active(self, value: bool) -> None:
        self._rust.text_input_active = bool(value)

    @property
    def key_is_pressed(self) -> bool:
        return bool(self._rust.key_is_pressed)

    @key_is_pressed.setter
    def key_is_pressed(self, value: bool) -> None:
        self._rust.key_is_pressed = bool(value)

    @property
    def touches(self) -> list[TouchPoint]:
        return [TouchPoint(**dict(payload)) for payload in self._rust.touch_payload()]

    @touches.setter
    def touches(self, value: list[TouchPoint]) -> None:
        self._rust.update_touches(value)

    @property
    def touch_supported(self) -> bool:
        return bool(self._rust.touch_supported)

    @touch_supported.setter
    def touch_supported(self, value: bool) -> None:
        self._rust.touch_supported = bool(value)

    @property
    def pointer_locked(self) -> bool:
        return bool(self._rust.pointer_locked)

    @pointer_locked.setter
    def pointer_locked(self, value: bool) -> None:
        self._rust.pointer_locked = bool(value)

    @property
    def pointer_lock_mode(self) -> c.PointerLockMode:
        return c.PointerLockMode(str(self._rust.pointer_lock_mode))

    @pointer_lock_mode.setter
    def pointer_lock_mode(self, value: c.PointerLockMode | str) -> None:
        self._rust.pointer_lock_mode = c.PointerLockMode(str(value)).value

    @property
    def pressed_keys(self) -> InputState:
        return self

    @property
    def pressed_codes(self) -> InputState:
        return self

    def add(self, value: int | str) -> None:
        if isinstance(value, int):
            self._rust.set_key_down(value, True)
        else:
            self._rust.set_code_down(value, True)

    def discard(self, value: int | str) -> None:
        if isinstance(value, int):
            self._rust.set_key_down(value, False)
        else:
            self._rust.set_code_down(value, False)

    def update_mouse(
        self, x: float, y: float, *, dx: float | None = None, dy: float | None = None
    ) -> None:
        self._rust.update_mouse(float(x), float(y), dx, dy)

    def update_touches(self, touches: list[TouchPoint]) -> None:
        self._rust.update_touches(touches)

    def require_touch_supported(self) -> None:
        if not self.touch_supported:
            from gummysnake.exceptions import BackendCapabilityError

            raise BackendCapabilityError(
                "Touch input is not supported by the active backend yet. "
                "The touch API is present so capable future backends can provide "
                f"{c.TOUCH_STARTED}, {c.TOUCH_MOVED}, and {c.TOUCH_ENDED} events."
            )

    def key_is_down(self, key_code: int) -> bool:
        return bool(self._rust.key_is_down(int(key_code)))

    def code_is_down(self, code: str) -> bool:
        return bool(self._rust.code_is_down(code))


@dataclass(slots=True)
class StateStackEntry:
    style: StyleState
    matrix: Matrix2D
    clip_depth: int


class SketchState:
    """Python facade over Rust-owned sketch runtime state."""

    __slots__ = (
        "_rust",
        "canvas",
        "color_mode",
        "style",
        "transform",
        "shape",
        "timing",
        "input",
        "stack",
    )

    def __init__(self) -> None:
        self._rust = require_canvas_runtime().SketchContextState()
        self.canvas = CanvasState(self._rust)
        self.color_mode = ColorModeState()
        self.style = StyleState()
        self.transform = TransformState()
        self.shape = ShapeState(self._rust)
        self.timing = TimingState(self._rust)
        self.input = InputState(self._rust)
        self.stack: list[StateStackEntry] = []

    @property
    def looping(self) -> bool:
        return bool(self._rust.looping)

    @looping.setter
    def looping(self, value: bool) -> None:
        self._rust.looping = bool(value)

    @property
    def redraw_requested(self) -> bool:
        return bool(self._rust.redraw_requested)

    @redraw_requested.setter
    def redraw_requested(self, value: bool) -> None:
        self._rust.redraw_requested = bool(value)

    @property
    def rust(self) -> Any:
        return self._rust
