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


def test_nested_style_contexts_render_distinct_fill_colors():
    def setup():
        gs.create_canvas(36, 12)
        gs.background(255)
        gs.no_stroke()

    def draw():
        with gs.style(stroke=(0, 0, 0)):
            with gs.style(fill=(255, 0, 0)):
                gs.rect(0, 0, 12, 12)
            with gs.style(fill=(0, 255, 0)):
                gs.rect(12, 0, 12, 12)
            with gs.style(fill=(0, 0, 255)):
                gs.rect(24, 0, 12, 12)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixels()

    def pixel_at(x: int, y: int) -> tuple[int, int, int, int]:
        offset = (y * 36 + x) * 4
        return tuple(pixels[offset : offset + 4])  # type: ignore[return-value]

    assert pixel_at(6, 6) == (255, 0, 0, 255)
    assert pixel_at(18, 6) == (0, 255, 0, 255)
    assert pixel_at(30, 6) == (0, 0, 255, 255)


def test_transform_contexts_do_not_reuse_stale_fill_payloads():
    def setup():
        gs.create_canvas(720, 420)
        gs.angle_mode(gs.DEGREES)
        gs.rect_mode(gs.CENTER)
        gs.ellipse_mode(gs.CENTER)

    def draw():
        gs.background(236, 239, 232)
        with gs.style(stroke=(34, 36, 42), stroke_weight=2):
            for row in range(3):
                for col in range(6):
                    with gs.transform(
                        translate=(80 + col * 112, 85 + row * 112),
                        rotate=gs.current.frame_count * 2 + row * 18 + col * 9,
                        scale=(1 + row * 0.12, 1 + col * 0.02),
                    ):
                        gs.fill(230 - row * 34, 105 + col * 18, 88 + row * 44, 210)
                        gs.rect(0, 0, 54, 54)
                        gs.no_fill()
                        gs.circle(0, 0, 76)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixels()

    def pixel_at(x: int, y: int) -> tuple[int, int, int, int]:
        offset = (y * 720 + x) * 4
        return tuple(pixels[offset : offset + 4])  # type: ignore[return-value]

    def blended_fill(row: int, col: int) -> tuple[int, int, int, int]:
        fill = (230 - row * 34, 105 + col * 18, 88 + row * 44)
        background = (236, 239, 232)
        alpha = 210 / 255
        red, green, blue = (
            round(channel * alpha + bg * (1 - alpha))
            for channel, bg in zip(fill, background, strict=True)
        )
        return red, green, blue, 255

    assert pixel_at(0, 0) == (236, 239, 232, 255)
    for row in range(3):
        for col in range(6):
            center = pixel_at(80 + col * 112, 85 + row * 112)
            assert center == blended_fill(row, col)


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
