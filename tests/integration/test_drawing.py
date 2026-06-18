from pathlib import Path

import p5


def test_basic_primitives_render_non_empty_canvas(tmp_path: Path):
    output = tmp_path / "sketch.png"

    def setup():
        p5.create_canvas(64, 64)
        p5.background(255)
        p5.stroke(0)
        p5.fill(255, 0, 0)

    def draw():
        p5.rect(5, 5, 20, 15)
        p5.circle(40, 15, 20)
        p5.line(0, 0, 63, 63)
        p5.triangle(10, 50, 20, 30, 30, 50)
        p5.save_canvas(str(output))

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)
    assert output.exists()
    assert context.frame_count == 1
    assert len(set(context.load_pixels())) > 1


def test_custom_shape_and_bezier_render():
    def setup():
        p5.create_canvas(40, 40)
        p5.background(255)
        p5.fill(0, 0, 255)

    def draw():
        p5.begin_shape()
        p5.vertex(5, 5)
        p5.vertex(30, 5)
        p5.quadratic_vertex(35, 20, 20, 30)
        p5.end_shape(p5.CLOSE)
        p5.stroke(255, 0, 0)
        p5.bezier(5, 35, 10, 20, 30, 20, 35, 35)

    context = p5.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixels()
    assert len(pixels) == 40 * 40 * 4
    assert any(channel == 255 for channel in pixels)
