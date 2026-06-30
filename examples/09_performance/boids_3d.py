"""3D boids flocking performance sketch.

A WEBGL version of Craig Reynolds-style boids: many agents steer using
separation, alignment, and cohesion while flying through a bounded 3D volume.
The simulation state is stored as ECS dataclass components and updated by an ECS
system before each draw call. The system uses generic `ecs.spatial.neighbors`
relations and aggregates for flocking, then each boid is rendered as a reused
Rust-backed 3D model transformed through `gs.fast()`.
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake import ecs
from gummysnake.drawing.renderer3d import Mesh3D, Model3D, Vec3
from gummysnake.ecs.world import EcsWorld

WIDTH = 960
HEIGHT = 540
TARGET_FPS = 60
BOID_COUNT = 2_000
WORLD_X = 760.0
WORLD_Y = 430.0
WORLD_Z = 620.0
PERCEPTION_RADIUS = 72.0
SEPARATION_RADIUS = 32.0
MAX_SPEED = 5.4
MIN_SPEED = 2.0
MAX_FORCE = 0.075
BOUND_MARGIN = 120.0
BOUND_FORCE = 0.045
FPS_SMOOTHING = 0.12
FOV_Y = math.pi / 3.1
CAMERA_ORBIT_RADIUS = 980.0
CAMERA_HEIGHT = -170.0
POINT_LIGHT_POSITION = (230.0, -170.0, 320.0)
BOID_TAG = "Boid"

OUTPUT = Path("examples/output/09_performance/boids_3d.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

fps_last_time: float | None = None
fps_value = float(TARGET_FPS)
_boid_state_cache: list[Any] = []
_boid_buckets: list[list[Any]] = []
_boid_bucket_indices: list[list[int]] = []
_boid_model_cache: Model3D | None = None
BOID_DRAW_FIELDS = ("x", "y", "z", "vx", "vy", "vz")
BOID_STATE_FIELDS = (*BOID_DRAW_FIELDS, "bucket")

palette = [
    (95, 185, 255, 220),
    (105, 238, 192, 215),
    (255, 216, 118, 215),
    (255, 140, 145, 212),
    (185, 145, 255, 218),
]


@dataclass
class BoidState:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    bucket: int


def _mag_expr(x: Any, y: Any, z: Any) -> ecs.Expression:
    return (x * x + y * y + z * z).sqrt()


def _set_magnitude_expr(
    x: Any, y: Any, z: Any, magnitude: Any
) -> tuple[ecs.Expression, ecs.Expression, ecs.Expression]:
    scale = magnitude / _mag_expr(x, y, z).clamp_min(1.0e-9)
    return x * scale, y * scale, z * scale


def _limit_expr(
    x: Any, y: Any, z: Any, maximum: float
) -> tuple[ecs.Expression, ecs.Expression, ecs.Expression]:
    scale = maximum / _mag_expr(x, y, z).clamp_min(maximum)
    return x * scale, y * scale, z * scale


def _steer_toward_expr(
    desired_x: Any,
    desired_y: Any,
    desired_z: Any,
    velocity_x: Any,
    velocity_y: Any,
    velocity_z: Any,
    speed: float = MAX_SPEED,
) -> tuple[ecs.Expression, ecs.Expression, ecs.Expression]:
    target_x, target_y, target_z = _set_magnitude_expr(desired_x, desired_y, desired_z, speed)
    return _limit_expr(
        target_x - velocity_x,
        target_y - velocity_y,
        target_z - velocity_z,
        MAX_FORCE,
    )


@ecs.system
def simulate_boids(boid: ecs.Query[ecs.Tag[BOID_TAG], BoidState]) -> ecs.Action:
    state = boid[BoidState]
    position = ecs.spatial.point3(state.x, state.y, state.z)
    neighbors = ecs.spatial.neighbors(
        boid,
        position=position,
        radius=PERCEPTION_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PERCEPTION_RADIUS, dimensions=3),
        include_self=False,
        allow_fallback=False,
        name="boid_neighbors",
    )
    close = neighbors.where(neighbors.distance_sq < SEPARATION_RADIUS * SEPARATION_RADIUS)

    neighbor_count = neighbors.count()
    inv_neighbors = 1.0 / neighbor_count.clamp_min(1)
    has_neighbors = neighbor_count > 0

    avg_vx = neighbors.sum(neighbors.item[BoidState].vx) * inv_neighbors
    avg_vy = neighbors.sum(neighbors.item[BoidState].vy) * inv_neighbors
    avg_vz = neighbors.sum(neighbors.item[BoidState].vz) * inv_neighbors
    align_x, align_y, align_z = _steer_toward_expr(
        avg_vx, avg_vy, avg_vz, state.vx, state.vy, state.vz
    )

    center_x = neighbors.sum(neighbors.item[BoidState].x) * inv_neighbors
    center_y = neighbors.sum(neighbors.item[BoidState].y) * inv_neighbors
    center_z = neighbors.sum(neighbors.item[BoidState].z) * inv_neighbors
    cohesion_x, cohesion_y, cohesion_z = _steer_toward_expr(
        center_x - state.x,
        center_y - state.y,
        center_z - state.z,
        state.vx,
        state.vy,
        state.vz,
        speed=MAX_SPEED * 0.82,
    )

    close_count = close.count()
    has_close_neighbors = close_count > 0
    separation_x = close.sum(-close.delta.x / close.distance.clamp_min(1.0))
    separation_y = close.sum(-close.delta.y / close.distance.clamp_min(1.0))
    separation_z = close.sum(-close.delta.z / close.distance.clamp_min(1.0))
    separate_x, separate_y, separate_z = _steer_toward_expr(
        separation_x,
        separation_y,
        separation_z,
        state.vx,
        state.vy,
        state.vz,
    )

    bound_x = ((state.x < (-WORLD_X * 0.5 + BOUND_MARGIN)) * BOUND_FORCE) + (
        (state.x > (WORLD_X * 0.5 - BOUND_MARGIN)) * -BOUND_FORCE
    )
    bound_y = ((state.y < (-WORLD_Y * 0.5 + BOUND_MARGIN)) * BOUND_FORCE) + (
        (state.y > (WORLD_Y * 0.5 - BOUND_MARGIN)) * -BOUND_FORCE
    )
    bound_z = ((state.z < (-WORLD_Z * 0.5 + BOUND_MARGIN)) * BOUND_FORCE) + (
        (state.z > (WORLD_Z * 0.5 - BOUND_MARGIN)) * -BOUND_FORCE
    )

    force_x = (
        (align_x + cohesion_x * 0.74) * has_neighbors
        + separate_x * 1.65 * has_close_neighbors
        + bound_x
    )
    force_y = (
        (align_y + cohesion_y * 0.74) * has_neighbors
        + separate_y * 1.65 * has_close_neighbors
        + bound_y
    )
    force_z = (
        (align_z + cohesion_z * 0.74) * has_neighbors
        + separate_z * 1.65 * has_close_neighbors
        + bound_z
    )

    limited_vx, limited_vy, limited_vz = _limit_expr(
        state.vx + force_x,
        state.vy + force_y,
        state.vz + force_z,
        MAX_SPEED,
    )
    speed = _mag_expr(limited_vx, limited_vy, limited_vz)
    min_speed_factor = ((speed < MIN_SPEED) * (MIN_SPEED / speed.clamp_min(1.0e-9))) + (
        (speed >= MIN_SPEED) * 1.0
    )
    next_vx = limited_vx * min_speed_factor
    next_vy = limited_vy * min_speed_factor
    next_vz = limited_vz * min_speed_factor

    return ecs.do_in_parallel(
        ecs.set(state.x, state.x + next_vx),
        ecs.set(state.y, state.y + next_vy),
        ecs.set(state.z, state.z + next_vz),
        ecs.set(state.vx, next_vx),
        ecs.set(state.vy, next_vy),
        ecs.set(state.vz, next_vz),
    )


def _update_fps() -> float:
    global fps_last_time, fps_value
    now = perf_counter()
    if fps_last_time is None:
        fps_last_time = now
        return fps_value
    elapsed = now - fps_last_time
    fps_last_time = now
    if elapsed <= 0.0:
        return fps_value
    fps_value += (1.0 / elapsed - fps_value) * FPS_SMOOTHING
    return fps_value


def _seed_boids() -> list[BoidState]:
    rng = random.Random(20240624)
    states: list[BoidState] = []
    for index in range(BOID_COUNT):
        angle = rng.random() * math.tau
        pitch = rng.uniform(-0.45, 0.45)
        speed = rng.uniform(MIN_SPEED, MAX_SPEED)
        states.append(
            BoidState(
                x=rng.uniform(-WORLD_X * 0.45, WORLD_X * 0.45),
                y=rng.uniform(-WORLD_Y * 0.45, WORLD_Y * 0.45),
                z=rng.uniform(-WORLD_Z * 0.45, WORLD_Z * 0.45),
                vx=math.cos(angle) * math.cos(pitch) * speed,
                vy=math.sin(pitch) * speed,
                vz=math.sin(angle) * math.cos(pitch) * speed,
                bucket=index % len(palette),
            )
        )
    return states


def _prepare_boids() -> None:
    global _boid_buckets, _boid_bucket_indices, _boid_state_cache
    _boid_state_cache = []
    _boid_buckets = [[] for _ in palette]
    _boid_bucket_indices = [[] for _ in palette]
    for state in _seed_boids():
        gs.add_entity(state, tags=[BOID_TAG])
    _boid_state_cache = _boid_states_from_context()
    _boid_buckets = _bucket_states(_boid_state_cache)
    _boid_bucket_indices = _bucket_indices(_boid_state_cache)


def _prepare_boids_world(*, add_system: bool = True) -> EcsWorld:
    global _boid_buckets, _boid_bucket_indices, _boid_state_cache
    world = EcsWorld()
    if add_system:
        world.add_system(simulate_boids)
    for state in _seed_boids():
        world.add_entity(state, tags=[BOID_TAG])
    _boid_state_cache = _boid_states_from_world(world)
    _boid_buckets = _bucket_states(_boid_state_cache)
    _boid_bucket_indices = _bucket_indices(_boid_state_cache)
    return world


def _boid_states_from_world(world: EcsWorld) -> list[tuple[Any, ...]]:
    return list(world.iter_component_fields(BoidState, *BOID_STATE_FIELDS, tags=[BOID_TAG]))


def _boid_states_from_context() -> list[tuple[Any, ...]]:
    return list(gs.iter_component_fields(BoidState, *BOID_STATE_FIELDS, tags=[BOID_TAG]))


def _boid_draw_states_from_context() -> list[tuple[Any, ...]]:
    return list(gs.iter_component_fields(BoidState, *BOID_DRAW_FIELDS, tags=[BOID_TAG]))


def _bucket_states(states: list[tuple[Any, ...]]) -> list[list[tuple[Any, ...]]]:
    buckets: list[list[tuple[Any, ...]]] = [[] for _ in palette]
    for state in states:
        buckets[int(state[6])].append(state)
    return buckets


def _bucket_indices(states: list[tuple[Any, ...]]) -> list[list[int]]:
    buckets: list[list[int]] = [[] for _ in palette]
    for index, state in enumerate(states):
        buckets[int(state[6])].append(index)
    return buckets


def _boid_model() -> Model3D:
    global _boid_model_cache
    if _boid_model_cache is not None:
        return _boid_model_cache
    length = 12.0
    width = 5.0
    height = 4.2
    vertices = (
        Vec3(length, 0.0, 0.0),
        Vec3(-length * 0.55, 0.0, -width),
        Vec3(-length * 0.55, 0.0, width),
        Vec3(0.0, height, 0.0),
    )
    normals = (
        Vec3(1.0, 0.0, 0.0),
        Vec3(0.0, 0.0, 1.0),
        Vec3(0.0, 0.0, -1.0),
        Vec3(0.0, 1.0, 0.0),
    )
    faces = ((0, 1, 3), (0, 3, 2), (0, 2, 1), (1, 2, 3))
    _boid_model_cache = Model3D(meshes=(Mesh3D(vertices=vertices, faces=faces, normals=normals),))
    return _boid_model_cache


def _orientation_quaternion(vx: float, vy: float, vz: float) -> tuple[float, float, float, float]:
    speed = math.sqrt(vx * vx + vy * vy + vz * vz)
    if speed <= 1.0e-12:
        return (1.0, 0.0, 0.0, 0.0)
    tx = vx / speed
    ty = vy / speed
    tz = vz / speed
    dot = tx
    if dot > 0.999_999:
        return (1.0, 0.0, 0.0, 0.0)
    if dot < -0.999_999:
        return (0.0, 0.0, 1.0, 0.0)
    # Quaternion from +X to target direction: (1 + dot, cross(+X, target)).
    w = 1.0 + dot
    x = 0.0
    y = -tz
    z = ty
    inv_length = 1.0 / math.sqrt(w * w + y * y + z * z)
    return (w * inv_length, x, y * inv_length, z * inv_length)


def _model_matrix_from_translation_quaternion(
    x: float, y: float, z: float, quaternion: tuple[float, float, float, float]
) -> tuple[float, ...]:
    w, qx, qy, qz = quaternion
    xx = qx * qx
    yy = qy * qy
    zz = qz * qz
    xy = qx * qy
    xz = qx * qz
    yz = qy * qz
    wx = w * qx
    wy = w * qy
    wz = w * qz
    return (
        1.0 - 2.0 * (yy + zz),
        2.0 * (xy + wz),
        2.0 * (xz - wy),
        0.0,
        2.0 * (xy - wz),
        1.0 - 2.0 * (xx + zz),
        2.0 * (yz + wx),
        0.0,
        2.0 * (xz + wy),
        2.0 * (yz - wx),
        1.0 - 2.0 * (xx + yy),
        0.0,
        x,
        y,
        z,
        1.0,
    )


def _boid_transform_keys(states: list[tuple[Any, ...]]) -> list[tuple[float, ...]]:
    transforms = []
    for state in states:
        x, y, z, vx, vy, vz = state[:6]
        transforms.append(
            _model_matrix_from_translation_quaternion(
                x,
                y,
                z,
                _orientation_quaternion(vx, vy, vz),
            )
        )
    return transforms


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT, gs.WEBGL)
    gs.frame_rate(TARGET_FPS)
    gs.no_stroke()
    gs.perspective(FOV_Y, WIDTH / HEIGHT, 0.1, 5000)
    gs.describe(
        "A 3D boids flocking simulation using an ECS system and fast WEBGL model transforms."
    )
    gs.configure_ecs(strict=False, warn_on_ambiguity=False)
    gs.add_system(simulate_boids, order=10)
    _prepare_boids()


@gs.draw
def draw() -> None:
    frame = gs.frame_count()
    fps = _update_fps()
    orbit = frame * 0.008
    eye_x = math.sin(orbit) * CAMERA_ORBIT_RADIUS
    eye_y = CAMERA_HEIGHT
    eye_z = math.cos(orbit) * CAMERA_ORBIT_RADIUS

    draw3d = gs.fast()
    draw3d.camera(eye_x, eye_y, eye_z, 0, 0, 0, 0, 1, 0)
    gs.background(5, 8, 18)
    draw3d.ambient_light(44)
    draw3d.directional_light(135, 172, 255, -0.35, -0.75, -1.0)
    draw3d.point_light(120, 238, 205, *POINT_LIGHT_POSITION)

    boid_rows = _boid_draw_states_from_context()

    model = _boid_model()
    for bucket, bucket_indices in enumerate(_boid_bucket_indices):
        draw3d.specular_material(*palette[bucket])
        draw3d.shininess(28)
        for index in bucket_indices:
            x, y, z, vx, vy, vz = boid_rows[index]
            quaternion = _orientation_quaternion(vx, vy, vz)
            with draw3d.pushed():
                draw3d.translate(x, y, z)
                draw3d.rotate_quaternion(*quaternion)
                draw3d.model(model)

    gs.reset_matrix()
    gs.fill(238, 244, 255, 235)
    gs.text_size(15)
    gs.text(f"ECS 3D boids | {BOID_COUNT:,} agents | separation + alignment + cohesion", 24, 32)
    gs.text(
        f"fps {fps:5.1f} | ECS spatial relation aggregates + fast model transforms", 24, HEIGHT - 24
    )
    save_once(ARGS, frame, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
