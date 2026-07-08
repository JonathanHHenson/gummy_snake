"""Temporary ECS perf sketch: Rust ECS 3D simulation with WEBGL drawing.

The simulation runs as a Rust ECS system using 3D spatial neighbors. Drawing uses
normal Python WEBGL APIs through ``gs.fast()`` because ECS canvas currently records
2D draw commands only. The scene renders boxes, spheres, and a retained model.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake import ecs
from gummysnake.drawing.renderer3d import Mesh3D, Model3D, Vec3
from gummysnake.drawing.software3d import box_model, sphere_model

WIDTH = 960
HEIGHT = 540
TARGET_FPS = 60
BODY_COUNT = 1_200
OUTPUT = Path("examples/output/11_temporary_perf_tests/webgl_3d_ecs_primitives_models.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

BODY_TAG = "webgl_body"
WORLD_X = 720.0
WORLD_Y = 420.0
WORLD_Z = 620.0
PERCEPTION_RADIUS = 72.0
MAX_SPEED = 4.8
FPS_LAST_TIME: float | None = None
FPS_VALUE = float(TARGET_FPS)
MODEL_CACHE: Model3D | None = None
SHAPE_CACHE: dict[int, Model3D] = {}

BodyRow = tuple[float, float, float, float, float, float, float, int]

PALETTE = (
    (92, 186, 255, 220),
    (111, 238, 196, 220),
    (255, 214, 108, 220),
    (255, 132, 150, 220),
    (184, 142, 255, 224),
)


@dataclass
class Body3D:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    spin: float
    bucket: int


def _expr_length(x: ecs.Expression, y: ecs.Expression, z: ecs.Expression) -> ecs.Expression:
    return (x * x + y * y + z * z).sqrt()


def _expr_limit_vector(
    x: ecs.Expression, y: ecs.Expression, z: ecs.Expression, maximum: float
) -> tuple[ecs.Expression, ecs.Expression, ecs.Expression]:
    scale = maximum / _expr_length(x, y, z).clamp_min(maximum)
    return x * scale, y * scale, z * scale


def _axis_force(value: ecs.Expression, extent: float) -> ecs.Expression:
    low = -extent * 0.5 + 65.0
    high = extent * 0.5 - 65.0
    return ((value < low) * 0.045) + ((value > high) * -0.045)


@ecs.system_plan(parallel=True, group="simulation")
def simulate_bodies(body: ecs.Query[ecs.Tag[BODY_TAG], Body3D]) -> None:
    state = body[Body3D]
    neighbors = ecs.spatial.neighbors(
        body,
        position=ecs.spatial.point3(state.x, state.y, state.z),
        radius=PERCEPTION_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PERCEPTION_RADIUS, dimensions=3),
        include_self=False,
        allow_fallback=False,
        name="temporary_3d_body_neighbors",
    )
    count = neighbors.count()
    inv_count = 1.0 / count.clamp_min(1)
    has_neighbors = count > 0

    center_x = neighbors.sum(neighbors.item[Body3D].x) * inv_count
    center_y = neighbors.sum(neighbors.item[Body3D].y) * inv_count
    center_z = neighbors.sum(neighbors.item[Body3D].z) * inv_count
    cohesion_x = (center_x - state.x) * 0.0009 * has_neighbors
    cohesion_y = (center_y - state.y) * 0.0009 * has_neighbors
    cohesion_z = (center_z - state.z) * 0.0009 * has_neighbors

    close = neighbors.where(neighbors.distance_sq < 42.0 * 42.0)
    separation_x = close.sum(-close.delta.x / close.distance.clamp_min(1.0)) * 0.018
    separation_y = close.sum(-close.delta.y / close.distance.clamp_min(1.0)) * 0.018
    separation_z = close.sum(-close.delta.z / close.distance.clamp_min(1.0)) * 0.018

    next_vx, next_vy, next_vz = _expr_limit_vector(
        state.vx + cohesion_x + separation_x + _axis_force(state.x, WORLD_X),
        state.vy + cohesion_y + separation_y + _axis_force(state.y, WORLD_Y),
        state.vz + cohesion_z + separation_z + _axis_force(state.z, WORLD_Z),
        MAX_SPEED,
    )
    state.x.set_to(state.x + next_vx)
    state.y.set_to(state.y + next_vy)
    state.z.set_to(state.z + next_vz)
    state.vx.set_to(next_vx)
    state.vy.set_to(next_vy)
    state.vz.set_to(next_vz)
    state.spin.set_to(state.spin + 0.018 + state.bucket * 0.0015)


def _temporary_model() -> Model3D:
    global MODEL_CACHE
    if MODEL_CACHE is not None:
        return MODEL_CACHE
    vertices = (
        Vec3(15.0, 0.0, 0.0),
        Vec3(-9.0, -7.0, -7.0),
        Vec3(-9.0, 7.0, -7.0),
        Vec3(-9.0, 0.0, 9.0),
    )
    normals = (
        Vec3(1.0, 0.0, 0.0),
        Vec3(0.0, -1.0, 0.0),
        Vec3(0.0, 1.0, 0.0),
        Vec3(0.0, 0.0, 1.0),
    )
    faces = ((0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 3, 2))
    MODEL_CACHE = Model3D(meshes=(Mesh3D(vertices=vertices, faces=faces, normals=normals),))
    return MODEL_CACHE


def _shape_for_bucket(bucket: int) -> Model3D:
    cached = SHAPE_CACHE.get(bucket)
    if cached is not None:
        return cached
    if bucket % 3 == 0:
        shape = box_model(12.0 + bucket * 2.0, 8.0 + bucket, 16.0)
    elif bucket % 3 == 1:
        shape = sphere_model(7.5 + bucket, 12, 8)
    else:
        shape = _temporary_model()
    SHAPE_CACHE[bucket] = shape
    return shape


def _seed_bodies() -> None:
    rng = random.Random(5333)
    for index in range(BODY_COUNT):
        angle = rng.random() * math.tau
        pitch = rng.uniform(-0.45, 0.45)
        speed = rng.uniform(1.2, MAX_SPEED)
        gs.add_entity(
            Body3D(
                x=rng.uniform(-WORLD_X * 0.45, WORLD_X * 0.45),
                y=rng.uniform(-WORLD_Y * 0.45, WORLD_Y * 0.45),
                z=rng.uniform(-WORLD_Z * 0.45, WORLD_Z * 0.45),
                vx=math.cos(angle) * math.cos(pitch) * speed,
                vy=math.sin(pitch) * speed,
                vz=math.sin(angle) * math.cos(pitch) * speed,
                spin=rng.random() * math.tau,
                bucket=index % len(PALETTE),
            ),
            tags=[BODY_TAG],
        )


def _body_rows() -> list[BodyRow]:
    rows = gs.iter_component_fields(
        Body3D, "x", "y", "z", "vx", "vy", "vz", "spin", "bucket", tags=[BODY_TAG]
    )
    return cast(list[BodyRow], list(rows))


def _update_fps() -> float:
    global FPS_LAST_TIME, FPS_VALUE
    now = perf_counter()
    if FPS_LAST_TIME is not None:
        elapsed = now - FPS_LAST_TIME
        if elapsed > 0.0:
            FPS_VALUE += (1.0 / elapsed - FPS_VALUE) * 0.12
    FPS_LAST_TIME = now
    return FPS_VALUE


def _draw_scene(draw3d: gs.FastDrawScope, rows: list[BodyRow]) -> None:
    bucketed_rows: list[list[BodyRow]] = [[] for _ in PALETTE]
    for row in rows:
        bucketed_rows[int(row[7])].append(row)
    for bucket, (red, green, blue, alpha) in enumerate(PALETTE):
        shape = _shape_for_bucket(bucket)
        draw3d.specular_material(red, green, blue, alpha)
        draw3d.shininess(24 + bucket * 5)
        for x, y, z, vx, vy, vz, spin, _bucket in bucketed_rows[bucket]:
            with draw3d.pushed():
                draw3d.translate(x, y, z)
                draw3d.rotate_y(spin)
                draw3d.rotate_z(math.atan2(vy, vx))
                if bucket % 3 == 2:
                    draw3d.rotate_y(math.atan2(vz, vx))
                draw3d.model(shape)


def _draw_hud(fps: float) -> None:
    gs.reset_matrix()
    gs.fill(236, 244, 255, 232)
    gs.text_size(15)
    gs.text("WEBGL ECS temporary perf: 3D spatial simulation + primitives + model", 24, 32)
    gs.text(f"fps {fps:5.1f} | bodies {BODY_COUNT:,} | boxes/spheres/model", 24, HEIGHT - 24)


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT, gs.WEBGL)
    gs.frame_rate(TARGET_FPS)
    gs.no_stroke()
    gs.perspective(math.pi / 3.1, WIDTH / HEIGHT, 0.1, 5000)
    gs.describe("Rust ECS 3D spatial simulation drawn with fast WEBGL primitives and models.")
    gs.configure_ecs(strict=False, warn_on_ambiguity=False)
    gs.order(["simulation", "draw"])
    gs.add_system(simulate_bodies)
    _seed_bodies()


@gs.draw
def draw() -> None:
    frame = gs.frame_count()
    fps = _update_fps()
    draw3d = gs.fast()
    gs.background(4, 7, 16)
    draw3d.camera(0, -160, 780, 0, 0, 0, 0, 1, 0)
    draw3d.ambient_light(42)
    draw3d.directional_light(136, 174, 255, -0.35, -0.8, -1.0)
    draw3d.point_light(118, 236, 204, 220, -160, 320)
    _draw_scene(draw3d, _body_rows())
    _draw_hud(fps)
    save_once(ARGS, frame, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
