"""WEBGL lights, materials, primitives, textures, and OBJ model loading."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

ASSETS = Path("examples/assets")
OUTPUT = Path("examples/output/08_3d/webgl_scene.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
TEXTURE = gs.create_image(2, 2)
TEAPOT = None


def preload() -> None:
    global TEAPOT
    TEXTURE.set(0, 0, (255, 70, 70, 255))
    TEXTURE.set(1, 0, (70, 210, 120, 255))
    TEXTURE.set(0, 1, (80, 120, 255, 255))
    TEXTURE.set(1, 1, (250, 220, 70, 255))
    TEAPOT = gs.load_model(ASSETS / "teapot.obj", normalize=True)


def setup() -> None:
    gs.create_canvas(800, 480, gs.WEBGL)
    gs.no_stroke()
    gs.camera(0, -60, 470, 0, 20, 0, 0, 1, 0)
    gs.perspective(math.pi / 3, 800 / 480, 0.1, 4000)


def draw() -> None:
    gs.background(10, 14, 28)
    gs.ambient_light(45)
    gs.directional_light(255, 244, 230, -0.45, -0.7, -1.0)
    gs.point_light(100, 180, 255, 160, -130, 220)

    with gs.pushed():
        gs.translate(-210, 0)
        gs.rotate(gs.frame_count() * 0.035)
        gs.specular_material(240, 150, 90)
        gs.shininess(18)
        gs.box(120)

    with gs.pushed():
        gs.translate(0, 8)
        gs.normal_material()
        gs.sphere(78, 28, 18)

    with gs.pushed():
        gs.translate(215, 24)
        gs.texture(TEXTURE)
        gs.rotate(-0.35)
        gs.plane(135, 135)

    with gs.pushed():
        gs.translate(0, 155)
        gs.ambient_material(44, 62, 92)
        gs.plane(650, 160)

    if TEAPOT is not None:
        with gs.pushed():
            gs.translate(0, -118)
            gs.scale(76)
            gs.specular_material(190, 160, 240)
            gs.model(TEAPOT)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(preload=preload, setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
