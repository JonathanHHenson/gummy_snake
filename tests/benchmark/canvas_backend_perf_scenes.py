from __future__ import annotations

import math

import gummysnake as gs

sprites = []
churn_pixels = b""
shots = []
asteroids = []

def _sprite(width, height, seed):
    pixels = bytearray(width * height * 4)
    cx = (width - 1) / 2
    cy = (height - 1) / 2
    radius = min(width, height) / 2
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 4
            distance = math.hypot(x - cx, y - cy)
            if distance > radius:
                pixels[offset : offset + 4] = b"\x00\x00\x00\x00"
                continue
            pixels[offset] = (seed * 41 + x * 5) % 256
            pixels[offset + 1] = (seed * 67 + y * 7) % 256
            pixels[offset + 2] = 160 + (x + y + seed) % 80
            pixels[offset + 3] = 255
    return gs.Image(width, height, bytes(pixels))


def _reset_asteroids():
    global shots, asteroids
    shots = [
        [360.0, 240.0, math.cos(index * 0.62) * 8.5, math.sin(index * 0.62) * 8.5, index]
        for index in range(14)
    ]
    asteroids = [
        [
            60.0 + (index * 101) % 610,
            50.0 + (index * 71) % 380,
            math.cos(index * 1.7) * (0.8 + index % 3 * 0.22),
            math.sin(index * 1.7) * (0.8 + index % 3 * 0.22),
            24.0 + (index % 4) * 9.0,
            index * 0.37,
        ]
        for index in range(18)
    ]


def _draw_starfield(count):
    gs.no_stroke()
    for index in range(count):
        x = (index * 97 + gs.frame_count() * (index % 4 + 1)) % 720
        y = (index * 53 + index * index) % 480
        alpha = 110 + (index % 4) * 35
        gs.fill(190, 220, 255, alpha)
        gs.circle(x, y, 1 + index % 3)


def _draw_primitives(count):
    for index in range(count):
        x = 90 + (index * 83) % 520
        y = 80 + (index * 59) % 280
        with gs.pushed():
            gs.translate(x, y)
            gs.rotate(index * 0.18 + gs.frame_count() * 0.01)
            gs.no_fill()
            gs.stroke(180, 190, 210)
            gs.stroke_weight(2.5)
            gs.ellipse(-18, -14, 52, 64)
            gs.stroke(170, 225, 255, 255)
            gs.fill(36, 116, 220, 245)
            gs.triangle(0, -24, -20, 20, 0, 6)
            gs.triangle(0, -24, 0, 6, 20, 20)


def _draw_laser_field(count):
    gs.no_fill()
    gs.stroke(100, 200, 255, 240)
    gs.stroke_weight(3)
    for index in range(count):
        sx = 80 + (index * 41) % 560
        sy = 60 + (index * 67) % 360
        with gs.pushed():
            gs.translate(sx, sy)
            gs.rotate(math.pi / 4 + index * 0.1)
            gs.line(0, -18, 0, 18)


def _draw_image_field(*, mutate):
    global churn_pixels
    gs.image_mode(gs.CENTER)
    for index in range(96):
        image = sprites[index % len(sprites)]
        if mutate and index == 0:
            image.update_pixels(churn_pixels)
        x = 34 + (index * 61 + gs.frame_count() * 3) % 660
        y = 34 + (index * 43 + index * index) % 410
        size = 20 + index % 5 * 5
        with gs.pushed():
            gs.translate(x, y)
            gs.rotate(index * 0.13 + gs.frame_count() * 0.012)
            gs.image(image, 0, 0, size, size)


def _draw_mixed_text_pixels():
    gs.background(11, 18, 28)
    _draw_starfield(24)
    _draw_primitives(8)
    _draw_image_field(mutate=False)
    pixels = gs.load_pixels()
    for offset in range(0, min(len(pixels), 1024), 16):
        pixels[offset] = (pixels[offset] + 3) % 256
        pixels[offset + 1] = (pixels[offset + 1] + 7) % 256
    gs.update_pixels(pixels)
    gs.fill(240)
    gs.no_stroke()
    gs.text_size(16)
    for index in range(18):
        gs.text_width(f"score {index} frame {gs.frame_count()}")
        gs.text(f"score {index * 125}", 28, 36 + index * 22)


def _draw_blend_modes():
    modes = [gs.BLEND, gs.ADD, gs.MULTIPLY, gs.SCREEN, gs.DIFFERENCE, gs.EXCLUSION]
    gs.no_stroke()
    for index in range(72):
        gs.blend_mode(modes[index % len(modes)])
        gs.fill(50 + index % 120, 120 + index % 80, 220, 180)
        x = 30 + (index * 53 + gs.frame_count() * 2) % 660
        y = 30 + (index * 47 + index * index) % 420
        gs.circle(x, y, 28 + index % 4 * 6)
    gs.blend_mode(gs.BLEND)


def _draw_erasing():
    gs.no_stroke()
    gs.fill(80, 150, 240, 230)
    for index in range(80):
        x = 28 + (index * 41) % 670
        y = 32 + (index * 67) % 410
        gs.circle(x, y, 30)
    gs.erase()
    gs.fill(255)
    for index in range(34):
        x = 30 + (index * 71 + gs.frame_count() * 3) % 660
        y = 30 + (index * 43) % 410
        gs.rect(x, y, 26, 18)
    gs.no_erase()


def _draw_transformed_images():
    gs.image_mode(gs.CENTER)
    for index in range(96):
        image = sprites[index % len(sprites)]
        x = 34 + (index * 61 + gs.frame_count() * 3) % 660
        y = 34 + (index * 43 + index * index) % 410
        with gs.pushed():
            gs.translate(x, y)
            gs.rotate(index * 0.17 + gs.frame_count() * 0.014)
            gs.scale(0.7 + (index % 5) * 0.18)
            gs.image(image, 0, 0, 34, 34)


def _draw_text_only():
    gs.fill(235)
    gs.no_stroke()
    gs.text_size(15)
    for index in range(80):
        gs.text_width(f"label {index % 12}")
        gs.text(f"label {index}", 24 + (index % 5) * 136, 28 + (index // 5) * 27)


def _draw_pixel_readback_upload():
    _draw_starfield(24)
    pixels = gs.load_pixel_bytes()
    gs.update_pixels(memoryview(pixels))


def _draw_asteroids_scene():
    gs.image_mode(gs.CENTER)
    gs.background(7, 10, 22)
    _draw_starfield(96)
    for shot in shots:
        shot[0] = (shot[0] + shot[2]) % 720
        shot[1] = (shot[1] + shot[3]) % 480
        gs.stroke(120, 220, 255)
        gs.stroke_weight(3)
        gs.line(shot[0], shot[1], shot[0] - shot[2] * 2.2, shot[1] - shot[3] * 2.2)
    for asteroid in asteroids:
        asteroid[0] = (asteroid[0] + asteroid[2]) % 720
        asteroid[1] = (asteroid[1] + asteroid[3]) % 480
        asteroid[5] += 0.025
        with gs.pushed():
            gs.translate(asteroid[0], asteroid[1])
            gs.rotate(asteroid[5])
            gs.image(
                sprites[int(asteroid[4]) % len(sprites)],
                0,
                0,
                asteroid[4] * 2,
                asteroid[4] * 2,
            )
            gs.no_fill()
            gs.stroke(190, 200, 220, 170)
            gs.stroke_weight(2)
            gs.circle(0, 0, asteroid[4] * 2.2)
    with gs.pushed():
        gs.translate(360, 240)
        gs.rotate(-math.pi / 2 + math.sin(gs.frame_count() * 0.04) * 0.7)
        gs.image(sprites[0], 0, 0, 88, 64)
        gs.stroke(90, 180, 255)
        gs.line(0, 0, 56, 0)
    gs.fill(245)
    gs.no_stroke()
    gs.text_size(18)
    gs.text(f"wave 4   shots {len(shots)}   rocks {len(asteroids)}", 24, 34)


def _draw_webgl_3d():
    gs.background(10, 14, 28)
    gs.ambient_light(45)
    gs.directional_light(255, 244, 230, -0.45, -0.7, -1.0)
    gs.point_light(100, 180, 255, 160, -130, 220)

    with gs.pushed():
        gs.translate(-185, 0)
        gs.rotate(gs.frame_count() * 0.035)
        gs.specular_material(240, 150, 90)
        gs.shininess(18)
        gs.box(120)

    with gs.pushed():
        gs.translate(25, 8)
        gs.normal_material()
        gs.sphere(78, 28, 18)

    with gs.pushed():
        gs.translate(225, 24)
        gs.texture(sprites[0])
        gs.rotate(-0.35)
        gs.plane(135, 135)

    with gs.pushed():
        gs.translate(0, 155)
        gs.ambient_material(44, 62, 92)
        gs.plane(650, 160)


def setup_scene(variant: str) -> None:
    global sprites, churn_pixels
    renderer = gs.WEBGL if variant == "webgl_3d" else gs.P2D
    gs.create_canvas(720, 480, renderer)
    gs.frame_rate(10_000)
    if variant == "webgl_3d":
        gs.no_stroke()
        gs.camera(0, -60, 470, 0, 20, 0, 0, 1, 0)
        gs.perspective(math.pi / 3, 720 / 480, 0.1, 4000)
    sprites = [_sprite(48, 48, seed) for seed in range(5)]
    churn_pixels = _sprite(48, 48, 99).to_rgba_bytes()
    if variant == "cached_images_nearest":
        gs.no_smooth()
    _reset_asteroids()


def draw_scene(variant: str) -> None:
    gs.background(8, 13, 32)
    if variant == "dense_primitives":
        _draw_starfield(72)
        _draw_primitives(28)
        _draw_laser_field(16)
    elif variant == "sparse_primitives":
        _draw_starfield(12)
        _draw_primitives(6)
        _draw_laser_field(4)
    elif variant == "cached_images" or variant == "cached_images_nearest":
        _draw_image_field(mutate=False)
    elif variant == "image_upload_churn":
        _draw_image_field(mutate=True)
    elif variant == "blend_modes":
        _draw_blend_modes()
    elif variant == "erasing":
        _draw_erasing()
    elif variant == "transformed_images":
        _draw_transformed_images()
    elif variant == "text_only":
        _draw_text_only()
    elif variant == "pixel_readback_upload":
        _draw_pixel_readback_upload()
    elif variant == "mixed_text_pixels":
        _draw_mixed_text_pixels()
    elif variant == "asteroids_scene":
        _draw_asteroids_scene()
    elif variant == "webgl_3d":
        _draw_webgl_3d()
    else:
        raise ValueError(f"unknown benchmark variant: {variant}")
