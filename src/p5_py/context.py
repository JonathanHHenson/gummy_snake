"""Sketch context containing mutable runtime state."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from p5_py import constants as c
from p5_py.assets.image import Image
from p5_py.assets.text import Font
from p5_py.core import math as p5math
from p5_py.core.color import Color, lerp_color
from p5_py.core.geometry import (
    flatten_cubic,
    flatten_quadratic,
    resolve_ellipse,
    resolve_rect,
)
from p5_py.core.state import SketchState, StateStackEntry
from p5_py.core.transform import Matrix2D
from p5_py.events.input_state import KeyboardEvent, MouseEvent, TouchEvent, TouchPoint
from p5_py.exceptions import ArgumentValidationError


class SketchContext:
    """Mutable state and operations for one running sketch."""

    def __init__(self, sketch, backend) -> None:
        self.sketch = sketch
        self.backend = backend
        self.renderer = backend.renderer
        self.state = SketchState()
        self.pixels: Sequence[int] = []

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

    def create_canvas(
        self,
        width: int,
        height: int,
        *,
        pixel_density: float | None = None,
    ) -> None:
        self.backend.create_canvas(int(width), int(height), pixel_density)
        self.renderer = self.backend.renderer
        self._sync_canvas_state()
        self.state.canvas.created = True

    def resize_canvas(self, width: int, height: int, *, pixel_density: float | None = None) -> None:
        density = self.state.canvas.pixel_density if pixel_density is None else pixel_density
        self.backend.resize_canvas(int(width), int(height), float(density))
        self.renderer = self.backend.renderer
        self._sync_canvas_state()
        self.state.canvas.created = True

    def ensure_canvas(self) -> None:
        if not self.state.canvas.created:
            self.create_canvas(self.state.canvas.width, self.state.canvas.height)

    def pixel_density(self, value: float | None = None) -> float:
        if value is None:
            return self.state.canvas.pixel_density
        if value <= 0:
            raise ArgumentValidationError("pixel_density() must be positive.")
        self.resize_canvas(self.state.canvas.width, self.state.canvas.height, pixel_density=value)
        return self.state.canvas.pixel_density

    def display_density(self) -> float:
        return self.backend.display_density()

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

    def stroke_cap(self, cap: str) -> None:
        if cap not in {c.ROUND, c.SQUARE, c.PROJECT}:
            raise ArgumentValidationError(f"Unsupported stroke cap {cap!r}.")
        self.state.style.stroke_cap = cap

    def stroke_join(self, join: str) -> None:
        if join not in {c.MITER, c.BEVEL, c.ROUND}:
            raise ArgumentValidationError(f"Unsupported stroke join {join!r}.")
        self.state.style.stroke_join = join

    def rect_mode(self, mode: str) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported rect mode {mode!r}.")
        self.state.style.rect_mode = mode

    def ellipse_mode(self, mode: str) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER, c.RADIUS}:
            raise ArgumentValidationError(f"Unsupported ellipse mode {mode!r}.")
        self.state.style.ellipse_mode = mode

    def image_mode(self, mode: str) -> None:
        if mode not in {c.CORNER, c.CORNERS, c.CENTER}:
            raise ArgumentValidationError(f"Unsupported image mode {mode!r}.")
        self.state.style.image_mode = mode

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
        p5math.set_angle_mode(mode)

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

    def image(self, image: Image, x: float, y: float, *args: float) -> None:
        if not isinstance(image, Image):
            raise ArgumentValidationError("image() requires a p5_py Image object.")
        if len(args) == 0:
            w, h = image.width, image.height
            source = None
        elif len(args) == 2:
            w, h = args
            source = None
        elif len(args) == 6:
            w, h, sx, sy, sw, sh = args
            source = (int(sx), int(sy), int(sw), int(sh))
        else:
            raise ArgumentValidationError(
                "image() accepts image, x, y; image, x, y, w, h; "
                "or image, x, y, w, h, sx, sy, sw, sh."
            )
        dx, dy, dw, dh = resolve_rect(
            self.state.style.image_mode, float(x), float(y), float(w), float(h)
        )
        self.renderer.draw_image(
            image,
            dx,
            dy,
            dw,
            dh,
            self.state.style,
            self.state.transform.matrix,
            source=source,
        )

    def text(self, value: object, x: float, y: float) -> None:
        self.renderer.text(
            str(value), float(x), float(y), self.state.style, self.state.transform.matrix
        )

    def text_size(self, size: float | None = None) -> float:
        if size is not None:
            if size <= 0:
                raise ArgumentValidationError("text_size() must be positive.")
            self.state.style.text_size = float(size)
        return self.state.style.text_size

    def text_font(self, font: Font | str | None = None) -> Font:
        if font is not None:
            if isinstance(font, str):
                font = Font(name=font)
            self.state.style.text_font = font
        return self.state.style.text_font

    def text_style(self, style: str | None = None) -> str:
        if style is not None:
            if style not in {c.NORMAL, c.ITALIC, c.BOLD, c.BOLDITALIC}:
                raise ArgumentValidationError(f"Unsupported text style {style!r}.")
            self.state.style.text_style = style
        return self.state.style.text_style

    def text_align(self, horizontal: str, vertical: str | None = None) -> None:
        if horizontal not in {c.LEFT, c.CENTER, c.RIGHT}:
            raise ArgumentValidationError(f"Unsupported horizontal text alignment {horizontal!r}.")
        if vertical is not None and vertical not in {c.TOP, c.CENTER, c.BOTTOM, c.BASELINE}:
            raise ArgumentValidationError(f"Unsupported vertical text alignment {vertical!r}.")
        self.state.style.text_align_x = horizontal
        if vertical is not None:
            self.state.style.text_align_y = vertical

    def text_leading(self, value: float | None = None) -> float:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("text_leading() must be positive.")
            self.state.style.text_leading = float(value)
        return self.state.style.text_leading

    def text_width(self, value: object) -> float:
        return self.renderer.text_width(str(value), self.state.style)

    def text_ascent(self) -> float:
        return self.renderer.text_ascent(self.state.style)

    def text_descent(self) -> float:
        return self.renderer.text_descent(self.state.style)

    def load_pixels(self) -> list[int]:
        pixels = self.renderer.load_pixels()
        self.pixels = pixels
        return pixels

    def update_pixels(self, pixels: Sequence[int] | None = None) -> None:
        if pixels is not None:
            self.pixels = pixels
        if not self.pixels:
            self.load_pixels()
        self.renderer.update_pixels(self.pixels)

    def pixel_array(self) -> list[list[tuple[int, int, int, int]]]:
        pixels = self.pixels or self.load_pixels()
        width = self.state.canvas.physical_width
        rows: list[list[tuple[int, int, int, int]]] = []
        for row_start in range(0, len(pixels), width * 4):
            row: list[tuple[int, int, int, int]] = []
            for index in range(row_start, row_start + width * 4, 4):
                row.append((pixels[index], pixels[index + 1], pixels[index + 2], pixels[index + 3]))
            rows.append(row)
        return rows

    def save_canvas(
        self,
        path: str | Path,
        *,
        extension: str | None = None,
        overwrite: bool = True,
    ) -> Path:
        output = Path(path)
        if output.name in {"", "."}:
            raise ArgumentValidationError("save_canvas() requires a file path, not a directory.")
        if extension is not None:
            suffix = extension if extension.startswith(".") else f".{extension}"
            output = output.with_suffix(suffix.lower())
        elif output.suffix == "":
            output = output.with_suffix(".png")
        if output.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}:
            raise ArgumentValidationError(f"Unsupported canvas export format {output.suffix!r}.")
        if output.exists() and not overwrite:
            raise ArgumentValidationError(f"Refusing to overwrite existing file: {output!s}.")
        output.parent.mkdir(parents=True, exist_ok=True)
        self.renderer.save(output)
        return output

    def blend_mode(self, mode: str) -> None:
        if mode not in self.backend.capabilities.blend_modes:
            raise ArgumentValidationError(
                f"Unsupported blend mode {mode!r} for backend {self.backend.name!r}."
            )
        self.state.style.blend_mode = mode

    def blend(self, *args: object) -> None:
        if len(args) == 9:
            source_image = None
            sx, sy, sw, sh, dx, dy, dw, dh, mode = args
        elif len(args) == 10 and isinstance(args[0], Image):
            source_image = args[0].pillow
            sx, sy, sw, sh, dx, dy, dw, dh, mode = args[1:]
        else:
            raise ArgumentValidationError(
                "blend() accepts sx, sy, sw, sh, dx, dy, dw, dh, mode or "
                "image, sx, sy, sw, sh, dx, dy, dw, dh, mode."
            )
        if not isinstance(mode, str):
            raise ArgumentValidationError("blend() mode must be a string blend constant.")
        if mode not in self.backend.capabilities.blend_modes:
            raise ArgumentValidationError(
                f"Unsupported blend mode {mode!r} for backend {self.backend.name!r}."
            )
        self.renderer.blend_region(
            source_image,
            (_coerce_int(sx), _coerce_int(sy), _coerce_int(sw), _coerce_int(sh)),
            (_coerce_int(dx), _coerce_int(dy), _coerce_int(dw), _coerce_int(dh)),
            mode,
        )

    def erase(self) -> None:
        self.state.style.erasing = True

    def no_erase(self) -> None:
        self.state.style.erasing = False

    @property
    def pmouse_x(self) -> float:
        return self.state.input.previous_mouse_x

    @property
    def pmouse_y(self) -> float:
        return self.state.input.previous_mouse_y

    @property
    def moved_x(self) -> float:
        return self.state.input.moved_x

    @property
    def moved_y(self) -> float:
        return self.state.input.moved_y

    @property
    def mouse_is_pressed(self) -> bool:
        return self.state.input.mouse_is_pressed

    @property
    def mouse_button(self) -> str | None:
        return self.state.input.mouse_button

    @property
    def key(self) -> str | None:
        return self.state.input.key

    @property
    def key_code(self) -> int | None:
        return self.state.input.key_code

    @property
    def key_is_pressed(self) -> bool:
        return self.state.input.key_is_pressed

    @property
    def touches(self) -> list[TouchPoint]:
        return list(self.state.input.touches)

    def update_mouse_event(self, event: MouseEvent, *, pressed: bool | None = None) -> None:
        self.state.input.update_mouse(event.x, event.y, dx=event.dx, dy=event.dy)
        if event.button is not None:
            self.state.input.mouse_button = event.button
        if pressed is not None:
            self.state.input.mouse_is_pressed = pressed
            if not pressed and event.button is not None:
                self.state.input.mouse_button = event.button

    def dispatch_mouse_event(self, event: MouseEvent) -> None:
        pressed = None
        if event.type == "mouse_pressed":
            pressed = True
        elif event.type == "mouse_released":
            pressed = False
        self.update_mouse_event(event, pressed=pressed)
        self.sketch._dispatch_callback(event.type, event)

    def update_keyboard_event(self, event: KeyboardEvent, *, pressed: bool | None = None) -> None:
        self.state.input.key = event.key
        self.state.input.key_code = event.key_code
        if pressed is not None:
            self.state.input.key_is_pressed = pressed
        if event.key_code is not None and pressed is not None:
            if pressed:
                self.state.input.pressed_keys.add(event.key_code)
            else:
                self.state.input.pressed_keys.discard(event.key_code)

    def dispatch_keyboard_event(self, event: KeyboardEvent) -> None:
        pressed = None
        if event.type == "key_pressed":
            pressed = True
        elif event.type == "key_released":
            pressed = False
        self.update_keyboard_event(event, pressed=pressed)
        self.sketch._dispatch_callback(event.type, event)

    def update_touch_event(self, event: TouchEvent) -> None:
        self.state.input.require_touch_supported()
        self.state.input.update_touches(event.touches)

    def dispatch_touch_event(self, event: TouchEvent) -> None:
        self.update_touch_event(event)
        self.sketch._dispatch_callback(event.type, event)

    def key_is_down(self, key_code: int) -> bool:
        return self.state.input.key_is_down(key_code)

    def _angle(self, value: float) -> float:
        mode = getattr(self, "angle_mode_value", c.RADIANS)
        return math.radians(value) if mode == c.DEGREES else float(value)


def _coerce_int(value: object) -> int:
    if isinstance(value, str | int | float):
        return int(value)
    raise ArgumentValidationError(
        f"Expected an integer-compatible value, got {type(value).__name__}."
    )
