"""WEBGL lights, materials, primitives, textures, and OBJ model loading."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

ASSETS = Path("examples/assets")
OUTPUT = Path("examples/output/08_3d/webgl_scene.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
TEXTURE = p5.create_image(2, 2)
TEAPOT = None


def preload() -> None:
    global TEAPOT
    TEXTURE.set(0, 0, (255, 70, 70, 255))
    TEXTURE.set(1, 0, (70, 210, 120, 255))
    TEXTURE.set(0, 1, (80, 120, 255, 255))
    TEXTURE.set(1, 1, (250, 220, 70, 255))
    TEAPOT = p5.load_model(ASSETS / "teapot.obj", normalize=True)


def setup() -> None:
    p5.create_canvas(800, 480, p5.WEBGL)
    p5.no_stroke()
    p5.camera(0, -60, 470, 0, 20, 0, 0, 1, 0)
    p5.perspective(math.pi / 3, 800 / 480, 0.1, 4000)


def draw() -> None:
    p5.background(10, 14, 28)
    p5.ambient_light(45)
    p5.directional_light(255, 244, 230, -0.45, -0.7, -1.0)
    p5.point_light(100, 180, 255, 160, -130, 220)

    with p5.pushed():
        p5.translate(-210, 0)
        p5.rotate(p5.frame_count() * 0.035)
        p5.specular_material(240, 150, 90)
        p5.shininess(18)
        p5.box(120)

    with p5.pushed():
        p5.translate(0, 8)
        p5.normal_material()
        p5.sphere(78, 28, 18)

    with p5.pushed():
        p5.translate(215, 24)
        p5.texture(TEXTURE)
        p5.rotate(-0.35)
        p5.plane(135, 135)

    with p5.pushed():
        p5.translate(0, 155)
        p5.ambient_material(44, 62, 92)
        p5.plane(650, 160)

    if TEAPOT is not None:
        with p5.pushed():
            p5.translate(0, -118)
            p5.scale(76)
            p5.specular_material(190, 160, 240)
            p5.model(TEAPOT)

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(preload=preload, setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
