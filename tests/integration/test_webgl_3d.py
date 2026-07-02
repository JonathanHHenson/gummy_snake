import math
from pathlib import Path

import gummysnake as gs


def test_webgl_box_renders_non_empty_headless_canvas():
    def setup():
        gs.create_canvas(96, 96, gs.WEBGL)
        gs.background(12, 16, 28)
        gs.no_stroke()
        gs.camera(0, 0, 180, 0, 0, 0, 0, 1, 0)
        gs.ambient_material(120, 200, 255)

    def draw():
        gs.ambient_light(40)
        gs.directional_light(255, 255, 255, -0.4, -0.7, -1.0)
        gs.box(70)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)

    pixels = context.load_pixels()
    assert any(value > 0 for value in pixels)


def test_webgl_textured_plane_renders_expected_quadrant_colors():
    texture = gs.create_image(2, 2)
    texture.set(0, 0, gs.Color(255, 0, 0, 255))
    texture.set(1, 0, gs.Color(0, 255, 0, 255))
    texture.set(0, 1, gs.Color(0, 0, 255, 255))
    texture.set(1, 1, gs.Color(255, 255, 0, 255))

    def setup():
        gs.create_canvas(64, 64, gs.WEBGL)
        gs.background(0)
        gs.no_stroke()
        gs.ortho(64, 64, 0.1, 1000)
        gs.texture(texture)

    def draw():
        gs.plane(48, 48)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)

    pixels = context.load_pixels()

    def sample_rgb(x: int, y: int) -> tuple[int, int, int]:
        index = (y * 64 + x) * 4
        return (pixels[index], pixels[index + 1], pixels[index + 2])

    top_left = sample_rgb(20, 20)
    top_right = sample_rgb(44, 20)
    bottom_left = sample_rgb(20, 44)
    bottom_right = sample_rgb(44, 44)

    assert top_left[0] > 180 and top_left[1] < 100 and top_left[2] < 100
    assert top_right[1] > 180 and top_right[0] < 100 and top_right[2] < 100
    assert bottom_left[2] > 180 and bottom_left[0] < 100 and bottom_left[1] < 100
    assert bottom_right[0] > 180 and bottom_right[1] > 180 and bottom_right[2] < 100


def test_webgl_obj_model_renders_from_example_asset():
    teapot = gs.load_model(Path("examples/assets/teapot.obj"), normalize=True)

    def setup():
        gs.create_canvas(128, 128, gs.WEBGL)
        gs.background(8, 10, 18)
        gs.no_stroke()
        gs.camera(0, 0, 4, 0, 0, 0, 0, 1, 0)
        gs.perspective(math.pi / 3, 1.0, 0.1, 100)
        gs.specular_material(220, 170, 255)
        gs.shininess(8)

    def draw():
        gs.ambient_light(50)
        gs.directional_light(255, 220, 210, -0.3, -0.7, -1.0)
        gs.model(teapot)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)

    pixels = context.load_pixels()
    assert any(value > 0 for value in pixels)


def test_webgl_obj_model_transform_is_applied_before_projection():
    teapot = gs.load_model(Path("examples/assets/teapot.obj"), normalize=True)

    def setup():
        gs.create_canvas(128, 128, gs.WEBGL)
        gs.background(0)
        gs.no_stroke()
        gs.camera(0, -60, 470, 0, 20, 0, 0, 1, 0)
        gs.perspective(math.pi / 3, 1.0, 0.1, 4000)
        gs.specular_material(190, 160, 240)

    def draw():
        gs.ambient_light(45)
        gs.directional_light(255, 244, 230, -0.45, -0.7, -1.0)
        gs.translate(0, -30)
        gs.scale(70)
        gs.model(teapot)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)

    pixels = context.load_pixels()
    occupied = []
    for y in range(128):
        for x in range(128):
            index = (y * 128 + x) * 4
            if pixels[index : index + 3] != [0, 0, 0]:
                occupied.append((x, y))

    assert occupied
    assert max(x for x, _ in occupied) - min(x for x, _ in occupied) >= 24
    assert max(y for _, y in occupied) - min(y for _, y in occupied) >= 12


def test_canvas_webgl_box_renders_non_empty_canvas():
    def setup():
        gs.create_canvas(96, 96, gs.WEBGL)
        gs.background(12, 16, 28)
        gs.no_stroke()
        gs.camera(0, 0, 180, 0, 0, 0, 0, 1, 0)
        gs.ambient_material(120, 200, 255)

    def draw():
        gs.ambient_light(40)
        gs.directional_light(255, 255, 255, -0.4, -0.7, -1.0)
        gs.box(70)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)

    pixels = context.load_pixels()
    assert any(value > 0 for value in pixels)


def test_canvas_webgl_shader_binding_and_uniforms_are_accepted():
    program = gs.create_shader(
        "void main() { gl_Position = gl_Vertex; }",
        "void main() { gl_FragColor = vec4(1.0); }",
    )

    def setup():
        gs.create_canvas(96, 96, gs.WEBGL)
        gs.background(0)
        gs.no_stroke()
        gs.camera(0, 0, 180, 0, 0, 0, 0, 1, 0)
        gs.shader(program)
        program.set_uniform("u_time", 1.25)

    def draw():
        gs.ambient_material(255, 180, 80)
        gs.box(60)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)

    assert context._shader3d is program
    assert program.uniforms["u_time"] == 1.25
    assert any(value > 0 for value in context.load_pixels())
