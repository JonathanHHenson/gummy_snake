"""Sketch context containing mutable runtime state."""

from __future__ import annotations

import math
from pathlib import Path

from p5_py import constants as c
from p5_py.core.color import Color, lerp_color
from p5_py.core.geometry import (
    flatten_cubic,
    flatten_quadratic,
    resolve_ellipse,
    resolve_rect,
)
from p5_py.core.state import SketchState, StateStackEntry
from p5_py.core.transform import Matrix2D
from p5_py.events.input_state import KeyboardEvent, MouseEvent
from p5_py.exceptions import ArgumentValidationError


class SketchContext:
    """Mutable state and operations for one running sketch."""

    def __init__(self, sketch, backend) -> None:
        self.sketch = sketch
        self.backend = backend
        self.renderer = backend.renderer
        self.state = SketchState()

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

    def create_canvas(self, width: int, height: int, *, pixel_density: float = 1.0) -> None:
        self.state.canvas.width = int(width)
        self.state.canvas.height = int(height)
        self.state.canvas.pixel_density = float(pixel_density)
        self.state.canvas.created = True
        self.backend.create_canvas(int(width), int(height), float(pixel_density))
        self.renderer = self.backend.renderer

    def resize_canvas(self, width: int, height: int, *, pixel_density: float | None = None) -> None:
        density = self.state.canvas.pixel_density if pixel_density is None else pixel_density
        self.state.canvas.width = int(width)
        self.state.canvas.height = int(height)
        self.state.canvas.pixel_density = float(density)
        self.state.canvas.created = True
        self.backend.resize_canvas(int(width), int(height), float(density))
        self.renderer = self.backend.renderer

    def ensure_canvas(self) -> None:
        if not self.state.canvas.created:
            self.create_canvas(self.state.canvas.width, self.state.canvas.height)

    def color(self, *args: object) -> Color:
        return Color.from_args(
            args,
            mode=self.state.color_mode.mode,
            ranges=self.state.color_mode.ranges,
        )

    def color_mode(
        self,
        mode: str,
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

    def no_fill(self) -> None:
        self.state.style.fill_color = None

    def stroke(self, *args: object) -> None:
        self.state.style.stroke_color = self.color(*args)

    def no_stroke(self) -> None:
        self.state.style.stroke_color = None

    def stroke_weight(self, weight: float) -> None:
        if weight < 0:
            raise ArgumentValidationError("stroke_weight() cannot be negative.")
        self.state.style.stroke_weight = float(weight)

    def rect_mode(self, mode: str) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported rect mode {mode!r}.")
        self.state.style.rect_mode = mode

    def ellipse_mode(self, mode: str) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported ellipse mode {mode!r}.")
        self.state.style.ellipse_mode = mode

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
        self.renderer.polygon(
            [(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)],
            self.state.style,
            self.state.transform.matrix,
            close=True,
        )

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
        self.renderer.polygon(
            [(float(x1), float(y1)), (float(x2), float(y2)), (float(x3), float(y3))],
            self.state.style,
            self.state.transform.matrix,
            close=True,
        )

    def quad(self, *coords: float) -> None:
        if len(coords) != 8:
            raise ArgumentValidationError("quad() requires eight coordinate values.")
        points = [(float(coords[i]), float(coords[i + 1])) for i in range(0, 8, 2)]
        self.renderer.polygon(points, self.state.style, self.state.transform.matrix, close=True)

    def arc(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        start: float,
        stop: float,
        mode: str = c.OPEN,
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

    def begin_shape(self, kind: str | None = None) -> None:
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

    def end_shape(self, mode: str = c.OPEN) -> None:
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
        self.renderer.polygon(
            [p0, *flatten_cubic(p0, p1, p2, p3)],
            self.state.style,
            self.state.transform.matrix,
            close=False,
        )
        self.state.style.fill_color = previous_fill

    def push(self) -> None:
        self.state.stack.append(
            StateStackEntry(self.state.style.copy(), self.state.transform.matrix)
        )

    def pop(self) -> None:
        if not self.state.stack:
            raise ArgumentValidationError("pop() called without matching push().")
        entry = self.state.stack.pop()
        self.state.style = entry.style
        self.state.transform.matrix = entry.matrix

    def translate(self, x: float, y: float) -> None:
        self.state.transform.matrix = self.state.transform.matrix.multiply(
            Matrix2D.translation(float(x), float(y))
        )

    def rotate(self, angle: float) -> None:
        self.state.transform.matrix = self.state.transform.matrix.multiply(
            Matrix2D.rotation(self._angle(angle))
        )

    def scale(self, x: float, y: float | None = None) -> None:
        self.state.transform.matrix = self.state.transform.matrix.multiply(
            Matrix2D.scaling(float(x), None if y is None else float(y))
        )

    def shear_x(self, angle: float) -> None:
        self.state.transform.matrix = self.state.transform.matrix.multiply(
            Matrix2D.shear_x(self._angle(angle))
        )

    def shear_y(self, angle: float) -> None:
        self.state.transform.matrix = self.state.transform.matrix.multiply(
            Matrix2D.shear_y(self._angle(angle))
        )

    def apply_matrix(self, a: float, b: float, cc: float, d: float, e: float, f: float) -> None:
        self.state.transform.matrix = self.state.transform.matrix.multiply(
            Matrix2D(a, b, cc, d, e, f)
        )

    def reset_matrix(self) -> None:
        self.state.transform.matrix = Matrix2D.identity()

    def angle_mode(self, mode: str) -> None:
        if mode not in {c.RADIANS, c.DEGREES}:
            raise ArgumentValidationError(f"Unsupported angle mode {mode!r}.")
        self.angle_mode_value = mode

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

    def load_pixels(self) -> list[int]:
        return self.renderer.load_pixels()

    def update_pixels(self, pixels: list[int]) -> None:
        self.renderer.update_pixels(pixels)

    def save_canvas(self, path: str | Path) -> None:
        self.renderer.save(path)

    def update_mouse_event(self, event: MouseEvent, *, pressed: bool | None = None) -> None:
        self.state.input.update_mouse(event.x, event.y)
        if event.button is not None:
            self.state.input.mouse_button = event.button
        if pressed is not None:
            self.state.input.mouse_is_pressed = pressed

    def update_keyboard_event(self, event: KeyboardEvent, *, pressed: bool) -> None:
        self.state.input.key = event.key
        self.state.input.key_code = event.key_code
        self.state.input.key_is_pressed = pressed
        if event.key_code is not None:
            if pressed:
                self.state.input.pressed_keys.add(event.key_code)
            else:
                self.state.input.pressed_keys.discard(event.key_code)

    def key_is_down(self, key_code: int) -> bool:
        return self.state.input.key_is_down(key_code)

    def _angle(self, value: float) -> float:
        mode = getattr(self, "angle_mode_value", c.RADIANS)
        return math.radians(value) if mode == c.DEGREES else float(value)
