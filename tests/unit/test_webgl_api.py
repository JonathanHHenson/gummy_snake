import math
from pathlib import Path
from typing import Any, cast

import pytest

import gummysnake as gs
from gummysnake.backend.canvas import CanvasBackend
from gummysnake.context import SketchContext
from gummysnake.core.input_events import MouseEvent
from gummysnake.drawing.renderer3d import Model3D, Shader3D
from gummysnake.exceptions import (
    ArgumentValidationError,
    BackendCapabilityError,
    ShaderUniformError,
)
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from tests.helpers.webgl import (
    FakeCanvas3DBackend,
    FakeUpgradeableCanvasBackend,
    _camera_radius,
    _WebGLSketch,
    make_context,
)


def test_canvas_backend_reports_software_webgl_separately_from_native_acceleration():
    backend = CanvasBackend(headless=True)

    assert backend.capabilities.three_d is True
    assert backend.capabilities.software_three_d is True
    assert backend.capabilities.native_three_d is False
    assert backend.capabilities.shaders is True
    assert backend.capabilities.native_shaders is False


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


def test_shader_object_helpers_copy_and_modify():
    shader = Shader3D(
        vertex_source="#version 300 es\nin vec3 position;\nvoid main() {}",
        fragment_source="uniform vec4 color;\nvoid main() {}",
    )
    shader.set_uniform("color", (1.0, 0.0, 0.0, 1.0))

    assert shader.version() == "glsl-es-300"
    assert shader.inspect_hooks() == {
        "vertex": True,
        "fragment": True,
        "uniforms": True,
        "attributes": True,
    }

    copied = shader.copy_to_context()
    copied.set_uniform("color", (0.0, 1.0, 0.0, 1.0))
    assert shader.uniforms["color"] == (1.0, 0.0, 0.0, 1.0)
    assert copied.uniforms["color"] == (0.0, 1.0, 0.0, 1.0)

    modified = shader.modify(fragment_source="void main() {}", uniforms={"time": 1.5})
    assert modified.fragment_source == "void main() {}"
    assert modified.uniforms["time"] == 1.5


def test_texture_requires_gummy_snake_image_and_material_apis_clear_bound_texture():
    context = make_context()

    with pytest.raises(ArgumentValidationError, match="Gummy Snake Image"):
        context.texture(cast(Any, object()))

    checker = gs.create_image(2, 2)
    context.texture(checker)
    assert context._effective_3d_material().texture is not None

    context.ambient_material(255)
    assert context._effective_3d_material().texture is None


def test_load_shader_and_create_shader_round_trip(tmp_path: Path):
    vertex_path = tmp_path / "basic.vert"
    fragment_path = tmp_path / "basic.frag"
    vertex_path.write_text("void main() { gl_Position = gl_Vertex; }", encoding="utf-8")
    fragment_path.write_text("void main() { gl_FragColor = vec4(1.0); }", encoding="utf-8")

    loaded = gs.load_shader(vertex_path, fragment_path)
    created = gs.create_shader(
        "void main() { gl_Position = gl_Vertex; }", "void main() { gl_FragColor = vec4(1.0); }"
    )

    assert loaded.vertex_path == vertex_path
    assert loaded.fragment_path == fragment_path
    assert "gl_Position" in loaded.vertex_source
    assert isinstance(created, Shader3D)


def test_shader_requires_backend_shader_capability_on_canvas_context():
    context = make_context()
    program = gs.create_shader(
        "void main() { gl_Position = gl_Vertex; }", "void main() { gl_FragColor = vec4(1.0); }"
    )

    with pytest.raises(BackendCapabilityError, match="does not support shader"):
        context.shader(program)


def test_set_shader_uniform_requires_active_shader():
    context = make_context()

    with pytest.raises(ShaderUniformError, match="without an active shader"):
        context.set_shader_uniform("u_time", 1.0)


def test_shader_can_upgrade_canvas_backend_from_software_webgl_to_native_shader_path():
    sketch = _WebGLSketch()
    backend = FakeUpgradeableCanvasBackend()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    context.create_canvas(96, 96, renderer=gs.WEBGL)
    program = gs.create_shader("void main() { gl_Position = vec4(0.0); }", "void main() { }")

    context.shader(program)

    assert backend.enable_calls == 1
    assert context.renderer is backend.renderer


def test_native_canvas_renderer_path_receives_camera_projection_shader_and_model_calls():
    sketch = _WebGLSketch()
    backend = FakeCanvas3DBackend()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    context.create_canvas(96, 96, renderer=gs.WEBGL)
    program = gs.create_shader(
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
