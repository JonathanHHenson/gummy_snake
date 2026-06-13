import math
from pathlib import Path
from typing import Any, cast

import pytest

import p5_py as p5
from p5_py.backends.base import BackendCapabilities
from p5_py.backends.headless import HeadlessBackend
from p5_py.context import SketchContext
from p5_py.drawing.renderer3d import Model3D, Shader3D
from p5_py.events.input_state import MouseEvent
from p5_py.exceptions import ArgumentValidationError, BackendCapabilityError, ShaderUniformError
from p5_py.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from p5_py.sketch import Sketch


class _WebGLSketch(Sketch):
    def __init__(self):
        super().__init__(backend="headless")


def make_context() -> SketchContext:
    sketch = _WebGLSketch()
    context = SketchContext(sketch, HeadlessBackend(), plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    context.create_canvas(96, 96, renderer=p5.WEBGL)
    return context


def _camera_radius(context: SketchContext) -> float:
    offset_x = context._camera3d.eye.x - context._camera3d.target.x
    offset_y = context._camera3d.eye.y - context._camera3d.target.y
    offset_z = context._camera3d.eye.z - context._camera3d.target.z
    return math.sqrt(offset_x * offset_x + offset_y * offset_y + offset_z * offset_z)


def test_orbit_control_rotates_camera_from_accumulated_mouse_drag():
    context = make_context()
    initial_eye = context._camera3d.eye
    initial_radius = _camera_radius(context)

    context.dispatch_mouse_event(MouseEvent(x=8, y=8, button="left", type="mouse_pressed"))
    context.dispatch_mouse_event(
        MouseEvent(x=18, y=2, dx=10, dy=-6, button="left", type="mouse_dragged")
    )

    camera = context.orbit_control()

    assert camera.eye != initial_eye
    assert _camera_radius(context) == pytest.approx(initial_radius)

    camera_after_second_call = context.orbit_control()
    assert camera_after_second_call.eye.x == pytest.approx(camera.eye.x)
    assert camera_after_second_call.eye.y == pytest.approx(camera.eye.y)
    assert camera_after_second_call.eye.z == pytest.approx(camera.eye.z)


def test_orbit_control_applies_mouse_wheel_zoom():
    context = make_context()
    initial_radius = _camera_radius(context)

    context.dispatch_mouse_event(MouseEvent(x=0, y=0, scroll_y=2.0, type="mouse_wheel"))
    context.orbit_control()

    assert _camera_radius(context) < initial_radius


class Fake3DRenderer:
    three_d = True
    width = 96
    height = 96
    physical_width = 96
    physical_height = 96
    pixel_density = 1.0

    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def resize(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        self.width = width
        self.height = height
        self.physical_width = width
        self.physical_height = height
        self.pixel_density = pixel_density

    def begin_frame(self) -> None: ...
    def end_frame(self) -> None: ...
    def background(self, color) -> None: ...
    def clear(self) -> None: ...
    def point(self, x, y, style, transform) -> None: ...
    def line(self, x1, y1, x2, y2, style, transform) -> None: ...
    def polygon(self, points, style, transform, *, close=True) -> None: ...
    def ellipse(self, x, y, width, height, style, transform) -> None: ...
    def arc(self, x, y, width, height, start, stop, mode, style, transform) -> None: ...
    def draw_image(self, image, dx, dy, dw, dh, style, transform, *, source=None) -> None: ...
    def text(self, value, x, y, style, transform) -> None: ...
    def text_width(self, value, style) -> float:
        return 0.0

    def text_ascent(self, style) -> float:
        return 0.0

    def text_descent(self, style) -> float:
        return 0.0

    def load_pixels(self) -> list[int]:
        return [0] * (self.physical_width * self.physical_height * 4)

    def update_pixels(self, pixels) -> None: ...
    def blend_region(self, source_image, source, destination, mode) -> None: ...
    def save(self, path) -> None: ...
    def set_camera(self, camera) -> None:
        self.calls.append(("camera", camera))

    def set_projection(self, projection) -> None:
        self.calls.append(("projection", projection))

    def set_lights(self, lights) -> None:
        self.calls.append(("lights", tuple(lights)))

    def set_material(self, material) -> None:
        self.calls.append(("material", material))

    def set_texture(self, texture) -> None:
        self.calls.append(("texture", texture))

    def use_shader(self, shader) -> None:
        self.calls.append(("shader", shader))

    def set_shader_uniform(self, name, value) -> None:
        self.calls.append((f"uniform:{name}", value))

    def draw_model(self, model, transform=None) -> None:
        self.calls.append(("draw_model", model))

    def draw_mesh(self, mesh, transform=None) -> None:
        self.calls.append(("draw_mesh", mesh))

    def plane(self, width, height) -> None: ...
    def box(self, width, height, depth) -> None: ...
    def sphere(self, radius, detail_x=24, detail_y=16) -> None: ...


class FakePyglet3DBackend:
    name = p5.PYGLET
    capabilities = BackendCapabilities(three_d=True, shaders=True)

    def __init__(self):
        self.renderer = Fake3DRenderer()

    def create_canvas(
        self, width: int, height: int, pixel_density: float | None = None, *, renderer: str = p5.P2D
    ) -> None:
        self.renderer.resize(width, height, 1.0 if pixel_density is None else pixel_density)

    def resize_canvas(
        self, width: int, height: int, pixel_density: float | None = None, *, renderer: str = p5.P2D
    ) -> None:
        self.create_canvas(width, height, pixel_density, renderer=renderer)

    def display_density(self) -> float:
        return 1.0

    def run(self, sketch, *, max_frames: int | None = None) -> None: ...
    def stop(self) -> None: ...
    def present(self) -> None: ...


class FakeUpgradeablePygletBackend(FakePyglet3DBackend):
    def __init__(self):
        super().__init__()
        self.capabilities = BackendCapabilities(three_d=True, shaders=False)
        self.enable_calls = 0

    def enable_native_webgl(self) -> bool:
        self.enable_calls += 1
        self.capabilities = BackendCapabilities(three_d=True, shaders=True)
        self.renderer = Fake3DRenderer()
        return True


def test_texture_requires_p5_image_and_material_apis_clear_bound_texture():
    context = make_context()

    with pytest.raises(ArgumentValidationError, match="p5_py Image"):
        context.texture(cast(Any, object()))

    checker = p5.create_image(2, 2)
    context.texture(checker)
    assert context._effective_3d_material().texture is not None

    context.ambient_material(255)
    assert context._effective_3d_material().texture is None


def test_load_shader_and_create_shader_round_trip(tmp_path: Path):
    vertex_path = tmp_path / "basic.vert"
    fragment_path = tmp_path / "basic.frag"
    vertex_path.write_text("void main() { gl_Position = gl_Vertex; }", encoding="utf-8")
    fragment_path.write_text("void main() { gl_FragColor = vec4(1.0); }", encoding="utf-8")

    loaded = p5.load_shader(vertex_path, fragment_path)
    created = p5.create_shader(
        "void main() { gl_Position = gl_Vertex; }", "void main() { gl_FragColor = vec4(1.0); }"
    )

    assert loaded.vertex_path == vertex_path
    assert loaded.fragment_path == fragment_path
    assert "gl_Position" in loaded.vertex_source
    assert isinstance(created, Shader3D)


def test_shader_requires_backend_shader_capability_on_headless_context():
    context = make_context()
    program = p5.create_shader(
        "void main() { gl_Position = gl_Vertex; }", "void main() { gl_FragColor = vec4(1.0); }"
    )

    with pytest.raises(BackendCapabilityError, match="does not support shader"):
        context.shader(program)


def test_set_shader_uniform_requires_active_shader():
    context = make_context()

    with pytest.raises(ShaderUniformError, match="without an active shader"):
        context.set_shader_uniform("u_time", 1.0)


def test_shader_can_upgrade_pyglet_backend_from_software_webgl_to_native_shader_path():
    sketch = _WebGLSketch()
    backend = FakeUpgradeablePygletBackend()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    context.create_canvas(96, 96, renderer=p5.WEBGL)
    program = p5.create_shader("void main() { gl_Position = vec4(0.0); }", "void main() { }")

    context.shader(program)

    assert backend.enable_calls == 1
    assert context.renderer is backend.renderer


def test_native_pyglet_renderer_path_receives_camera_projection_shader_and_model_calls():
    sketch = _WebGLSketch()
    backend = FakePyglet3DBackend()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    context.create_canvas(96, 96, renderer=p5.WEBGL)
    program = p5.create_shader(
        "void main() { gl_Position = gl_Vertex; }", "void main() { gl_FragColor = vec4(1.0); }"
    )
    context.shader(program)
    context.set_shader_uniform("u_time", 1.25)
    context.camera(0, 0, 180, 0, 0, 0, 0, 1, 0)
    context.perspective(math.pi / 3, 1.0, 0.1, 100.0)
    context.model(Model3D(meshes=()))

    call_names = [name for name, _value in backend.renderer.calls]
    assert "camera" in call_names
    assert "projection" in call_names
    assert "material" in call_names
    assert "shader" in call_names
    assert "draw_model" in call_names
    shader_calls = [value for name, value in backend.renderer.calls if name == "shader"]
    assert shader_calls[-1] is program
    assert program.uniforms["u_time"] == 1.25
