import math
from pathlib import Path

import p5
from p5.rust.canvas import is_canvas_available


def test_webgl_box_renders_non_empty_headless_canvas():
    def setup():
        p5.create_canvas(96, 96, p5.WEBGL)
        p5.background(12, 16, 28)
        p5.no_stroke()
        p5.camera(0, 0, 180, 0, 0, 0, 0, 1, 0)
        p5.ambient_material(120, 200, 255)

    def draw():
        p5.ambient_light(40)
        p5.directional_light(255, 255, 255, -0.4, -0.7, -1.0)
        p5.box(70)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)

    pixels = context.load_pixels()
    assert any(value > 0 for value in pixels)


def test_webgl_textured_plane_renders_expected_quadrant_colors():
    texture = p5.create_image(2, 2)
    texture.set(0, 0, p5.Color(255, 0, 0, 255))
    texture.set(1, 0, p5.Color(0, 255, 0, 255))
    texture.set(0, 1, p5.Color(0, 0, 255, 255))
    texture.set(1, 1, p5.Color(255, 255, 0, 255))

    def setup():
        p5.create_canvas(64, 64, p5.WEBGL)
        p5.background(0)
        p5.no_stroke()
        p5.ortho(64, 64, 0.1, 1000)
        p5.texture(texture)

    def draw():
        p5.plane(48, 48)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)

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
    teapot = p5.load_model(Path("examples/assets/teapot.obj"), normalize=True)

    def setup():
        p5.create_canvas(128, 128, p5.WEBGL)
        p5.background(8, 10, 18)
        p5.stroke(24, 28, 44)
        p5.camera(0, 0, 4, 0, 0, 0, 0, 1, 0)
        p5.perspective(math.pi / 3, 1.0, 0.1, 100)
        p5.specular_material(220, 170, 255)
        p5.shininess(8)

    def draw():
        p5.ambient_light(50)
        p5.directional_light(255, 220, 210, -0.3, -0.7, -1.0)
        p5.model(teapot)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)

    pixels = context.load_pixels()
    assert any(value > 0 for value in pixels)


def test_canvas_webgl_box_renders_non_empty_canvas():
    if not is_canvas_available():
        return

    def setup():
        p5.create_canvas(96, 96, p5.WEBGL)
        p5.background(12, 16, 28)
        p5.no_stroke()
        p5.camera(0, 0, 180, 0, 0, 0, 0, 1, 0)
        p5.ambient_material(120, 200, 255)

    def draw():
        p5.ambient_light(40)
        p5.directional_light(255, 255, 255, -0.4, -0.7, -1.0)
        p5.box(70)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)

    pixels = context.load_pixels()
    assert any(value > 0 for value in pixels)


def test_canvas_webgl_shader_binding_and_uniforms_are_accepted():
    if not is_canvas_available():
        return

    program = p5.create_shader(
        "void main() { gl_Position = gl_Vertex; }",
        "void main() { gl_FragColor = vec4(1.0); }",
    )

    def setup():
        p5.create_canvas(96, 96, p5.WEBGL)
        p5.background(0)
        p5.no_stroke()
        p5.camera(0, 0, 180, 0, 0, 0, 0, 1, 0)
        p5.shader(program)
        program.set_uniform("u_time", 1.25)

    def draw():
        p5.ambient_material(255, 180, 80)
        p5.box(60)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)

    assert context._shader3d is program
    assert program.uniforms["u_time"] == 1.25
    assert any(value > 0 for value in context.load_pixels())
