from pathlib import Path

import gummysnake as gs


def test_basic_primitives_render_non_empty_canvas(tmp_path: Path):
    output = tmp_path / "sketch.png"

    def setup():
        gs.create_canvas(64, 64)
        gs.background(255)
        gs.stroke(0)
        gs.fill(255, 0, 0)

    def draw():
        gs.rect(5, 5, 20, 15)
        gs.circle(40, 15, 20)
        gs.line(0, 0, 63, 63)
        gs.triangle(10, 50, 20, 30, 30, 50)
        gs.save_canvas(str(output))

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    assert output.exists()
    assert context.frame_count == 1
    assert len(set(context.load_pixels())) > 1


def test_custom_shape_and_bezier_render():
    def setup():
        gs.create_canvas(40, 40)
        gs.background(255)
        gs.fill(0, 0, 255)

    def draw():
        gs.begin_shape()
        gs.vertex(5, 5)
        gs.vertex(30, 5)
        gs.quadratic_vertex(35, 20, 20, 30)
        gs.end_shape(gs.CLOSE)
        gs.stroke(255, 0, 0)
        gs.bezier(5, 35, 10, 20, 30, 20, 35, 35)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixels()
    assert len(pixels) == 40 * 40 * 4
    assert any(channel == 255 for channel in pixels)
