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
        return (
            pixels[offset],
            pixels[offset + 1],
            pixels[offset + 2],
            pixels[offset + 3],
        )

    assert pixel_at(6, 6) == (255, 0, 0, 255)
    assert pixel_at(18, 6) == (0, 255, 0, 255)
    assert pixel_at(30, 6) == (0, 0, 255, 255)


def test_procedural_fill_primitive_batch_renders_non_empty_canvas():
    def setup():
        gs.create_canvas(64, 64)
        gs.background(0)
        gs.no_stroke()
        gs.fill(255, 0, 0, 255)

    def draw():
        for index in range(24):
            x = 8 + (index % 6) * 9
            y = 8 + (index // 6) * 12
            if index % 3 == 0:
                gs.rect(x, y, 5, 7)
            elif index % 3 == 1:
                gs.circle(x + 3, y + 3, 7)
            else:
                gs.triangle(x, y, x + 7, y + 2, x + 2, y + 8)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixel_bytes()
    assert any(pixels[offset] == 255 for offset in range(0, len(pixels), 4))


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
        return (
            pixels[offset],
            pixels[offset + 1],
            pixels[offset + 2],
            pixels[offset + 3],
        )

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
            expected = blended_fill(row, col)
            assert all(
                abs(actual - target) <= 1 for actual, target in zip(center, expected, strict=True)
            ), (center, expected)


def test_text_before_later_primitive_and_centered_text_is_not_clipped():
    background = (248, 245, 238)
    blue = (36, 126, 180)

    def setup():
        gs.create_canvas(720, 360)

    def draw():
        gs.background(*background)
        gs.no_stroke()
        gs.fill(*blue)
        gs.text_size(15)
        gs.text("text_width: 182.8", 44, 210)

        gs.text_align(gs.TextAlign.CENTER, gs.TextAlign.CENTER)
        gs.fill(238)
        gs.rect(485, 120, 170, 82)
        gs.fill(28, 32, 42)
        gs.text("CENTER", 570, 161)
        gs.text_align(gs.LEFT, gs.BASELINE)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixel_bytes()
    width = context.width
    prefix_pixels = []
    for y in range(190, 220):
        for x in range(44, 70):
            offset = (y * width + x) * 4
            red, green, blue_channel, alpha = pixels[offset : offset + 4]
            if blue_channel > red and blue_channel > green and alpha > 0:
                prefix_pixels.append((x, y))

    assert prefix_pixels


def test_custom_shape_and_bezier_render():
    def setup():
        gs.create_canvas(40, 40)
        gs.background(255)
        gs.fill(0, 0, 255)

    def draw():
        gs.begin_shape()
        gs.vertex(5, 5)
        gs.vertex(30, 5)
        gs.vertex(20, 30)
        gs.end_shape(gs.CLOSE)
        gs.no_fill()
        gs.stroke(255, 0, 0)
        gs.bezier(5, 35, 10, 20, 30, 20, 35, 35)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixels()
    assert len(pixels) == 40 * 40 * 4
    assert any(channel == 255 for channel in pixels)


def test_filled_curved_shape_renders_with_gpu_curve_fill():
    def setup():
        gs.create_canvas(40, 40)
        gs.background(255)
        gs.fill(0, 0, 255)
        gs.no_stroke()

    def draw():
        gs.begin_shape()
        gs.vertex(5, 5)
        gs.vertex(30, 5)
        gs.quadratic_vertex(35, 20, 20, 30)
        gs.end_shape(gs.CLOSE)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixel_bytes()
    blue_pixels = [
        pixels[offset : offset + 4]
        for offset in range(0, len(pixels), 4)
        if pixels[offset + 2] > 180 and pixels[offset] < 80 and pixels[offset + 1] < 80
    ]
    assert blue_pixels
    assert context.renderer_performance_counters()["native"]["cpu_fallbacks"] == 0


def test_filled_arc_renders_with_gpu_arc_fill():
    def setup():
        gs.create_canvas(40, 40)
        gs.background(255)
        gs.fill(0, 0, 255)
        gs.no_stroke()

    def draw():
        gs.arc(20, 20, 30, 30, 0.2, 5.3, gs.PIE)

    context = gs.run(setup=setup, draw=draw, headless=True, max_frames=1)
    pixels = context.load_pixel_bytes()
    width = context.width
    center_offset = (20 * width + 20) * 4
    center = pixels[center_offset : center_offset + 4]
    assert center[2] > 180 and center[0] < 80 and center[1] < 80
    assert context.renderer_performance_counters()["native"]["cpu_fallbacks"] == 0
