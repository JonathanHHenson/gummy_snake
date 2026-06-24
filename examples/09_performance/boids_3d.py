"""3D boids flocking performance sketch.

A WEBGL version of Craig Reynolds-style boids: many agents steer using
separation, alignment, and cohesion while flying through a bounded 3D volume.
The simulation uses a small spatial hash so neighbor queries stay practical in
plain Python, then renders each flock as one lightweight dynamic 3D mesh.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once
from gummysnake.drawing.renderer3d import Mesh3D, Model3D, Vec3

WIDTH = 960
HEIGHT = 540
TARGET_FPS = 60
BOID_COUNT = 1_200
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

OUTPUT = Path("examples/output/09_performance/boids_3d.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

positions_x: list[float] = []
positions_y: list[float] = []
positions_z: list[float] = []
velocities_x: list[float] = []
velocities_y: list[float] = []
velocities_z: list[float] = []
bucket_indices: list[list[int]] = []
spatial_grid: dict[tuple[int, int, int], list[int]] = {}
fps_last_time: float | None = None
fps_value = float(TARGET_FPS)

palette = [
    (95, 185, 255, 220),
    (105, 238, 192, 215),
    (255, 216, 118, 215),
    (255, 140, 145, 212),
    (185, 145, 255, 218),
]


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


def _length(x: float, y: float, z: float) -> float:
    return math.sqrt(x * x + y * y + z * z)


def _limit_vector(
    x: float,
    y: float,
    z: float,
    maximum: float,
) -> tuple[float, float, float]:
    length = _length(x, y, z)
    if length <= maximum or length <= 1e-9:
        return (x, y, z)
    scale = maximum / length
    return (x * scale, y * scale, z * scale)


def _set_magnitude(
    x: float,
    y: float,
    z: float,
    magnitude: float,
) -> tuple[float, float, float]:
    length = _length(x, y, z)
    if length <= 1e-9:
        return (magnitude, 0.0, 0.0)
    scale = magnitude / length
    return (x * scale, y * scale, z * scale)


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    ax, ay, az = left
    bx, by, bz = right
    return (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)


def _prepare_boids() -> None:
    global bucket_indices
    rng = random.Random(20240624)
    positions_x.clear()
    positions_y.clear()
    positions_z.clear()
    velocities_x.clear()
    velocities_y.clear()
    velocities_z.clear()
    bucket_indices = [[] for _ in palette]

    for index in range(BOID_COUNT):
        positions_x.append(rng.uniform(-WORLD_X * 0.45, WORLD_X * 0.45))
        positions_y.append(rng.uniform(-WORLD_Y * 0.45, WORLD_Y * 0.45))
        positions_z.append(rng.uniform(-WORLD_Z * 0.45, WORLD_Z * 0.45))
        angle = rng.random() * math.tau
        pitch = rng.uniform(-0.45, 0.45)
        speed = rng.uniform(MIN_SPEED, MAX_SPEED)
        velocities_x.append(math.cos(angle) * math.cos(pitch) * speed)
        velocities_y.append(math.sin(pitch) * speed)
        velocities_z.append(math.sin(angle) * math.cos(pitch) * speed)
        bucket_indices[index % len(palette)].append(index)


def _cell_for(index: int) -> tuple[int, int, int]:
    cell_size = PERCEPTION_RADIUS
    return (
        math.floor(positions_x[index] / cell_size),
        math.floor(positions_y[index] / cell_size),
        math.floor(positions_z[index] / cell_size),
    )


def _rebuild_grid() -> None:
    spatial_grid.clear()
    for index in range(BOID_COUNT):
        spatial_grid.setdefault(_cell_for(index), []).append(index)


def _neighbor_indices(index: int) -> list[int]:
    cx, cy, cz = _cell_for(index)
    neighbors: list[int] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                neighbors.extend(spatial_grid.get((cx + dx, cy + dy, cz + dz), ()))
    return neighbors


def _steer_toward(
    desired_x: float,
    desired_y: float,
    desired_z: float,
    velocity_x: float,
    velocity_y: float,
    velocity_z: float,
    speed: float = MAX_SPEED,
) -> tuple[float, float, float]:
    desired_x, desired_y, desired_z = _set_magnitude(desired_x, desired_y, desired_z, speed)
    return _limit_vector(
        desired_x - velocity_x,
        desired_y - velocity_y,
        desired_z - velocity_z,
        MAX_FORCE,
    )


def _update_boid(index: int) -> None:
    x = positions_x[index]
    y = positions_y[index]
    z = positions_z[index]
    vx = velocities_x[index]
    vy = velocities_y[index]
    vz = velocities_z[index]

    separation_x = separation_y = separation_z = 0.0
    alignment_x = alignment_y = alignment_z = 0.0
    cohesion_x = cohesion_y = cohesion_z = 0.0
    separation_count = 0
    flock_count = 0

    for other in _neighbor_indices(index):
        if other == index:
            continue
        dx = positions_x[other] - x
        dy = positions_y[other] - y
        dz = positions_z[other] - z
        distance_squared = dx * dx + dy * dy + dz * dz
        if distance_squared <= 1e-9 or distance_squared > PERCEPTION_RADIUS * PERCEPTION_RADIUS:
            continue
        distance = math.sqrt(distance_squared)
        alignment_x += velocities_x[other]
        alignment_y += velocities_y[other]
        alignment_z += velocities_z[other]
        cohesion_x += positions_x[other]
        cohesion_y += positions_y[other]
        cohesion_z += positions_z[other]
        flock_count += 1
        if distance < SEPARATION_RADIUS:
            weight = 1.0 / max(distance, 1.0)
            separation_x -= dx * weight
            separation_y -= dy * weight
            separation_z -= dz * weight
            separation_count += 1

    force_x = force_y = force_z = 0.0
    if flock_count > 0:
        inv_count = 1.0 / flock_count
        align = _steer_toward(
            alignment_x * inv_count,
            alignment_y * inv_count,
            alignment_z * inv_count,
            vx,
            vy,
            vz,
        )
        cohesion = _steer_toward(
            cohesion_x * inv_count - x,
            cohesion_y * inv_count - y,
            cohesion_z * inv_count - z,
            vx,
            vy,
            vz,
            speed=MAX_SPEED * 0.82,
        )
        force_x += align[0] * 1.0 + cohesion[0] * 0.74
        force_y += align[1] * 1.0 + cohesion[1] * 0.74
        force_z += align[2] * 1.0 + cohesion[2] * 0.74
    if separation_count > 0:
        separate = _steer_toward(separation_x, separation_y, separation_z, vx, vy, vz)
        force_x += separate[0] * 1.65
        force_y += separate[1] * 1.65
        force_z += separate[2] * 1.65

    if abs(x) > WORLD_X * 0.5 - BOUND_MARGIN:
        force_x -= math.copysign(BOUND_FORCE, x)
    if abs(y) > WORLD_Y * 0.5 - BOUND_MARGIN:
        force_y -= math.copysign(BOUND_FORCE, y)
    if abs(z) > WORLD_Z * 0.5 - BOUND_MARGIN:
        force_z -= math.copysign(BOUND_FORCE, z)

    vx, vy, vz = _limit_vector(vx + force_x, vy + force_y, vz + force_z, MAX_SPEED)
    speed = _length(vx, vy, vz)
    if speed < MIN_SPEED:
        vx, vy, vz = _set_magnitude(vx, vy, vz, MIN_SPEED)

    positions_x[index] = x + vx
    positions_y[index] = y + vy
    positions_z[index] = z + vz
    velocities_x[index] = vx
    velocities_y[index] = vy
    velocities_z[index] = vz


def _append_boid(
    vertices: list[Vec3],
    normals: list[Vec3],
    faces: list[tuple[int, int, int]],
    index: int,
) -> None:
    x = positions_x[index]
    y = positions_y[index]
    z = positions_z[index]
    forward = _set_magnitude(velocities_x[index], velocities_y[index], velocities_z[index], 1.0)
    reference = (0.0, 1.0, 0.0) if abs(forward[1]) < 0.9 else (1.0, 0.0, 0.0)
    right = _set_magnitude(*_cross(forward, reference), magnitude=1.0)
    up = _set_magnitude(*_cross(right, forward), magnitude=1.0)
    length = 12.0
    width = 5.0
    height = 4.2
    base = len(vertices)

    nose = Vec3(x + forward[0] * length, y + forward[1] * length, z + forward[2] * length)
    left = Vec3(
        x - forward[0] * length * 0.55 - right[0] * width,
        y - forward[1] * length * 0.55 - right[1] * width,
        z - forward[2] * length * 0.55 - right[2] * width,
    )
    right_vertex = Vec3(
        x - forward[0] * length * 0.55 + right[0] * width,
        y - forward[1] * length * 0.55 + right[1] * width,
        z - forward[2] * length * 0.55 + right[2] * width,
    )
    dorsal = Vec3(x + up[0] * height, y + up[1] * height, z + up[2] * height)
    vertices.extend((nose, left, right_vertex, dorsal))
    normals.extend((Vec3(*forward), Vec3(*right), Vec3(-right[0], -right[1], -right[2]), Vec3(*up)))
    faces.extend(
        (
            (base, base + 1, base + 3),
            (base, base + 3, base + 2),
            (base, base + 2, base + 1),
            (base + 1, base + 2, base + 3),
        )
    )


def _flock_model(indices: list[int]) -> Model3D:
    vertices: list[Vec3] = []
    normals: list[Vec3] = []
    faces: list[tuple[int, int, int]] = []
    for index in indices:
        _append_boid(vertices, normals, faces, index)
    return Model3D(meshes=(Mesh3D(vertices=vertices, faces=faces, normals=normals),))


@gs.setup
def setup() -> None:
    gs.create_canvas(WIDTH, HEIGHT, gs.WEBGL)
    gs.frame_rate(TARGET_FPS)
    gs.no_stroke()
    gs.perspective(FOV_Y, WIDTH / HEIGHT, 0.1, 5000)
    gs.describe("A 3D boids flocking simulation using spatial hashing and WEBGL meshes.")
    _prepare_boids()


@gs.draw
def draw() -> None:
    frame = gs.frame_count()
    fps = _update_fps()
    orbit = frame * 0.008
    eye_x = math.sin(orbit) * CAMERA_ORBIT_RADIUS
    eye_y = CAMERA_HEIGHT
    eye_z = math.cos(orbit) * CAMERA_ORBIT_RADIUS

    _rebuild_grid()
    for index in range(BOID_COUNT):
        _update_boid(index)

    gs.camera(eye_x, eye_y, eye_z, 0, 0, 0, 0, 1, 0)
    gs.background(5, 8, 18)
    gs.ambient_light(44)
    gs.directional_light(135, 172, 255, -0.35, -0.75, -1.0)
    gs.point_light(120, 238, 205, *POINT_LIGHT_POSITION)

    for bucket, indices in enumerate(bucket_indices):
        gs.specular_material(*palette[bucket])
        gs.shininess(28)
        gs.model(_flock_model(indices))

    gs.reset_matrix()
    gs.fill(238, 244, 255, 235)
    gs.text_size(15)
    gs.text(f"3D boids | {BOID_COUNT:,} agents | separation + alignment + cohesion", 24, 32)
    gs.text(f"fps {fps:5.1f} | spatial hash neighbor lookup", 24, HEIGHT - 24)
    save_once(ARGS, frame, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
