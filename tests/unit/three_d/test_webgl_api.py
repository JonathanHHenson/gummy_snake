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


def test_camera_projection_helpers_round_trip_screen_coordinates():
    context = make_context()
    camera = context.create_camera()
    moved = camera.move(10, 0, 0).look_at(10, 0, 0)

    assert context.set_camera(moved) is moved
    rolled = context.roll(0.1)
    assert rolled.up != moved.up

    projection = context.frustum(-1, 1, -1, 1, 1, 100)
    assert projection.near == 1
    screen_x, screen_y, depth = context.world_to_screen(10, 0, 450)
    world = context.screen_to_world(screen_x, screen_y, depth)

    assert screen_x == pytest.approx(context.width / 2)
    assert screen_y == pytest.approx(context.height / 2)
    assert world.x == pytest.approx(10)
    assert world.z == pytest.approx(450)


def test_webgpu_renderer_mode_is_accepted_for_canvas_and_3d_apis():
    sketch = _WebGLSketch()
    backend = FakeCanvas3DBackend()
    context = SketchContext(sketch, backend, plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context

    context.create_canvas(32, 32, renderer=gs.WEBGPU)
    context.lights()
    context.model(Model3D(meshes=()))

    assert context.state.canvas.renderer == gs.WEBGPU
    assert any(name == "draw_model" for name, _value in backend.renderer.calls)


def test_light_state_is_restored_by_push_pop():
    context = make_context()

    context.ambient_light(20)
    outer_lights = list(context._lights3d)
    context.push()
    context.point_light(255, 1, 2, 3)
    assert len(context._lights3d) == 2

    context.pop()

    assert context._lights3d == outer_lights


def test_lights_materials_and_texture_modes_update_3d_state():
    context = make_context()
    image = gs.create_image(2, 2)

    context.lights()
    assert len(context._lights3d) == 2
    context.no_lights()
    assert context._lights3d == []
    context.light_falloff(1, 0.5, 0.25)
    context.spot_light(255, 1, 2, 3, 0, 0, -1, 0.5, 2)
    context.image_light(image, intensity=0.25)
    assert context._lights3d[-1].intensity == 0.25
    assert context.panorama(image) is image

    context.specular_color(255, 0, 0)
    context.emissive_material(0, 255, 0)
    context.metalness(0.75)
    context.texture_mode(gs.IMAGE)
    context.texture_wrap(gs.REPEAT, gs.MIRROR)
    context.texture(image)

    material = context._effective_3d_material()
    assert material.metalness == pytest.approx(0.75)
    assert material.texture is not None
    assert material.texture.coordinate_mode == gs.IMAGE
    assert material.texture.wrap_x == gs.REPEAT
    assert material.texture.wrap_y == gs.MIRROR


def test_build_geometry_and_uv_helpers_capture_primitive_models():
    context = make_context()

    model = context.build_geometry(lambda: context.box(10))
    assert isinstance(model, Model3D)
    assert model.meshes

    flipped = context.flip_u(model)
    assert isinstance(flipped, Model3D)
    context.normal(0, 1, 0)
    context.vertex_property("weight", 0.5)
    assert context._current_3d_normal == (0.0, 1.0, 0.0)
    assert context._current_vertex_properties["weight"] == 0.5
    context.free_geometry(model)
    assert model.meshes


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
