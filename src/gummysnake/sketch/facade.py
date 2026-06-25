"""Object-oriented sketch convenience facade methods."""

from __future__ import annotations

from collections.abc import Buffer, Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake._fast_draw import FastDrawScope
from gummysnake.assets.image import Image
from gummysnake.context import SketchContext
from gummysnake.core.color import Color
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Shader3D,
)
from gummysnake.pixels import PixelBuffer

Number = int | float
ColorValue = Color | str


class SketchFacadeMixin:
    context: SketchContext | None

    def no_loop(self) -> None:
        self._ctx.no_loop()

    def loop(self) -> None:
        self._ctx.loop()

    def redraw(self) -> None:
        self._ctx.redraw()

    def is_looping(self) -> bool:
        return self._ctx.is_looping()

    def create_canvas(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode = c.P2D,
        *,
        pixel_density: float | None = None,
    ) -> None:
        self._ctx.create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)

    def resize_canvas(self, width: int, height: int, *, pixel_density: float | None = None) -> None:
        self._ctx.resize_canvas(width, height, pixel_density=pixel_density)

    def pixel_density(self, value: float | None = None) -> float:
        return self._ctx.pixel_density(value)

    def display_density(self) -> float:
        return self._ctx.display_density()

    def fast(self) -> FastDrawScope:
        return self._ctx.fast()

    def enable_performance_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        self._ctx.enable_performance_diagnostics(enabled, reset=reset)

    def reset_performance_diagnostics(self) -> None:
        self._ctx.reset_performance_diagnostics()

    def performance_diagnostics(self) -> dict[str, Any]:
        return self._ctx.performance_diagnostics()

    def renderer_performance_counters(self) -> dict[str, Any]:
        return self._ctx.renderer_performance_counters()

    def reset_renderer_performance_counters(self) -> None:
        self._ctx.reset_renderer_performance_counters()

    def enable_frame_pacing_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        self._ctx.enable_frame_pacing_diagnostics(enabled, reset=reset)

    def frame_pacing_diagnostics(self) -> dict[str, Any]:
        return self._ctx.frame_pacing_diagnostics()

    def reset_frame_pacing_diagnostics(self) -> None:
        self._ctx.reset_frame_pacing_diagnostics()

    @overload
    def background(self, value: ColorValue, /) -> None: ...

    @overload
    def background(self, gray: Number, /) -> None: ...

    @overload
    def background(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def background(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def background(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def background(self, *args: Any) -> None:
        cast(Any, self._ctx).background(*args)

    def clear(self) -> None:
        self._ctx.clear()

    @overload
    def fill(self, value: ColorValue, /) -> None: ...

    @overload
    def fill(self, gray: Number, /) -> None: ...

    @overload
    def fill(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def fill(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def fill(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def fill(self, *args: Any) -> None:
        cast(Any, self._ctx).fill(*args)

    def no_fill(self) -> None:
        self._ctx.no_fill()

    @overload
    def stroke(self, value: ColorValue, /) -> None: ...

    @overload
    def stroke(self, gray: Number, /) -> None: ...

    @overload
    def stroke(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def stroke(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def stroke(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def stroke(self, *args: Any) -> None:
        cast(Any, self._ctx).stroke(*args)

    def no_stroke(self) -> None:
        self._ctx.no_stroke()

    def stroke_weight(self, weight: float) -> None:
        self._ctx.stroke_weight(weight)

    def point(self, x: float, y: float) -> None:
        self._ctx.point(x, y)

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self._ctx.line(x1, y1, x2, y2)

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None:
        self._ctx.rect(x, y, width, height)

    def square(self, x: float, y: float, size: float) -> None:
        self._ctx.square(x, y, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        self._ctx.ellipse(x, y, width, height)

    def circle(self, x: float, y: float, diameter: float) -> None:
        self._ctx.circle(x, y, diameter)

    def triangle(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        self._ctx.triangle(x1, y1, x2, y2, x3, y3)

    def quad(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        x4: float,
        y4: float,
    ) -> None:
        self._ctx.quad(x1, y1, x2, y2, x3, y3, x4, y4)

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
        self._ctx.arc(x, y, width, height, start, stop, mode)

    def begin_shape(self, kind: c.ShapeKind | None = None) -> None:
        self._ctx.begin_shape(kind)

    @contextmanager
    def shape(
        self, mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None
    ) -> Generator[None]:
        with self._ctx.shape(mode, kind=kind):
            yield

    def begin_contour(self) -> None:
        self._ctx.begin_contour()

    @contextmanager
    def contour(self) -> Generator[None]:
        with self._ctx.contour():
            yield

    def end_contour(self) -> None:
        self._ctx.end_contour()

    def begin_clip(self) -> None:
        self._ctx.begin_clip()

    @contextmanager
    def clip_path(self) -> Generator[None]:
        with self._ctx.clip_path():
            yield

    def clip(self) -> None:
        self._ctx.clip()

    def end_clip(self) -> None:
        self._ctx.end_clip()

    def vertex(self, x: float, y: float) -> None:
        self._ctx.vertex(x, y)

    def bezier_vertex(
        self, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
    ) -> None:
        self._ctx.bezier_vertex(x2, y2, x3, y3, x4, y4)

    def quadratic_vertex(self, cx: float, cy: float, x3: float, y3: float) -> None:
        self._ctx.quadratic_vertex(cx, cy, x3, y3)

    def spline_vertex(self, x: float, y: float) -> None:
        self._ctx.spline_vertex(x, y)

    def end_shape(self, mode: c.ArcMode = c.OPEN) -> None:
        self._ctx.end_shape(mode)

    @overload
    def create_camera(self) -> Camera3D: ...

    @overload
    def create_camera(self, camera: Camera3D, /) -> Camera3D: ...

    @overload
    def create_camera(
        self,
        eye_x: Number,
        eye_y: Number,
        eye_z: Number,
        center_x: Number,
        center_y: Number,
        center_z: Number,
        up_x: Number,
        up_y: Number,
        up_z: Number,
        /,
    ) -> Camera3D: ...

    def create_camera(self, *args: Any) -> Camera3D:
        return self._ctx.create_camera(*args)

    @overload
    def camera(self) -> Camera3D: ...

    @overload
    def camera(self, camera: Camera3D, /) -> Camera3D: ...

    @overload
    def camera(
        self,
        eye_x: Number,
        eye_y: Number,
        eye_z: Number,
        center_x: Number,
        center_y: Number,
        center_z: Number,
        up_x: Number,
        up_y: Number,
        up_z: Number,
        /,
    ) -> Camera3D: ...

    def camera(self, *args: Any) -> Camera3D:
        return self._ctx.camera(*args)

    @overload
    def perspective(self) -> PerspectiveProjection: ...

    @overload
    def perspective(self, fov: Number, /) -> PerspectiveProjection: ...

    @overload
    def perspective(self, fov: Number, aspect: Number, /) -> PerspectiveProjection: ...

    @overload
    def perspective(
        self, fov: Number, aspect: Number, near: Number, /
    ) -> PerspectiveProjection: ...

    @overload
    def perspective(
        self, fov: Number, aspect: Number, near: Number, far: Number, /
    ) -> PerspectiveProjection: ...

    def perspective(self, *args: Any) -> PerspectiveProjection:
        return self._ctx.perspective(*args)

    @overload
    def ortho(self) -> OrthographicProjection: ...

    @overload
    def ortho(self, width: Number, height: Number, /) -> OrthographicProjection: ...

    @overload
    def ortho(
        self, width: Number, height: Number, near: Number, far: Number, /
    ) -> OrthographicProjection: ...

    def ortho(self, *args: Any) -> OrthographicProjection:
        return self._ctx.ortho(*args)

    @overload
    def orbit_control(self) -> Camera3D: ...

    @overload
    def orbit_control(self, sensitivity_x: Number, /) -> Camera3D: ...

    @overload
    def orbit_control(self, sensitivity_x: Number, sensitivity_y: Number, /) -> Camera3D: ...

    @overload
    def orbit_control(
        self, sensitivity_x: Number, sensitivity_y: Number, sensitivity_z: Number, /
    ) -> Camera3D: ...

    def orbit_control(self, *args: Any) -> Camera3D:
        return self._ctx.orbit_control(*args)

    @overload
    def ambient_light(self, value: ColorValue, /) -> None: ...

    @overload
    def ambient_light(self, gray: Number, /) -> None: ...

    @overload
    def ambient_light(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def ambient_light(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def ambient_light(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def ambient_light(self, *args: Any) -> None:
        cast(Any, self._ctx).ambient_light(*args)

    @overload
    def directional_light(self, value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def directional_light(self, gray: Number, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def directional_light(
        self, gray: Number, alpha: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def directional_light(
        self, v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def directional_light(
        self,
        v1: Number,
        v2: Number,
        v3: Number,
        alpha: Number,
        x: Number,
        y: Number,
        z: Number,
        /,
    ) -> None: ...

    def directional_light(self, *args: Any) -> None:
        cast(Any, self._ctx).directional_light(*args)

    @overload
    def point_light(self, value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def point_light(self, gray: Number, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def point_light(
        self, gray: Number, alpha: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def point_light(
        self, v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def point_light(
        self,
        v1: Number,
        v2: Number,
        v3: Number,
        alpha: Number,
        x: Number,
        y: Number,
        z: Number,
        /,
    ) -> None: ...

    def point_light(self, *args: Any) -> None:
        cast(Any, self._ctx).point_light(*args)

    def normal_material(self) -> None:
        self._ctx.normal_material()

    @overload
    def ambient_material(self, value: ColorValue, /) -> None: ...

    @overload
    def ambient_material(self, gray: Number, /) -> None: ...

    @overload
    def ambient_material(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def ambient_material(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def ambient_material(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def ambient_material(self, *args: Any) -> None:
        cast(Any, self._ctx).ambient_material(*args)

    @overload
    def specular_material(self, value: ColorValue, /) -> None: ...

    @overload
    def specular_material(self, gray: Number, /) -> None: ...

    @overload
    def specular_material(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def specular_material(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def specular_material(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def specular_material(self, *args: Any) -> None:
        cast(Any, self._ctx).specular_material(*args)

    def shininess(self, value: float) -> None:
        self._ctx.shininess(value)

    def texture(self, image: Image) -> None:
        self._ctx.texture(image)

    def plane(self, width: float, height: float | None = None) -> None:
        self._ctx.plane(width, height)

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        self._ctx.box(width, height, depth)

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        self._ctx.sphere(radius, detail_x, detail_y)

    def model(self, shape: Mesh3D | Model3D) -> None:
        self._ctx.model(shape)

    def load_shader(self, vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
        return self._ctx.load_shader(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str) -> Shader3D:
        return self._ctx.create_shader(vertex_source, fragment_source)

    def shader(self, shader_program: Shader3D) -> None:
        self._ctx.shader(shader_program)

    def reset_shader(self) -> None:
        self._ctx.reset_shader()

    def push(self) -> None:
        self._ctx.push()

    def pop(self) -> None:
        self._ctx.pop()

    @contextmanager
    def pushed(self) -> Generator[None]:
        self.push()
        try:
            yield
        finally:
            self.pop()

    def translate(self, x: float, y: float) -> None:
        self._ctx.translate(x, y)

    def rotate(self, angle: float) -> None:
        self._ctx.rotate(angle)

    def scale(self, x: float, y: float | None = None) -> None:
        self._ctx.scale(x, y)

    @property
    def width(self) -> int:
        return self._ctx.width

    @property
    def height(self) -> int:
        return self._ctx.height

    @property
    def frame_count(self) -> int:
        return self._ctx.frame_count

    def load_pixels(self) -> PixelBuffer:
        return self._ctx.load_pixels()

    def load_pixel_bytes(self) -> bytes:
        return self._ctx.load_pixel_bytes()

    def update_pixels(self, pixels: Sequence[int] | Buffer | None = None) -> None:
        self._ctx.update_pixels(pixels)

    def save_canvas(
        self, path: str | Path, *, extension: str | None = None, overwrite: bool = True
    ) -> Path:
        return self._ctx.save_canvas(path, extension=extension, overwrite=overwrite)

    def blend_mode(self, mode: c.BlendMode) -> None:
        self._ctx.blend_mode(mode)

    @overload
    def blend(
        self,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        mode: c.BlendMode,
        /,
    ) -> None: ...

    @overload
    def blend(
        self,
        image: Image,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        mode: c.BlendMode,
        /,
    ) -> None: ...

    def blend(self, *args: Any) -> None:
        cast(Any, self._ctx).blend(*args)

    def erase(self) -> None:
        self._ctx.erase()

    def no_erase(self) -> None:
        self._ctx.no_erase()

    @property
    def mouse_x(self) -> float:
        return self._ctx.mouse_x

    @property
    def mouse_y(self) -> float:
        return self._ctx.mouse_y

    @property
    def pmouse_x(self) -> float:
        return self._ctx.pmouse_x

    @property
    def pmouse_y(self) -> float:
        return self._ctx.pmouse_y

    @property
    def mouse_is_pressed(self) -> bool:
        return self._ctx.mouse_is_pressed

    @property
    def key(self) -> str | None:
        return self._ctx.key

    @property
    def key_code(self) -> int | None:
        return self._ctx.key_code

    @property
    def key_is_pressed(self) -> bool:
        return self._ctx.key_is_pressed

    def key_is_down(self, key_code: int) -> bool:
        return self._ctx.key_is_down(key_code)

    @property
    def _ctx(self) -> SketchContext:
        if self.context is None:
            raise RuntimeError("Sketch context is not available until run() starts.")
        return self.context
