"""WEBGPU-style 3D cameras, projections, lights, materials, textures, and geometry."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

ASSETS = Path("examples/assets")
OUTPUT = Path("examples/output/08_3d/advanced_webgpu_geometry.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

TEXTURE = gs.create_image(4, 4)
ENVIRONMENT = gs.create_image(8, 4)
GEOMETRY = None
STL_MODEL = None
SCREEN_POINT = (0.0, 0.0, 0.0)
WORLD_POINT = None


def preload() -> None:
    global STL_MODEL
    colors = (
        (255, 90, 90, 255),
        (90, 210, 255, 255),
        (255, 220, 90, 255),
        (100, 255, 150, 255),
    )
    for y in range(TEXTURE.height):
        for x in range(TEXTURE.width):
            TEXTURE.set(x, y, colors[(x + y) % len(colors)])

    for y in range(ENVIRONMENT.height):
        for x in range(ENVIRONMENT.width):
            t = x / max(1, ENVIRONMENT.width - 1)
            ENVIRONMENT.set(x, y, (30 + int(80 * t), 55 + int(120 * t), 120 + int(80 * t), 255))

    STL_MODEL = gs.load_model(ASSETS / "triangle.stl", normalize=True)


def _geometry_callback() -> None:
    gs.normal(0, 0, 1)
    gs.vertex_property("example", "built geometry with flipped UVs")
    gs.torus(74, 22, 32, 12)


def setup() -> None:
    global GEOMETRY
    gs.create_canvas(820, 500, gs.WEBGPU)
    gs.no_stroke()
    gs.set_camera(gs.create_camera(0, -80, 520, 0, 0, 0, 0, 1, 0))
    gs.frustum(-0.09, 0.09, -0.055, 0.055, 0.1, 3_000)
    gs.texture_mode(gs.NORMALIZED)
    gs.texture_wrap(gs.REPEAT, gs.MIRROR)

    built = gs.build_geometry(_geometry_callback)
    GEOMETRY = gs.flip_u(gs.flip_v(built))

    temporary = gs.build_geometry(lambda: gs.box(12))
    gs.free_geometry(temporary)


def draw() -> None:
    global SCREEN_POINT, WORLD_POINT
    frame = gs.frame_count()
    gs.background(8, 11, 22)
    gs.set_camera(gs.create_camera(0, -90, 540, 0, 0, 0, 0, 1, 0))
    gs.roll(math.sin(frame * 0.03) * 0.08)
    gs.frustum(-0.09, 0.09, -0.055, 0.055, 0.1, 3_000)

    gs.no_lights()
    gs.lights()
    gs.light_falloff(1.0, 0.002, 0.00001)
    gs.spot_light(255, 230, 170, 0, -260, 420, 0, 0, -1, math.pi / 5, 0.9)
    gs.image_light(ENVIRONMENT, 0.35)
    gs.panorama(ENVIRONMENT)

    with gs.pushed():
        gs.translate(-250, -20)
        gs.texture_mode(gs.NORMALIZED)
        gs.texture_wrap(gs.REPEAT, gs.MIRROR)
        gs.texture(TEXTURE)
        gs.plane(150, 150)

    if GEOMETRY is not None:
        with gs.pushed():
            gs.translate(0, 0)
            gs.specular_color(255, 244, 205)
            gs.specular_material(95, 165, 255)
            gs.shininess(36)
            gs.metalness(0.72)
            gs.model(GEOMETRY)

    with gs.pushed():
        gs.translate(250, 2)
        gs.emissive_material(255, 80, 150)
        gs.metalness(0.0)
        gs.sphere(58, 24, 16)

    if STL_MODEL is not None:
        with gs.pushed():
            gs.translate(0, 158)
            gs.scale(72)
            gs.ambient_material(110, 240, 170)
            gs.model(STL_MODEL)

    SCREEN_POINT = gs.world_to_screen(0, 0, 0)
    WORLD_POINT = gs.screen_to_world(*SCREEN_POINT)

    gs.no_lights()
    gs.no_stroke()
    gs.fill(245)
    gs.text_size(19)
    gs.text("Advanced WEBGPU-style 3D APIs", 24, 34)
    gs.text_size(13)
    gs.text("set_camera + roll + frustum projection", 24, 58)
    gs.text("lights(), spot_light(), image_light(), panorama(), light_falloff()", 24, 78)
    gs.text(
        "texture_mode(NORMALIZED), texture_wrap(REPEAT, MIRROR), build_geometry(), flip_u/v()",
        24,
        98,
    )
    gs.text(
        "load_model() reads STL assets; specular/emissive/metalness materials vary per model",
        24,
        118,
    )
    gs.fill(255, 210, 90)
    gs.circle(SCREEN_POINT[0], SCREEN_POINT[1], 9)
    if WORLD_POINT is not None:
        gs.fill(220)
        screen_summary = (
            f"origin -> screen ({SCREEN_POINT[0]:.1f}, {SCREEN_POINT[1]:.1f}, "
            f"depth {SCREEN_POINT[2]:.3f})"
        )
        world_summary = f" -> world ({WORLD_POINT.x:.1f}, {WORLD_POINT.y:.1f}, {WORLD_POINT.z:.1f})"
        gs.text(screen_summary + world_summary, 24, 474)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(preload=preload, setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
