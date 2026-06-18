"""WEBGL primitives, materials, camera, and projection gallery.

Headless/export:
    uv run python examples/webgl_primitives_gallery.py --headless --frames 1

Interactive:
    uv run python examples/webgl_primitives_gallery.py --interactive
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import p5

OUTPUT = Path("examples/output/webgl_primitives_gallery.png")
HEADLESS = None
EXPORT_CANVAS = False
PROJECTION = "perspective"


def setup() -> None:
    p5.create_canvas(900, 540, p5.WEBGL)
    p5.create_camera(0, -70, 520, 0, 20, 0, 0, 1, 0)
    p5.no_stroke()
    p5.frame_rate(30)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)


def configure_projection() -> None:
    aspect = 900 / 540
    if PROJECTION == "ortho":
        p5.ortho(900, 540, 0.1, 4000)
    else:
        p5.perspective(math.pi / 3, aspect, 0.1, 4000)


def configure_camera() -> None:
    if HEADLESS is not False:
        orbit = p5.frame_count() * 0.045
        p5.camera(
            math.sin(orbit) * 420.0,
            -90.0,
            math.cos(orbit) * 420.0,
            0.0,
            20.0,
            0.0,
            0.0,
            1.0,
            0.0,
        )
    else:
        p5.orbit_control(1.0, 1.0, 1.2)


def draw_ground() -> None:
    p5.push()
    p5.translate(0, 110)
    p5.ambient_material(48, 74, 108)
    p5.plane(620, 620)
    p5.pop()


def draw_box() -> None:
    p5.push()
    p5.translate(-180, -10)
    p5.rotate(p5.frame_count() * 0.04)
    p5.specular_material(250, 146, 92)
    p5.shininess(18)
    p5.box(120, 120, 120)
    p5.pop()


def draw_sphere() -> None:
    p5.push()
    p5.translate(180, -8)
    p5.rotate(-p5.frame_count() * 0.03)
    p5.normal_material()
    p5.sphere(82, 28, 20)
    p5.pop()


def draw() -> None:
    configure_projection()
    configure_camera()

    p5.background(10, 14, 28)
    p5.ambient_light(44)
    p5.directional_light(255, 244, 236, -0.5, -0.7, -1.0)
    p5.point_light(110, 180, 255, 180, -120, 220)

    draw_ground()
    draw_box()
    draw_sphere()

    if EXPORT_CANVAS and p5.frame_count() == 0:
        p5.save_canvas(str(OUTPUT))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=1)
    parser.add_argument(
        "--projection",
        choices=("perspective", "ortho"),
        default="perspective",
        help="Projection mode for the gallery scene.",
    )
    args = parser.parse_args()

    global HEADLESS, EXPORT_CANVAS, PROJECTION
    HEADLESS = args.headless
    EXPORT_CANVAS = args.headless is not False or args.frames is not None
    PROJECTION = args.projection
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
