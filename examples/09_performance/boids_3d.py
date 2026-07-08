"""3D boids flocking performance sketch.

A WEBGL version of Craig Reynolds-style boids: many agents steer using
separation, alignment, and cohesion while flying through a bounded 3D volume.
The simulation state is stored as ECS dataclass components and updated by an ECS
system before each draw call. The system uses generic ``ecs.spatial.neighbors``
relations and aggregates for flocking, then each boid is rendered as a reused
Rust-backed 3D model transformed through ``gs.fast()``.
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

# -----------------------------------------------------------------------------
# Sketch and scene configuration

WIDTH = 960
HEIGHT = 540
TARGET_FPS = 60
OUTPUT = Path("examples/output/09_performance/boids_3d.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

FOV_Y = math.pi / 3.1
CAMERA_DISTANCE = 800.0
CAMERA_HEIGHT = -170.0
POINT_LIGHT_POSITION = (230.0, -170.0, 320.0)
FPS_SMOOTHING = 0.12

# -----------------------------------------------------------------------------
# Boid simulation tuning

BOID_COUNT = 6_000
BOID_TAG = "Boid"

WORLD_X = 760.0
WORLD_Y = 430.0
WORLD_Z = 620.0
BOUND_MARGIN = 120.0
BOUND_FORCE = 0.045

PERCEPTION_RADIUS = 60.0
SEPARATION_RADIUS = 40.0
MAX_SPEED = 5.4
MIN_SPEED = 2.0
MAX_FORCE = 0.075
ALIGNMENT_WEIGHT = 1.0
COHESION_WEIGHT = 0.7
SEPARATION_WEIGHT = 1.7
COHESION_SPEED_FACTOR = 0.82

# -----------------------------------------------------------------------------
# Rendering constants and cached runtime state

PALETTE = [
    (95, 185, 255, 220),
    (105, 238, 192, 215),
    (255, 216, 118, 215),
    (255, 140, 145, 212),
    (185, 145, 255, 218),
]
BOID_MODEL_LENGTH = 12.0
BOID_MODEL_WIDTH = 5.0
BOID_MODEL_HEIGHT = 4.2
BOID_DRAW_FIELDS = ("x", "y", "z", "vx", "vy", "vz")
BOID_STATE_FIELDS = (*BOID_DRAW_FIELDS, "bucket")

Quaternion = tuple[float, float, float, float]
BoidDrawRow = tuple[float, float, float, float, float, float]
BoidStateRow = tuple[float, float, float, float, float, float, int]
PlanVector3 = tuple[ecs.Expression, ecs.Expression, ecs.Expression]

fps_last_time: float | None = None
fps_value = float(TARGET_FPS)
_boid_bucket_indices: list[list[int]] = [[] for _ in PALETTE]
_boid_model_cache: Model3D | None = None


# -----------------------------------------------------------------------------
# ECS component and system plan


@dataclass
class BoidState:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    bucket: int


def _expr_length(x: ecs.Expression, y: ecs.Expression, z: ecs.Expression) -> ecs.Expression:
    """Length expression for ECS vector components."""
    return (x * x + y * y + z * z).sqrt()


def _expr_set_magnitude(
    x: ecs.Expression, y: ecs.Expression, z: ecs.Expression, magnitude: float
) -> PlanVector3:
    scale = magnitude / _expr_length(x, y, z).clamp_min(1.0e-9)
    return x * scale, y * scale, z * scale


def _expr_limit_vector(
    x: ecs.Expression, y: ecs.Expression, z: ecs.Expression, maximum: float
) -> PlanVector3:
    scale = maximum / _expr_length(x, y, z).clamp_min(maximum)
    return x * scale, y * scale, z * scale


def _expr_steer_toward(
    desired_x: ecs.Expression,
    desired_y: ecs.Expression,
    desired_z: ecs.Expression,
    velocity_x: ecs.Expression,
    velocity_y: ecs.Expression,
    velocity_z: ecs.Expression,
    *,
    speed: float = MAX_SPEED,
) -> PlanVector3:
    target_x, target_y, target_z = _expr_set_magnitude(desired_x, desired_y, desired_z, speed)
    return _expr_limit_vector(
        target_x - velocity_x,
        target_y - velocity_y,
        target_z - velocity_z,
        MAX_FORCE,
    )


def _boid_neighbors(
    boid: ecs.Query, state: ecs.ComponentExpressionProxy
) -> ecs.spatial.SpatialRelation:
    return ecs.spatial.neighbors(
        boid,
        position=ecs.spatial.point3(state.x, state.y, state.z),
        radius=PERCEPTION_RADIUS,
        algorithm=ecs.spatial.HashGrid(cell_size=PERCEPTION_RADIUS, dimensions=3),
        include_self=False,
        allow_fallback=False,
        name="boid_neighbors",
    )


def _alignment_and_cohesion(
    state: ecs.ComponentExpressionProxy, neighbors: ecs.spatial.SpatialRelation
) -> PlanVector3:
    neighbor_count = neighbors.count()
    inv_neighbors = 1.0 / neighbor_count.clamp_min(1)
    has_neighbors = neighbor_count > 0

    avg_vx = neighbors.sum(neighbors.item[BoidState].vx) * inv_neighbors
    avg_vy = neighbors.sum(neighbors.item[BoidState].vy) * inv_neighbors
    avg_vz = neighbors.sum(neighbors.item[BoidState].vz) * inv_neighbors
    align_x, align_y, align_z = _expr_steer_toward(
        avg_vx, avg_vy, avg_vz, state.vx, state.vy, state.vz
    )

    center_x = neighbors.sum(neighbors.item[BoidState].x) * inv_neighbors
    center_y = neighbors.sum(neighbors.item[BoidState].y) * inv_neighbors
    center_z = neighbors.sum(neighbors.item[BoidState].z) * inv_neighbors
    cohesion_x, cohesion_y, cohesion_z = _expr_steer_toward(
        center_x - state.x,
        center_y - state.y,
        center_z - state.z,
        state.vx,
        state.vy,
        state.vz,
        speed=MAX_SPEED * COHESION_SPEED_FACTOR,
    )

    return (
        (align_x * ALIGNMENT_WEIGHT + cohesion_x * COHESION_WEIGHT) * has_neighbors,
        (align_y * ALIGNMENT_WEIGHT + cohesion_y * COHESION_WEIGHT) * has_neighbors,
        (align_z * ALIGNMENT_WEIGHT + cohesion_z * COHESION_WEIGHT) * has_neighbors,
    )


def _separation_force(
    state: ecs.ComponentExpressionProxy, neighbors: ecs.spatial.SpatialRelation
) -> PlanVector3:
    close = neighbors.where(neighbors.distance_sq < SEPARATION_RADIUS * SEPARATION_RADIUS)
    close_count = close.count()
    has_close_neighbors = close_count > 0

    separation_x = close.sum(-close.delta.x / close.distance.clamp_min(1.0))
    separation_y = close.sum(-close.delta.y / close.distance.clamp_min(1.0))
    separation_z = close.sum(-close.delta.z / close.distance.clamp_min(1.0))
    separate_x, separate_y, separate_z = _expr_steer_toward(
        separation_x,
        separation_y,
        separation_z,
        state.vx,
        state.vy,
        state.vz,
    )
    return (
        separate_x * SEPARATION_WEIGHT * has_close_neighbors,
        separate_y * SEPARATION_WEIGHT * has_close_neighbors,
        separate_z * SEPARATION_WEIGHT * has_close_neighbors,
    )


def _axis_boundary_force(value: ecs.Expression, extent: float) -> ecs.Expression:
    low = -extent * 0.5 + BOUND_MARGIN
    high = extent * 0.5 - BOUND_MARGIN
    return ((value < low) * BOUND_FORCE) + ((value > high) * -BOUND_FORCE)


def _boundary_force(state: ecs.ComponentExpressionProxy) -> PlanVector3:
    return (
        _axis_boundary_force(state.x, WORLD_X),
        _axis_boundary_force(state.y, WORLD_Y),
        _axis_boundary_force(state.z, WORLD_Z),
    )


def _apply_speed_floor(x: ecs.Expression, y: ecs.Expression, z: ecs.Expression) -> PlanVector3:
    speed = _expr_length(x, y, z)
    min_speed_factor = ((speed < MIN_SPEED) * (MIN_SPEED / speed.clamp_min(1.0e-9))) + (
        (speed >= MIN_SPEED) * 1.0
    )
    return x * min_speed_factor, y * min_speed_factor, z * min_speed_factor


@ecs.system(parallel=True)
def simulate_boids(boid: ecs.Query[ecs.Tag[BOID_TAG], BoidState]) -> None:
    state = boid[BoidState]
    neighbors = _boid_neighbors(boid, state)

    flock_x, flock_y, flock_z = _alignment_and_cohesion(state, neighbors)
    separate_x, separate_y, separate_z = _separation_force(state, neighbors)
    bound_x, bound_y, bound_z = _boundary_force(state)

    force_x = flock_x + separate_x + bound_x
    force_y = flock_y + separate_y + bound_y
    force_z = flock_z + separate_z + bound_z

    limited_vx, limited_vy, limited_vz = _expr_limit_vector(
        state.vx + force_x,
        state.vy + force_y,
        state.vz + force_z,
        MAX_SPEED,
    )
    next_vx, next_vy, next_vz = _apply_speed_floor(limited_vx, limited_vy, limited_vz)

    state.x.set_to(state.x + next_vx)
    state.y.set_to(state.y + next_vy)
    state.z.set_to(state.z + next_vz)
    state.vx.set_to(next_vx)
    state.vy.set_to(next_vy)
    state.vz.set_to(next_vz)


# -----------------------------------------------------------------------------
# Boid setup helpers


def _seed_boids() -> list[BoidState]:
    rng = random.Random(20240624)
    states: list[BoidState] = []
    for index in range(BOID_COUNT):
        angle = rng.random() * math.tau
        pitch = rng.uniform(-0.45, 0.45)
        speed = rng.uniform(MIN_SPEED, MAX_SPEED)
        vx = math.cos(angle) * math.cos(pitch) * speed
        vy = math.sin(pitch) * speed
        vz = math.sin(angle) * math.cos(pitch) * speed
        states.append(
            BoidState(
                x=rng.uniform(-WORLD_X * 0.45, WORLD_X * 0.45),
                y=rng.uniform(-WORLD_Y * 0.45, WORLD_Y * 0.45),
                z=rng.uniform(-WORLD_Z * 0.45, WORLD_Z * 0.45),
                vx=vx,
                vy=vy,
                vz=vz,
                bucket=index % len(PALETTE),
            )
        )
    return states


def _prepare_boids() -> None:
    global _boid_bucket_indices
    for state in _seed_boids():
        gs.add_entity(state, tags=[BOID_TAG])
    _boid_bucket_indices = _bucket_indices(_boid_states_from_context())


def _boid_states_from_context() -> list[BoidStateRow]:
    rows = gs.iter_component_fields(BoidState, *BOID_STATE_FIELDS, tags=[BOID_TAG])
    return cast(list[BoidStateRow], list(rows))


def _boid_draw_states_from_context() -> list[BoidDrawRow]:
    rows = gs.iter_component_fields(BoidState, *BOID_DRAW_FIELDS, tags=[BOID_TAG])
    return cast(list[BoidDrawRow], list(rows))


def _bucket_indices(states: list[BoidStateRow]) -> list[list[int]]:
    buckets: list[list[int]] = [[] for _ in PALETTE]
    for index, state in enumerate(states):
        buckets[int(state[6])].append(index)
    return buckets


# -----------------------------------------------------------------------------
# Model and transform helpers


def _boid_model() -> Model3D:
    global _boid_model_cache
    if _boid_model_cache is not None:
        return _boid_model_cache

    length = BOID_MODEL_LENGTH
    width = BOID_MODEL_WIDTH
    height = BOID_MODEL_HEIGHT
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


def _orientation_quaternion(vx: float, vy: float, vz: float) -> Quaternion:
    speed = math.hypot(vx, vy, vz)
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


# -----------------------------------------------------------------------------
# Drawing helpers


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


def _set_camera_and_lights(draw3d: gs.FastDrawScope) -> None:
    draw3d.camera(0, CAMERA_HEIGHT, CAMERA_DISTANCE, 0, 0, 0, 0, 1, 0)
    draw3d.ambient_light(44)
    draw3d.directional_light(135, 172, 255, -0.35, -0.75, -1.0)
    draw3d.point_light(120, 238, 205, *POINT_LIGHT_POSITION)


def _draw_boids(draw3d: gs.FastDrawScope, boid_rows: list[BoidDrawRow]) -> None:
    model = _boid_model()
    for bucket, bucket_indices in enumerate(_boid_bucket_indices):
        draw3d.specular_material(*PALETTE[bucket])
        draw3d.shininess(28)
        for index in bucket_indices:
            x, y, z, vx, vy, vz = boid_rows[index]
            with draw3d.pushed():
                draw3d.translate(x, y, z)
                draw3d.rotate_quaternion(*_orientation_quaternion(vx, vy, vz))
                draw3d.model(model)


def _draw_hud(fps: float) -> None:
    gs.reset_matrix()
    gs.fill(238, 244, 255, 235)
    gs.text_size(15)
    gs.text(f"ECS 3D boids | {BOID_COUNT:,} agents | separation + alignment + cohesion", 24, 32)
    gs.text(
        f"fps {fps:5.1f} | ECS spatial relation aggregates + fast model transforms",
        24,
        HEIGHT - 24,
    )


# -----------------------------------------------------------------------------
# Sketch lifecycle


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
    gs.order(["simulation", "draw"])
    gs.add_system(simulate_boids, group="simulation")
    _prepare_boids()


@gs.draw
def draw() -> None:
    frame = gs.frame_count()
    fps = _update_fps()
    draw3d = gs.fast()

    gs.background(5, 8, 18)
    _set_camera_and_lights(draw3d)
    _draw_boids(draw3d, _boid_draw_states_from_context())
    _draw_hud(fps)
    save_once(ARGS, frame, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
