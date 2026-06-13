"""Sketch context containing mutable runtime state."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

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
from p5_py.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Shader3D,
    ShaderUniformValue,
    Texture3D,
    Vec3,
)
from p5_py.drawing.software3d import (
    box_model,
    plane_model,
    rasterize_faces_image,
    shade_model_faces,
    sphere_model,
)
from p5_py.events.input_state import KeyboardEvent, MouseEvent, TouchEvent, TouchPoint
from p5_py.exceptions import ArgumentValidationError, BackendCapabilityError, ShaderUniformError

if TYPE_CHECKING:
    from p5_py.plugins.registry import PluginRegistry

_MATERIAL_UNSET = object()


class SketchContext:
    """Mutable state and operations for one running sketch."""

    def __init__(self, sketch, backend, *, plugins: PluginRegistry) -> None:
        self.sketch = sketch
        self.backend = backend
        self.renderer = backend.renderer
        self.plugins = plugins
        self.state = SketchState()
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
        renderer: str = c.P2D,
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
        self._material3d_style_stack.append((self._material3d, self._normal_material3d))

    def pop(self) -> None:
        if not self.state.stack:
            raise ArgumentValidationError("pop() called without matching push().")
        entry = self.state.stack.pop()
        self.state.style = entry.style
        self.state.transform.matrix = entry.matrix
        self._material3d, self._normal_material3d = self._material3d_style_stack.pop()

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

    def create_camera(self, *args: object) -> Camera3D:
        return self.camera(*args)

    def camera(self, *args: object) -> Camera3D:
        self._require_webgl_mode("camera")
        if len(args) == 0:
            camera = Camera3D()
        elif len(args) == 1 and isinstance(args[0], Camera3D):
            camera = args[0]
        elif len(args) == 9 and all(isinstance(value, int | float) for value in args):
            numeric_args = self._numeric_values(args)
            camera = Camera3D(
                eye=Vec3(numeric_args[0], numeric_args[1], numeric_args[2]),
                target=Vec3(numeric_args[3], numeric_args[4], numeric_args[5]),
                up=Vec3(numeric_args[6], numeric_args[7], numeric_args[8]),
            )
        else:
            raise ArgumentValidationError(
                "camera() accepts no arguments, a Camera3D, or nine numeric values."
            )
        self._camera3d = camera
        return camera

    def perspective(self, *args: object) -> PerspectiveProjection:
        self._require_webgl_mode("perspective")
        if len(args) > 4 or not all(isinstance(value, int | float) for value in args):
            raise ArgumentValidationError(
                "perspective() accepts fov, aspect, near, and far numeric values."
            )
        numeric_args = self._numeric_values(args)
        fov_y = 60.0 if len(numeric_args) == 0 else math.degrees(self._angle(numeric_args[0]))
        aspect = None if len(numeric_args) < 2 else numeric_args[1]
        near = 0.1 if len(numeric_args) < 3 else numeric_args[2]
        far = 10_000.0 if len(numeric_args) < 4 else numeric_args[3]
        projection = PerspectiveProjection(fov_y=fov_y, aspect=aspect, near=near, far=far)
        self._projection3d = projection
        return projection

    def ortho(self, *args: object) -> OrthographicProjection:
        self._require_webgl_mode("ortho")
        if len(args) not in {0, 2, 4} or not all(isinstance(value, int | float) for value in args):
            raise ArgumentValidationError(
                "ortho() accepts no arguments, width/height, or width/height/near/far."
            )
        numeric_args = self._numeric_values(args)
        ortho_width = float(self.width) if len(numeric_args) == 0 else numeric_args[0]
        ortho_height = float(self.height) if len(numeric_args) == 0 else numeric_args[1]
        near = 0.1 if len(numeric_args) < 4 else numeric_args[2]
        far = 10_000.0 if len(numeric_args) < 4 else numeric_args[3]
        projection = OrthographicProjection(
            width=ortho_width,
            height=ortho_height,
            near=near,
            far=far,
        )
        self._projection3d = projection
        return projection

    def orbit_control(self, *args: object) -> Camera3D:
        self._require_webgl_mode("orbit_control")
        if len(args) > 3 or not all(isinstance(value, int | float) for value in args):
            raise ArgumentValidationError(
                "orbit_control() accepts up to three numeric sensitivity values."
            )
        numeric_args = self._numeric_values(args)
        sensitivity_x = 1.0 if len(numeric_args) == 0 else numeric_args[0]
        sensitivity_y = sensitivity_x if len(numeric_args) < 2 else numeric_args[1]
        sensitivity_z = 1.0 if len(numeric_args) < 3 else numeric_args[2]
        if sensitivity_x <= 0 or sensitivity_y <= 0 or sensitivity_z <= 0:
            raise ArgumentValidationError("orbit_control() sensitivities must be positive.")

        dx = self._frame_mouse_dx
        dy = self._frame_mouse_dy
        scroll_y = self._frame_scroll_y
        offset = Vec3(
            self._camera3d.eye.x - self._camera3d.target.x,
            self._camera3d.eye.y - self._camera3d.target.y,
            self._camera3d.eye.z - self._camera3d.target.z,
        )
        radius = math.sqrt(offset.x * offset.x + offset.y * offset.y + offset.z * offset.z)
        if radius <= 0:
            raise ArgumentValidationError("orbit_control() requires a non-zero camera distance.")

        azimuth = math.atan2(offset.x, offset.z)
        polar = math.acos(max(-1.0, min(1.0, offset.y / radius)))
        if self.state.input.mouse_is_pressed:
            azimuth -= dx * 0.01 * sensitivity_x
            polar = max(1e-3, min(math.pi - 1e-3, polar + dy * 0.01 * sensitivity_y))
        if scroll_y != 0.0:
            radius = max(1.0, radius * math.exp(-scroll_y * 0.1 * sensitivity_z))

        sin_polar = math.sin(polar)
        new_eye = Vec3(
            self._camera3d.target.x + radius * sin_polar * math.sin(azimuth),
            self._camera3d.target.y + radius * math.cos(polar),
            self._camera3d.target.z + radius * sin_polar * math.cos(azimuth),
        )
        self._camera3d = Camera3D(eye=new_eye, target=self._camera3d.target, up=Vec3(0.0, 1.0, 0.0))
        self._frame_mouse_dx = 0.0
        self._frame_mouse_dy = 0.0
        self._frame_scroll_x = 0.0
        self._frame_scroll_y = 0.0
        return self._camera3d

    def ambient_light(self, *args: object) -> None:
        self._require_webgl_mode("ambient_light")
        self._lights3d.append(Light3D(kind="ambient", color=self._color_to_rgba(self.color(*args))))

    def directional_light(self, *args: object) -> None:
        self._require_webgl_mode("directional_light")
        color, tail = self._split_color_args(args, tail_count=3)
        self._lights3d.append(
            Light3D(
                kind="directional",
                color=self._color_to_rgba(color),
                direction=Vec3(float(tail[0]), float(tail[1]), float(tail[2])),
            )
        )

    def point_light(self, *args: object) -> None:
        self._require_webgl_mode("point_light")
        color, tail = self._split_color_args(args, tail_count=3)
        self._lights3d.append(
            Light3D(
                kind="point",
                color=self._color_to_rgba(color),
                position=Vec3(float(tail[0]), float(tail[1]), float(tail[2])),
            )
        )

    def normal_material(self) -> None:
        self._require_webgl_mode("normal_material")
        self._material3d = None
        self._normal_material3d = True

    def ambient_material(self, *args: object) -> None:
        self._require_webgl_mode("ambient_material")
        self._material3d = self._replace_material(
            base_color=self._color_to_rgba(self.color(*args)),
            texture=None,
        )
        self._normal_material3d = False

    def specular_material(self, *args: object) -> None:
        self._require_webgl_mode("specular_material")
        color = self._color_to_rgba(self.color(*args))
        self._material3d = self._replace_material(
            base_color=color,
            specular_color=color,
            texture=None,
        )
        self._normal_material3d = False

    def shininess(self, value: float) -> None:
        self._require_webgl_mode("shininess")
        if value <= 0:
            raise ArgumentValidationError("shininess() must be positive.")
        self._material3d = self._replace_material(shininess=float(value))

    def texture(self, image: Image) -> None:
        self._require_webgl_mode("texture")
        if not isinstance(image, Image):
            raise ArgumentValidationError("texture() requires a p5_py Image object.")
        self._material3d = self._replace_material(
            texture=Texture3D(source=image, width=image.width, height=image.height)
        )
        self._normal_material3d = False

    def load_shader(self, vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
        from p5_py.assets.shader import load_shader as _load_shader

        return _load_shader(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str) -> Shader3D:
        from p5_py.assets.shader import create_shader as _create_shader

        return _create_shader(vertex_source, fragment_source)

    def shader(self, shader: Shader3D) -> None:
        self._require_webgl_mode("shader")
        if not self.backend.capabilities.shaders:
            enable_native_webgl = getattr(self.backend, "enable_native_webgl", None)
            if callable(enable_native_webgl) and enable_native_webgl():
                self.renderer = self.backend.renderer
        if not self.backend.capabilities.shaders:
            raise BackendCapabilityError(
                f"Backend {self.backend.name!r} does not support shader()."
            )
        if not isinstance(shader, Shader3D):
            raise ArgumentValidationError("shader() requires a Shader3D value.")
        self._shader3d = shader

    def reset_shader(self) -> None:
        self._require_webgl_mode("reset_shader")
        self._shader3d = None

    def set_shader_uniform(self, name: str, value: object) -> None:
        self._require_webgl_mode("set_shader_uniform")
        if self._shader3d is None:
            raise ShaderUniformError(
                f"Cannot set uniform {name!r} without an active shader. Call shader(...) first."
            )
        self._shader3d.set_uniform(name, cast("ShaderUniformValue", value))

    def plane(self, width: float, height: float | None = None) -> None:
        self.model(plane_model(float(width), None if height is None else float(height)))

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        self.model(
            box_model(
                float(width),
                None if height is None else float(height),
                None if depth is None else float(depth),
            )
        )

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        self.model(sphere_model(float(radius), int(detail_x), int(detail_y)))

    def model(self, shape: object) -> None:
        self._require_webgl_mode("model")
        if isinstance(shape, Mesh3D):
            model = Model3D(meshes=(shape,))
        elif isinstance(shape, Model3D):
            model = shape
        else:
            raise ArgumentValidationError("model() requires a Mesh3D or Model3D value.")

        native_renderer = self.renderer if getattr(self.renderer, "three_d", False) else None
        if native_renderer is not None and self.backend.name == c.PYGLET:
            material = self._effective_3d_material()
            native_renderer.set_camera(self._camera3d)
            native_renderer.set_projection(self._projection3d)
            native_renderer.set_lights(tuple(self._lights3d))
            native_renderer.set_material(material)
            native_renderer.set_texture(material.texture)
            native_renderer.use_shader(self._shader3d)
            native_renderer.draw_model(model)
            return

        faces = shade_model_faces(
            model,
            self._camera3d,
            self._projection3d,
            viewport_width=float(self.width),
            viewport_height=float(self.height),
            base_material=self._effective_3d_material(),
            lights=tuple(self._lights3d),
            normal_material=self._normal_material3d,
        )
        draw_fill = (
            self._normal_material3d
            or self._material3d is not None
            or self.state.style.fill_color is not None
        )
        if draw_fill:
            textured_faces = [
                face for face in faces if face.texture is not None and face.texcoords is not None
            ]
            if textured_faces:
                overlay = rasterize_faces_image(
                    faces,
                    viewport_width=float(self.width),
                    viewport_height=float(self.height),
                )
                overlay_style = self.state.style.copy()
                overlay_style.fill_color = None
                overlay_style.stroke_color = None
                self.renderer.draw_image(
                    overlay,
                    0.0,
                    0.0,
                    float(self.width),
                    float(self.height),
                    overlay_style,
                    self.state.transform.matrix,
                )
            else:
                for face in faces:
                    fill_style = self.state.style.copy()
                    fill_style.fill_color = self._rgba_float_to_color(face.color)
                    fill_style.stroke_color = None
                    self.renderer.polygon(
                        list(face.points),
                        fill_style,
                        self.state.transform.matrix,
                        close=True,
                    )
        if self.state.style.stroke_color is not None:
            stroke_style = self.state.style.copy()
            stroke_style.fill_color = None
            for face in faces:
                self.renderer.polygon(
                    list(face.points),
                    stroke_style,
                    self.state.transform.matrix,
                    close=True,
                )

    def image(self, image: Image, x: float, y: float, *args: float) -> None:
        if not isinstance(image, Image):
            raise ArgumentValidationError("image() requires a p5_py Image object.")
        w: float
        h: float
        source: tuple[int, int, int, int] | None
        if len(args) == 0:
            w = float(image.width)
            h = float(image.height)
            source = None
        elif len(args) == 2:
            w = float(args[0])
            h = float(args[1])
            source = None
        elif len(args) == 6:
            w = float(args[0])
            h = float(args[1])
            sx = float(args[2])
            sy = float(args[3])
            sw = float(args[4])
            sh = float(args[5])
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
        if event.type in {"mouse_moved", "mouse_dragged"}:
            self._frame_mouse_dx += event.dx
            self._frame_mouse_dy += event.dy
        if event.type == "mouse_wheel":
            self._frame_scroll_x += event.scroll_x
            self._frame_scroll_y += event.scroll_y
        self.update_mouse_event(event, pressed=pressed)
        self.plugins.dispatch_event("on_mouse_event", self, event)
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
        self.plugins.dispatch_event("on_keyboard_event", self, event)
        self.sketch._dispatch_callback(event.type, event)

    def update_touch_event(self, event: TouchEvent) -> None:
        self.state.input.require_touch_supported()
        self.state.input.update_touches(event.touches)

    def dispatch_touch_event(self, event: TouchEvent) -> None:
        self.update_touch_event(event)
        self.plugins.dispatch_event("on_touch_event", self, event)
        self.sketch._dispatch_callback(event.type, event)

    def key_is_down(self, key_code: int) -> bool:
        return self.state.input.key_is_down(key_code)

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


def _coerce_int(value: object) -> int:
    if isinstance(value, str | int | float):
        return int(value)
    raise ArgumentValidationError(
        f"Expected an integer-compatible value, got {type(value).__name__}."
    )
