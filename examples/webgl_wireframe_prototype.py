"""Wireframe cube demo using the epic 100 math-only 3D prototype.

This example does not use a native 3D renderer yet. Instead it projects a cube with
`prototype3d.py` and draws the resulting wireframe with the existing 2D API.

Interactive:
    uv run python examples/webgl_wireframe_prototype.py

Headless/export:
    uv run python examples/webgl_wireframe_prototype.py --backend headless --frames 1
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import p5_py as p5
from p5_py.drawing.prototype3d import cube_model, wireframe_segments
from p5_py.drawing.renderer3d import Camera3D, OrthographicProjection, PerspectiveProjection, Vec3

OUTPUT = Path("examples/output/webgl_wireframe_prototype.png")
EXPORT_CANVAS = False
CUBE = cube_model(150)


def setup() -> None:
    p5.create_canvas(820, 420)
    p5.frame_rate(30)
    p5.rect_mode(p5.CORNER)
    p5.text_size(14)


def draw() -> None:
    p5.background(10, 14, 26)
    orbit = p5.frame_count() * 0.04

    left_camera = Camera3D(
        eye=Vec3(math.sin(orbit) * 140, math.sin(orbit * 0.6) * 60, 320),
        target=Vec3(0, 0, 0),
        up=Vec3(0, 1, 0),
    )
    right_camera = Camera3D(
        eye=Vec3(120, -40, 320),
        target=Vec3(0, 0, 0),
        up=Vec3(0, 1, 0),
    )

    draw_panel(
        x=20,
        y=54,
        width=360,
        height=320,
        title="PerspectiveProjection",
        subtitle="camera orbits the cube",
        camera=left_camera,
        projection=PerspectiveProjection(fov_y=58, near=1, far=1000),
        stroke_color=(110, 230, 255),
    )
    draw_panel(
        x=440,
        y=54,
        width=360,
        height=320,
        title="OrthographicProjection",
        subtitle="same mesh, flattened depth",
        camera=right_camera,
        projection=OrthographicProjection(width=320, height=320, near=1, far=1000),
        stroke_color=(255, 193, 94),
    )

    draw_header(orbit)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT))


def draw_panel(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    subtitle: str,
    camera: Camera3D,
    projection: PerspectiveProjection | OrthographicProjection,
    stroke_color: tuple[int, int, int],
) -> None:
    p5.no_stroke()
    p5.fill(255, 255, 255, 14)
    p5.rect(x, y, width, height)

    p5.fill(255, 255, 255, 220)
    p5.text(title, x + 18, y - 18)
    p5.fill(190, 202, 235, 190)
    p5.text(subtitle, x + 18, y)

    segments = wireframe_segments(
        CUBE,
        camera,
        projection,
        viewport_width=width,
        viewport_height=height,
    )

    p5.no_fill()
    p5.stroke(*stroke_color)
    p5.stroke_weight(2)
    for segment in segments:
        p5.line(x + segment.start[0], y + segment.start[1], x + segment.end[0], y + segment.end[1])

    p5.no_stroke()
    p5.fill(255, 255, 255, 120)
    p5.circle(x + width / 2, y + height / 2, 5)


def draw_header(orbit: float) -> None:
    p5.no_stroke()
    p5.fill(255, 255, 255, 235)
    p5.text_size(20)
    p5.text("Epic 100: math-only WEBGL-like prototype", 22, 28)
    p5.text_size(13)
    p5.fill(175, 188, 220, 220)
    p5.text(
        "`prototype3d.py` projects 3D wireframes into logical 2D coordinates so "
        "camera and projection",
        22,
        395,
    )
    p5.text(
        f"semantics can be tested before a native renderer exists. orbit={orbit:.2f} rad",
        22,
        412,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="pyglet", choices=p5.available_backends())
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    global EXPORT_CANVAS
    EXPORT_CANVAS = args.backend in {p5.HEADLESS, p5.PILLOW}
    p5.run(setup=setup, draw=draw, backend=args.backend, max_frames=args.frames)


if __name__ == "__main__":
    main()
