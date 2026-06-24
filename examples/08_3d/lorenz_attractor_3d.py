"""Retained WEBGL Lorenz attractor mesh for the performance examples."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake.drawing.renderer3d import Mesh3D, Model3D, Vec3

WIDTH = 960
HEIGHT = 540
POINT_COUNT = 2_400
WARMUP_STEPS = 180
TUBE_SIDES = 6
STEP = 0.006
OUTPUT = Path("examples/output/09_performance/lorenz_attractor_3d.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

ATTRACTOR: Model3D | None = None


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = vector
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 1e-9:
        return (0.0, 1.0, 0.0)
    return (x / length, y / length, z / length)


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    ax, ay, az = left
    bx, by, bz = right
    return (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)


def _lorenz_points() -> list[tuple[float, float, float]]:
    sigma = 10.0
    rho = 28.0
    beta = 8.0 / 3.0
    x = 0.1
    y = 0.0
    z = 0.0
    points: list[tuple[float, float, float]] = []
    for step_index in range(POINT_COUNT + WARMUP_STEPS):
        dx = sigma * (y - x)
        dy = x * (rho - z) - y
        dz = x * y - beta * z
        x += dx * STEP
        y += dy * STEP
        z += dz * STEP
        if step_index >= WARMUP_STEPS:
            points.append((x * 7.0, (z - 26.0) * 6.0, y * 7.0))
    return points


def _build_attractor_model() -> Model3D:
    points = _lorenz_points()
    vertices: list[Vec3] = []
    normals: list[Vec3] = []
    faces: list[tuple[int, int, int, int]] = []

    for index, point in enumerate(points):
        previous_point = points[max(0, index - 1)]
        next_point = points[min(len(points) - 1, index + 1)]
        tangent = _normalize(
            (
                next_point[0] - previous_point[0],
                next_point[1] - previous_point[1],
                next_point[2] - previous_point[2],
            )
        )
        reference = (0.0, 1.0, 0.0) if abs(tangent[1]) < 0.92 else (1.0, 0.0, 0.0)
        normal = _normalize(_cross(tangent, reference))
        binormal = _normalize(_cross(tangent, normal))
        radius = 0.72 + 0.2 * math.sin(index * 0.037)
        for side in range(TUBE_SIDES):
            angle = math.tau * side / TUBE_SIDES
            nx = math.cos(angle) * normal[0] + math.sin(angle) * binormal[0]
            ny = math.cos(angle) * normal[1] + math.sin(angle) * binormal[1]
            nz = math.cos(angle) * normal[2] + math.sin(angle) * binormal[2]
            vertices.append(
                Vec3(
                    point[0] + nx * radius,
                    point[1] + ny * radius,
                    point[2] + nz * radius,
                )
            )
            normals.append(Vec3(nx, ny, nz))

    for ring in range(len(points) - 1):
        current = ring * TUBE_SIDES
        following = (ring + 1) * TUBE_SIDES
        for side in range(TUBE_SIDES):
            next_side = (side + 1) % TUBE_SIDES
            faces.append(
                (
                    current + side,
                    current + next_side,
                    following + next_side,
                    following + side,
                )
            )

    mesh = Mesh3D(vertices=vertices, faces=faces, normals=normals)
    return gs.create_model(mesh)


@gs.setup
def setup() -> None:
    global ATTRACTOR
    gs.create_canvas(WIDTH, HEIGHT, gs.WEBGL)
    gs.frame_rate(60)
    gs.no_stroke()
    gs.perspective(math.pi / 3.2, WIDTH / HEIGHT, 0.1, 5000)
    gs.describe("A retained WEBGL Lorenz attractor mesh with animated camera and lights.")
    ATTRACTOR = _build_attractor_model()


@gs.draw
def draw() -> None:
    frame = gs.frame_count()
    orbit = frame * 0.018
    eye_x = math.cos(orbit) * 430
    eye_z = math.sin(orbit) * 430

    gs.camera(eye_x, 0, eye_z, 0, 0, 0, 0, 1, 0)
    gs.background(4, 7, 16)
    gs.ambient_light(38)
    gs.directional_light(135, 170, 255, -0.35, -0.65, -1.0)
    gs.point_light(120, 235, 205, math.cos(orbit * 1.7) * 170, -120, 260)

    if ATTRACTOR is not None:
        gs.specular_material(96, 214, 244)
        gs.shininess(42)
        gs.model(ATTRACTOR)

    save_once(ARGS, frame, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
