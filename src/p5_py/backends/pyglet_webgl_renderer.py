"""Native Pyglet WEBGL-style renderer backed by a depth-tested OpenGL path."""

from __future__ import annotations

import ctypes
import math
from collections.abc import Sequence
from typing import Any, cast

from p5_py.assets.image import Image
from p5_py.backends.pyglet_renderer import PygletRenderer
from p5_py.core.color import Color
from p5_py.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Mesh3D,
    Model3D,
    PerspectiveProjection,
    Projection3D,
    Shader3D,
    ShaderUniformValue,
    Texture3D,
    Vec3,
)
from p5_py.exceptions import ShaderCompilationError, ShaderUniformError


def _normalize(v: Vec3) -> Vec3:
    length = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
    if length <= 0:
        return Vec3(0.0, 0.0, 1.0)
    return Vec3(v.x / length, v.y / length, v.z / length)


def _subtract(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def _multiply_matrix(
    a: tuple[tuple[float, ...], ...], b: tuple[tuple[float, ...], ...]
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(sum(a[row][k] * b[k][col] for k in range(4)) for col in range(4)) for row in range(4)
    )


def _flatten_column_major(matrix: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    return tuple(matrix[row][col] for col in range(4) for row in range(4))


def _triangulate(face: tuple[int, ...]) -> list[tuple[int, int, int]]:
    if len(face) < 3:
        return []
    return [(face[0], face[index], face[index + 1]) for index in range(1, len(face) - 1)]


class PygletWebGLRenderer(PygletRenderer):
    """Pyglet renderer with a native OpenGL draw path for WEBGL sketches."""

    three_d = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._camera = Camera3D()
        self._projection: Projection3D = PerspectiveProjection()
        self._lights: tuple[Light3D, ...] = ()
        self._material: Material3D | None = None
        self._texture: Texture3D | None = None
        self._active_shader: Shader3D | None = None
        self._shader_programs: dict[int, int] = {}
        self._queued_models: list[
            tuple[Model3D, Material3D | None, Texture3D | None, Shader3D | None]
        ] = []
        self._clear_color = (0.0, 0.0, 0.0, 0.0)

    def begin_frame(self) -> None:
        super().begin_frame()
        self._queued_models = []

    def background(self, color: Color) -> None:
        self._clear_color = (
            color.r / 255.0,
            color.g / 255.0,
            color.b / 255.0,
            color.a / 255.0,
        )
        super().background(color)

    def set_camera(self, camera: Camera3D) -> None:
        self._camera = camera

    def set_projection(self, projection: Projection3D) -> None:
        self._projection = projection

    def set_lights(self, lights: Sequence[Light3D]) -> None:
        self._lights = tuple(lights)

    def set_material(self, material: Material3D | None) -> None:
        self._material = material

    def set_texture(self, texture: Texture3D | None) -> None:
        self._texture = texture

    def use_shader(self, shader: Shader3D | None) -> None:
        self._active_shader = shader

    def set_shader_uniform(self, name: str, value: ShaderUniformValue) -> None:
        if self._active_shader is None:
            raise ShaderUniformError(
                f"Cannot set uniform {name!r} without an active shader on backend 'pyglet'."
            )
        self._active_shader.set_uniform(name, value)

    def draw_model(
        self, model: Model3D, transform: tuple[tuple[float, ...], ...] | None = None
    ) -> None:
        del transform
        self._queued_models.append((model, self._material, self._texture, self._active_shader))

    def draw_mesh(
        self, mesh: Mesh3D, transform: tuple[tuple[float, ...], ...] | None = None
    ) -> None:
        del transform
        self.draw_model(Model3D(meshes=(mesh,)))

    def plane(self, width: float, height: float) -> None:
        del width, height

    def box(self, width: float, height: float, depth: float) -> None:
        del width, height, depth

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        del radius, detail_x, detail_y

    def draw(self) -> None:
        if not self._queued_models:
            super().draw()
            return
        self._render_native_scene()

    def _render_native_scene(self) -> None:
        pyglet = self._load_pyglet()
        gl = pyglet.gl
        viewport = (0, 0, self.physical_width, self.physical_height)
        gl.glViewport(*viewport)
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDepthMask(gl.GL_TRUE)
        gl.glClearColor(*self._clear_color)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        if self._batch is not None and not self._parity_active:
            self._batch.draw()

        projection = _projection_matrix(self._projection, self.width, self.height)
        view = _view_matrix(self._camera)
        mvp = _multiply_matrix(projection, view)

        projection_array = (ctypes.c_float * 16)(*_flatten_column_major(projection))
        model_view_array = (ctypes.c_float * 16)(*_flatten_column_major(view))
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadMatrixf(projection_array)
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glLoadMatrixf(model_view_array)

        for model, material, texture, shader in self._queued_models:
            program = 0
            if shader is not None:
                program = self._program_for_shader(shader)
                gl.glUseProgram(program)
                self._apply_builtin_uniforms(gl, program, projection, view, mvp)
                for uniform_name, uniform_value in shader.uniforms.items():
                    self._apply_uniform(gl, program, uniform_name, uniform_value)
            else:
                gl.glUseProgram(0)
            self._bind_material_texture(gl, program, material, texture)
            self._draw_model_immediate(gl, model, material)
            if shader is not None:
                gl.glUseProgram(0)
        gl.glDisable(gl.GL_DEPTH_TEST)

    def _draw_model_immediate(self, gl: Any, model: Model3D, material: Material3D | None) -> None:
        rgba = (1.0, 1.0, 1.0, 1.0) if material is None else material.base_color
        gl.glColor4f(*rgba)
        for mesh in model.meshes:
            for face in mesh.faces:
                triangles = _triangulate(face)
                if not triangles:
                    continue
                gl.glBegin(gl.GL_TRIANGLES)
                try:
                    for ia, ib, ic in triangles:
                        for index in (ia, ib, ic):
                            vertex = mesh.vertices[index]
                            gl.glVertex3f(vertex.x, vertex.y, vertex.z)
                finally:
                    gl.glEnd()

    def _program_for_shader(self, shader: Shader3D) -> int:
        key = id(shader)
        if key in self._shader_programs:
            return self._shader_programs[key]
        pyglet = self._load_pyglet()
        gl = pyglet.gl
        vertex_shader = self._compile_shader(
            gl, gl.GL_VERTEX_SHADER, shader.vertex_source, shader.vertex_path
        )
        fragment_shader = self._compile_shader(
            gl, gl.GL_FRAGMENT_SHADER, shader.fragment_source, shader.fragment_path
        )
        program = gl.glCreateProgram()
        gl.glAttachShader(program, vertex_shader)
        gl.glAttachShader(program, fragment_shader)
        gl.glLinkProgram(program)
        status = ctypes.c_int()
        gl.glGetProgramiv(program, gl.GL_LINK_STATUS, ctypes.byref(status))
        if status.value != gl.GL_TRUE:
            raise ShaderCompilationError(
                _link_error_message(gl, program, backend="pyglet", shader=shader)
            )
        self._shader_programs[key] = int(program)
        return int(program)

    def _compile_shader(self, gl: Any, shader_type: int, source: str, path: object) -> int:
        shader = gl.glCreateShader(shader_type)
        encoded = source.encode("utf-8")
        source_buffer = ctypes.c_char_p(encoded)
        source_ptr = ctypes.cast(
            ctypes.pointer(source_buffer), ctypes.POINTER(ctypes.POINTER(ctypes.c_char))
        )
        length = ctypes.c_int(len(encoded))
        gl.glShaderSource(shader, 1, source_ptr, ctypes.byref(length))
        gl.glCompileShader(shader)
        status = ctypes.c_int()
        gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS, ctypes.byref(status))
        if status.value != gl.GL_TRUE:
            stage = "vertex" if shader_type == gl.GL_VERTEX_SHADER else "fragment"
            raise ShaderCompilationError(
                _compile_error_message(gl, shader, backend="pyglet", stage=stage, path=path)
            )
        return int(shader)

    def _apply_builtin_uniforms(
        self,
        gl: Any,
        program: int,
        projection: tuple[tuple[float, ...], ...],
        view: tuple[tuple[float, ...], ...],
        mvp: tuple[tuple[float, ...], ...],
    ) -> None:
        for name, matrix in {
            "u_projection": projection,
            "u_view": view,
            "u_model": _identity4(),
            "u_model_view_projection": mvp,
        }.items():
            with_context = _uniform_location(gl, program, name)
            if with_context >= 0:
                gl.glUniformMatrix4fv(
                    with_context,
                    1,
                    gl.GL_FALSE,
                    (ctypes.c_float * 16)(*_flatten_column_major(matrix)),
                )

    def _bind_material_texture(
        self,
        gl: Any,
        program: int,
        material: Material3D | None,
        texture: Texture3D | None,
    ) -> None:
        candidate = texture or (material.texture if material is not None else None)
        if candidate is None:
            return
        source = candidate.source
        if isinstance(source, Image):
            texture_id = self._upload_image_texture(gl, source)
            gl.glActiveTexture(gl.GL_TEXTURE0)
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
            if program:
                location = _uniform_location(gl, program, "u_texture")
                if location >= 0:
                    gl.glUniform1i(location, 0)

    def _upload_image_texture(self, gl: Any, image: Image) -> int:
        texture_id = ctypes.c_uint()
        gl.glGenTextures(1, ctypes.byref(texture_id))
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id.value)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        rgba = image.pillow.convert("RGBA")
        data = rgba.tobytes()
        gl.glTexImage2D(
            gl.GL_TEXTURE_2D,
            0,
            gl.GL_RGBA,
            rgba.width,
            rgba.height,
            0,
            gl.GL_RGBA,
            gl.GL_UNSIGNED_BYTE,
            data,
        )
        return int(texture_id.value)

    def _apply_uniform(self, gl: Any, program: int, name: str, value: ShaderUniformValue) -> None:
        location = _uniform_location(gl, program, name)
        if location < 0:
            return
        if isinstance(value, bool):
            gl.glUniform1i(location, 1 if value else 0)
            return
        if isinstance(value, int):
            gl.glUniform1i(location, value)
            return
        if isinstance(value, float):
            gl.glUniform1f(location, value)
            return
        if isinstance(value, Vec3):
            gl.glUniform3f(location, value.x, value.y, value.z)
            return
        if isinstance(value, Texture3D):
            self._bind_material_texture(gl, program, None, value)
            gl.glUniform1i(location, 0)
            return
        if (
            isinstance(value, tuple)
            and value
            and all(isinstance(item, int | float) for item in value)
        ):
            scalar_items = cast(tuple[int | float, ...], value)
            floats = tuple(float(item) for item in scalar_items)
            if len(floats) == 2:
                gl.glUniform2f(location, floats[0], floats[1])
                return
            if len(floats) == 3:
                gl.glUniform3f(location, floats[0], floats[1], floats[2])
                return
            if len(floats) == 4:
                gl.glUniform4f(location, floats[0], floats[1], floats[2], floats[3])
                return
        if isinstance(value, tuple) and value and all(isinstance(row, tuple) for row in value):
            rows = cast(tuple[tuple[float, ...], ...], value)
            if len(rows) == 2 and all(len(row) == 2 for row in rows):
                gl.glUniformMatrix2fv(
                    location,
                    1,
                    gl.GL_FALSE,
                    (ctypes.c_float * 4)(rows[0][0], rows[1][0], rows[0][1], rows[1][1]),
                )
                return
            if len(rows) == 3 and all(len(row) == 3 for row in rows):
                flattened = tuple(rows[row][col] for col in range(3) for row in range(3))
                gl.glUniformMatrix3fv(location, 1, gl.GL_FALSE, (ctypes.c_float * 9)(*flattened))
                return
            if len(rows) == 4 and all(len(row) == 4 for row in rows):
                gl.glUniformMatrix4fv(
                    location,
                    1,
                    gl.GL_FALSE,
                    (ctypes.c_float * 16)(*_flatten_column_major(rows)),
                )
                return
        raise ShaderUniformError(
            f"Unsupported uniform value for {name!r} on backend 'pyglet': {type(value).__name__}."
        )


def _identity4() -> tuple[tuple[float, ...], ...]:
    return (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def _view_matrix(camera: Camera3D) -> tuple[tuple[float, ...], ...]:
    forward = _normalize(_subtract(camera.target, camera.eye))
    side = _normalize(_cross(forward, camera.up))
    up = _cross(side, forward)
    return (
        (side.x, side.y, side.z, -_dot(side, camera.eye)),
        (up.x, up.y, up.z, -_dot(up, camera.eye)),
        (-forward.x, -forward.y, -forward.z, _dot(forward, camera.eye)),
        (0.0, 0.0, 0.0, 1.0),
    )


def _projection_matrix(
    projection: Projection3D,
    width: int,
    height: int,
) -> tuple[tuple[float, ...], ...]:
    if isinstance(projection, PerspectiveProjection):
        fov = math.radians(projection.fov_y)
        aspect = projection.aspect or (width / max(1, height))
        f = 1.0 / math.tan(fov / 2.0)
        near = projection.near
        far = projection.far
        return (
            (f / aspect, 0.0, 0.0, 0.0),
            (0.0, f, 0.0, 0.0),
            (0.0, 0.0, (far + near) / (near - far), (2 * far * near) / (near - far)),
            (0.0, 0.0, -1.0, 0.0),
        )
    half_width = projection.width / 2.0
    half_height = projection.height / 2.0
    near = projection.near
    far = projection.far
    return (
        (1.0 / max(1e-6, half_width), 0.0, 0.0, 0.0),
        (0.0, 1.0 / max(1e-6, half_height), 0.0, 0.0),
        (0.0, 0.0, -2.0 / max(1e-6, far - near), -(far + near) / max(1e-6, far - near)),
        (0.0, 0.0, 0.0, 1.0),
    )


def _shader_log(gl: Any, shader: int) -> str:
    length = ctypes.c_int()
    gl.glGetShaderiv(shader, gl.GL_INFO_LOG_LENGTH, ctypes.byref(length))
    if length.value <= 1:
        return "Unknown shader compile failure."
    buffer = ctypes.create_string_buffer(length.value)
    gl.glGetShaderInfoLog(shader, length.value, None, buffer)
    return buffer.value.decode("utf-8", errors="replace").strip()


def _program_log(gl: Any, program: int) -> str:
    length = ctypes.c_int()
    gl.glGetProgramiv(program, gl.GL_INFO_LOG_LENGTH, ctypes.byref(length))
    if length.value <= 1:
        return "Unknown shader link failure."
    buffer = ctypes.create_string_buffer(length.value)
    gl.glGetProgramInfoLog(program, length.value, None, buffer)
    return buffer.value.decode("utf-8", errors="replace").strip()


def _compile_error_message(gl: Any, shader: int, *, backend: str, stage: str, path: object) -> str:
    location = f" path={path!s}" if path is not None else ""
    return (
        f"Shader compilation failed on backend {backend!r} "
        f"for {stage} shader.{location}\n{_shader_log(gl, shader)}"
    )


def _link_error_message(gl: Any, program: int, *, backend: str, shader: Shader3D) -> str:
    locations: list[str] = []
    if shader.vertex_path is not None:
        locations.append(f"vertex={shader.vertex_path!s}")
    if shader.fragment_path is not None:
        locations.append(f"fragment={shader.fragment_path!s}")
    location = f" ({', '.join(locations)})" if locations else ""
    return f"Shader link failed on backend {backend!r}{location}\n{_program_log(gl, program)}"


def _uniform_location(gl: Any, program: int, name: str) -> int:
    return int(gl.glGetUniformLocation(program, name.encode("utf-8")))
