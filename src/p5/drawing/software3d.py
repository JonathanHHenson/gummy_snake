"""Software-projected 3D helpers used by the first WEBGL-style milestone."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from p5.assets.image import Image as P5Image
from p5.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Projection3D,
    Vec3,
)
from p5.exceptions import ArgumentValidationError

type ScreenPoint = tuple[float, float]
type RGBAFloat = tuple[float, float, float, float]
type UVCoord = tuple[float, float]


@dataclass(frozen=True, slots=True)
class ProjectedFace:
    points: tuple[ScreenPoint, ...]
    depth: float
    normal: Vec3
    center: Vec3
    texcoords: tuple[UVCoord, ...] | None = None
    texture: P5Image | None = None


@dataclass(frozen=True, slots=True)
class ShadedFace:
    points: tuple[ScreenPoint, ...]
    color: RGBAFloat
    depth: float
    texcoords: tuple[UVCoord, ...] | None = None
    texture: P5Image | None = None


def plane_model(width: float, height: float | None = None) -> Model3D:
    plane_height = width if height is None else height
    if width <= 0 or plane_height <= 0:
        raise ArgumentValidationError("plane() dimensions must be positive.")
    hw = width / 2.0
    hh = plane_height / 2.0
    mesh = Mesh3D(
        vertices=(
            Vec3(-hw, -hh, 0.0),
            Vec3(hw, -hh, 0.0),
            Vec3(hw, hh, 0.0),
            Vec3(-hw, hh, 0.0),
        ),
        faces=((0, 1, 2, 3),),
        texcoords=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
    )
    return Model3D(meshes=(mesh,))


def box_model(width: float, height: float | None = None, depth: float | None = None) -> Model3D:
    box_height = width if height is None else height
    box_depth = width if depth is None else depth
    if width <= 0 or box_height <= 0 or box_depth <= 0:
        raise ArgumentValidationError("box() dimensions must be positive.")
    hw = width / 2.0
    hh = box_height / 2.0
    hd = box_depth / 2.0

    face_specs = (
        (
            (Vec3(-hw, -hh, -hd), Vec3(hw, -hh, -hd), Vec3(hw, hh, -hd), Vec3(-hw, hh, -hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(-hw, -hh, hd), Vec3(hw, -hh, hd), Vec3(hw, hh, hd), Vec3(-hw, hh, hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(-hw, -hh, -hd), Vec3(hw, -hh, -hd), Vec3(hw, -hh, hd), Vec3(-hw, -hh, hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(hw, hh, -hd), Vec3(-hw, hh, -hd), Vec3(-hw, hh, hd), Vec3(hw, hh, hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(hw, -hh, -hd), Vec3(hw, hh, -hd), Vec3(hw, hh, hd), Vec3(hw, -hh, hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
        (
            (Vec3(-hw, -hh, -hd), Vec3(-hw, hh, -hd), Vec3(-hw, hh, hd), Vec3(-hw, -hh, hd)),
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        ),
    )

    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []
    for face_vertices, face_texcoords in face_specs:
        start = len(vertices)
        vertices.extend(face_vertices)
        texcoords.extend(face_texcoords)
        faces.append((start, start + 1, start + 2, start + 3))

    mesh = Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords))
    return Model3D(meshes=(mesh,))


def sphere_model(radius: float, detail_x: int = 24, detail_y: int = 16) -> Model3D:
    if radius <= 0:
        raise ArgumentValidationError("sphere() radius must be positive.")
    if detail_x < 3 or detail_y < 2:
        raise ArgumentValidationError("sphere() detail values must be at least 3 and 2.")

    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []

    for iy in range(detail_y + 1):
        phi = math.pi * iy / detail_y
        y = math.cos(phi) * radius
        ring_radius = math.sin(phi) * radius
        v = 1.0 - iy / detail_y
        for ix in range(detail_x):
            theta = 2.0 * math.pi * ix / detail_x
            x = math.cos(theta) * ring_radius
            z = math.sin(theta) * ring_radius
            vertices.append(Vec3(x, y, z))
            texcoords.append((ix / detail_x, v))

    def vertex_index(ix: int, iy: int) -> int:
        return iy * detail_x + (ix % detail_x)

    for iy in range(detail_y):
        for ix in range(detail_x):
            top_left = vertex_index(ix, iy)
            top_right = vertex_index(ix + 1, iy)
            bottom_left = vertex_index(ix, iy + 1)
            bottom_right = vertex_index(ix + 1, iy + 1)
            if iy == 0:
                faces.append((top_left, bottom_left, bottom_right))
            elif iy == detail_y - 1:
                faces.append((top_left, top_right, bottom_left))
            else:
                faces.append((top_left, top_right, bottom_right, bottom_left))

    return Model3D(
        meshes=(Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords)),)
    )


def ellipsoid_model(
    radius_x: float,
    radius_y: float | None = None,
    radius_z: float | None = None,
    detail_x: int = 24,
    detail_y: int = 16,
) -> Model3D:
    ry = radius_x if radius_y is None else radius_y
    rz = radius_x if radius_z is None else radius_z
    model = sphere_model(1.0, detail_x, detail_y)
    mesh = model.meshes[0]
    vertices = tuple(
        Vec3(vertex.x * radius_x, vertex.y * ry, vertex.z * rz) for vertex in mesh.vertices
    )
    return Model3D(meshes=(Mesh3D(vertices=vertices, faces=mesh.faces, texcoords=mesh.texcoords),))


def cylinder_model(
    radius: float,
    height: float,
    detail_x: int = 24,
    detail_y: int = 1,
    *,
    bottom_cap: bool = True,
    top_cap: bool = True,
) -> Model3D:
    if radius <= 0 or height <= 0:
        raise ArgumentValidationError("cylinder() radius and height must be positive.")
    if detail_x < 3 or detail_y < 1:
        raise ArgumentValidationError("cylinder() detail values must be at least 3 and 1.")
    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []
    half_height = height / 2.0
    for iy in range(detail_y + 1):
        y = -half_height + height * iy / detail_y
        v = iy / detail_y
        for ix in range(detail_x):
            theta = math.tau * ix / detail_x
            vertices.append(Vec3(math.cos(theta) * radius, y, math.sin(theta) * radius))
            texcoords.append((ix / detail_x, v))

    def vertex_index(ix: int, iy: int) -> int:
        return iy * detail_x + (ix % detail_x)

    for iy in range(detail_y):
        for ix in range(detail_x):
            faces.append(
                (
                    vertex_index(ix, iy),
                    vertex_index(ix + 1, iy),
                    vertex_index(ix + 1, iy + 1),
                    vertex_index(ix, iy + 1),
                )
            )
    if bottom_cap:
        center = len(vertices)
        vertices.append(Vec3(0.0, -half_height, 0.0))
        texcoords.append((0.5, 0.5))
        for ix in range(detail_x):
            faces.append((center, vertex_index(ix + 1, 0), vertex_index(ix, 0)))
    if top_cap:
        center = len(vertices)
        vertices.append(Vec3(0.0, half_height, 0.0))
        texcoords.append((0.5, 0.5))
        for ix in range(detail_x):
            faces.append((center, vertex_index(ix, detail_y), vertex_index(ix + 1, detail_y)))
    return Model3D(
        meshes=(Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords)),)
    )


def cone_model(
    radius: float,
    height: float,
    detail_x: int = 24,
    detail_y: int = 1,
    *,
    cap: bool = True,
) -> Model3D:
    if radius <= 0 or height <= 0:
        raise ArgumentValidationError("cone() radius and height must be positive.")
    if detail_x < 3 or detail_y < 1:
        raise ArgumentValidationError("cone() detail values must be at least 3 and 1.")
    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []
    half_height = height / 2.0
    for iy in range(detail_y + 1):
        fraction = iy / detail_y
        ring_radius = radius * (1.0 - fraction)
        y = -half_height + height * fraction
        for ix in range(detail_x):
            theta = math.tau * ix / detail_x
            vertices.append(Vec3(math.cos(theta) * ring_radius, y, math.sin(theta) * ring_radius))
            texcoords.append((ix / detail_x, fraction))

    def vertex_index(ix: int, iy: int) -> int:
        return iy * detail_x + (ix % detail_x)

    for iy in range(detail_y):
        for ix in range(detail_x):
            if iy == detail_y - 1:
                faces.append(
                    (vertex_index(ix, iy), vertex_index(ix + 1, iy), vertex_index(ix, iy + 1))
                )
            else:
                faces.append(
                    (
                        vertex_index(ix, iy),
                        vertex_index(ix + 1, iy),
                        vertex_index(ix + 1, iy + 1),
                        vertex_index(ix, iy + 1),
                    )
                )
    if cap:
        center = len(vertices)
        vertices.append(Vec3(0.0, -half_height, 0.0))
        texcoords.append((0.5, 0.5))
        for ix in range(detail_x):
            faces.append((center, vertex_index(ix + 1, 0), vertex_index(ix, 0)))
    return Model3D(
        meshes=(Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords)),)
    )


def torus_model(
    radius: float,
    tube_radius: float | None = None,
    detail_x: int = 24,
    detail_y: int = 12,
) -> Model3D:
    tube = radius / 4.0 if tube_radius is None else tube_radius
    if radius <= 0 or tube <= 0:
        raise ArgumentValidationError("torus() radius values must be positive.")
    if detail_x < 3 or detail_y < 3:
        raise ArgumentValidationError("torus() detail values must be at least 3.")
    vertices: list[Vec3] = []
    texcoords: list[UVCoord] = []
    faces: list[tuple[int, ...]] = []
    for iy in range(detail_y):
        phi = math.tau * iy / detail_y
        cos_phi = math.cos(phi)
        sin_phi = math.sin(phi)
        for ix in range(detail_x):
            theta = math.tau * ix / detail_x
            ring = radius + tube * math.cos(theta)
            vertices.append(Vec3(ring * cos_phi, tube * math.sin(theta), ring * sin_phi))
            texcoords.append((ix / detail_x, iy / detail_y))

    def vertex_index(ix: int, iy: int) -> int:
        return (iy % detail_y) * detail_x + (ix % detail_x)

    for iy in range(detail_y):
        for ix in range(detail_x):
            faces.append(
                (
                    vertex_index(ix, iy),
                    vertex_index(ix + 1, iy),
                    vertex_index(ix + 1, iy + 1),
                    vertex_index(ix, iy + 1),
                )
            )
    return Model3D(
        meshes=(Mesh3D(vertices=tuple(vertices), faces=tuple(faces), texcoords=tuple(texcoords)),)
    )


def save_obj(model: Model3D, path: str | Path) -> Path:
    output = Path(path)
    lines: list[str] = ["# Generated by p5-py"]
    vertex_offset = 1
    for mesh in model.meshes:
        for vertex in mesh.vertices:
            lines.append(f"v {vertex.x:.9g} {vertex.y:.9g} {vertex.z:.9g}")
        for u, v in mesh.texcoords:
            lines.append(f"vt {u:.9g} {v:.9g}")
        for face in mesh.faces:
            lines.append("f " + " ".join(str(index + vertex_offset) for index in face))
        vertex_offset += len(mesh.vertices)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def save_stl(model: Model3D, path: str | Path, *, name: str = "p5_py_model") -> Path:
    output = Path(path)
    lines = [f"solid {name}"]
    for mesh in model.meshes:
        for face in mesh.faces:
            if len(face) < 3:
                continue
            first = face[0]
            for index in range(1, len(face) - 1):
                a = mesh.vertices[first]
                b = mesh.vertices[face[index]]
                c = mesh.vertices[face[index + 1]]
                normal = _triangle_normal(a, b, c)
                lines.append(f"  facet normal {normal.x:.9g} {normal.y:.9g} {normal.z:.9g}")
                lines.append("    outer loop")
                for vertex in (a, b, c):
                    lines.append(f"      vertex {vertex.x:.9g} {vertex.y:.9g} {vertex.z:.9g}")
                lines.append("    endloop")
                lines.append("  endfacet")
    lines.append(f"endsolid {name}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _triangle_normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ux, uy, uz = b.x - a.x, b.y - a.y, b.z - a.z
    vx, vy, vz = c.x - a.x, c.y - a.y, c.z - a.z
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return Vec3(0.0, 0.0, 0.0)
    return Vec3(nx / length, ny / length, nz / length)


def shade_model_faces(
    model: Model3D,
    camera: Camera3D,
    projection: Projection3D,
    *,
    viewport_width: float,
    viewport_height: float,
    base_material: Material3D,
    lights: tuple[Light3D, ...],
    normal_material: bool = False,
    cull_backfaces: bool = True,
) -> list[ShadedFace]:
    projected_faces: list[ProjectedFace] = []
    texture = _texture_image(base_material)
    for mesh in model.meshes:
        projected_faces.extend(
            _project_mesh_faces(
                mesh,
                camera,
                projection,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                cull_backfaces=cull_backfaces,
                texture=texture,
            )
        )
    projected_faces.sort(key=lambda face: face.depth, reverse=True)
    return [
        ShadedFace(
            points=face.points,
            color=_shade_face(
                face,
                material=base_material,
                camera=camera,
                lights=lights,
                normal_material=normal_material,
            ),
            depth=face.depth,
            texcoords=face.texcoords,
            texture=None if normal_material else face.texture,
        )
        for face in projected_faces
    ]


def project_model_faces(
    model: Model3D,
    camera: Camera3D,
    projection: Projection3D,
    *,
    viewport_width: float,
    viewport_height: float,
    cull_backfaces: bool = True,
) -> list[ProjectedFace]:
    if viewport_width <= 0 or viewport_height <= 0:
        raise ArgumentValidationError("viewport dimensions must be positive.")
    _validate_projection(projection)

    projected_faces: list[ProjectedFace] = []
    for mesh in model.meshes:
        projected_faces.extend(
            _project_mesh_faces(
                mesh,
                camera,
                projection,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                cull_backfaces=cull_backfaces,
            )
        )

    return sorted(projected_faces, key=lambda face: face.depth, reverse=True)


def rasterize_faces_image(
    faces: list[ShadedFace],
    *,
    viewport_width: float,
    viewport_height: float,
) -> P5Image:
    width = max(1, int(math.ceil(viewport_width)))
    height = max(1, int(math.ceil(viewport_height)))
    overlay = P5Image(width, height)

    for face in faces:
        if (
            face.texture is not None
            and face.texcoords is not None
            and len(face.points) == len(face.texcoords)
        ):
            _draw_textured_face(overlay, face)
            continue
        _draw_polygon(overlay, face.points, _rgba_to_int(face.color))

    return overlay


def _project_mesh_faces(
    mesh: Mesh3D,
    camera: Camera3D,
    projection: Projection3D,
    *,
    viewport_width: float,
    viewport_height: float,
    cull_backfaces: bool,
    texture: P5Image | None = None,
) -> list[ProjectedFace]:
    projected_faces: list[ProjectedFace] = []
    has_face_texcoords = len(mesh.texcoords) == len(mesh.vertices)

    for face_indices in mesh.faces:
        if len(face_indices) < 3:
            continue
        world_points = [mesh.vertices[index] for index in face_indices]
        normal = _face_normal(world_points)
        if normal is None:
            continue
        center = _face_center(world_points)
        if cull_backfaces and _dot(normal, _sub(camera.eye, center)) <= 0:
            continue
        camera_points = [_camera_space(point, camera) for point in world_points]
        if any(not _visible(point, projection) for point in camera_points):
            continue
        screen_points = [
            _project_camera_point(point, projection, viewport_width, viewport_height)
            for point in camera_points
        ]
        if any(point is None for point in screen_points):
            continue
        face_texcoords = None
        if has_face_texcoords:
            face_texcoords = tuple(mesh.texcoords[index] for index in face_indices)
        projected_faces.append(
            ProjectedFace(
                points=tuple(cast(ScreenPoint, point) for point in screen_points),
                depth=sum(point.z for point in camera_points) / len(camera_points),
                normal=_normalize(normal),
                center=center,
                texcoords=face_texcoords,
                texture=texture,
            )
        )

    return projected_faces


def _shade_face(
    face: ProjectedFace,
    *,
    material: Material3D,
    camera: Camera3D,
    lights: tuple[Light3D, ...],
    normal_material: bool,
) -> RGBAFloat:
    if normal_material:
        normal = face.normal
        return (
            (normal.x + 1.0) / 2.0,
            (normal.y + 1.0) / 2.0,
            (normal.z + 1.0) / 2.0,
            material.base_color[3],
        )

    base_r, base_g, base_b, base_a = material.base_color
    if not lights:
        return _clamp_rgba(
            (
                base_r + material.emissive_color[0],
                base_g + material.emissive_color[1],
                base_b + material.emissive_color[2],
                base_a,
            )
        )

    result = [material.emissive_color[0], material.emissive_color[1], material.emissive_color[2]]
    normal = face.normal
    view_dir = _normalize(_sub(camera.eye, face.center))
    for light in lights:
        light_rgb = light.color[:3]
        intensity = max(0.0, light.intensity)
        if light.kind == "ambient":
            for index in range(3):
                result[index] += (
                    base_material_component(base_r, base_g, base_b, index)
                    * light_rgb[index]
                    * intensity
                )
            continue
        light_dir = _light_direction(light, face.center)
        if light_dir is None:
            continue
        diffuse = max(0.0, _dot(normal, light_dir))
        for index in range(3):
            result[index] += (
                base_material_component(base_r, base_g, base_b, index)
                * light_rgb[index]
                * diffuse
                * intensity
            )
        half_vector = _normalize(_add(light_dir, view_dir))
        specular = max(0.0, _dot(normal, half_vector)) ** max(1.0, material.shininess)
        for index, component in enumerate(material.specular_color[:3]):
            result[index] += component * light_rgb[index] * specular * intensity

    return _clamp_rgba((result[0], result[1], result[2], base_a))


def _draw_textured_face(image: P5Image, face: ShadedFace) -> None:
    if face.texture is None or face.texcoords is None:
        return
    for triangle_points, triangle_texcoords in _triangulated_face(face.points, face.texcoords):
        _draw_textured_triangle(
            image,
            face.texture,
            triangle_points,
            triangle_texcoords,
            modulation=face.color,
        )


def _triangulated_face(
    points: tuple[ScreenPoint, ...],
    texcoords: tuple[UVCoord, ...],
):
    for index in range(1, len(points) - 1):
        yield (
            (points[0], points[index], points[index + 1]),
            (texcoords[0], texcoords[index], texcoords[index + 1]),
        )


def _draw_textured_triangle(
    target: P5Image,
    texture: P5Image,
    points: tuple[ScreenPoint, ScreenPoint, ScreenPoint],
    texcoords: tuple[UVCoord, UVCoord, UVCoord],
    *,
    modulation: RGBAFloat,
) -> None:
    (x1, y1), (x2, y2), (x3, y3) = points
    denominator = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if denominator == 0:
        return

    width, height = target.width, target.height
    min_x = max(0, int(math.floor(min(x1, x2, x3))))
    max_x = min(width - 1, int(math.ceil(max(x1, x2, x3))))
    min_y = max(0, int(math.floor(min(y1, y2, y3))))
    max_y = min(height - 1, int(math.ceil(max(y1, y2, y3))))
    if min_x > max_x or min_y > max_y:
        return

    for py in range(min_y, max_y + 1):
        sample_y = py + 0.5
        for px in range(min_x, max_x + 1):
            sample_x = px + 0.5
            w1 = ((y2 - y3) * (sample_x - x3) + (x3 - x2) * (sample_y - y3)) / denominator
            w2 = ((y3 - y1) * (sample_x - x3) + (x1 - x3) * (sample_y - y3)) / denominator
            w3 = 1.0 - w1 - w2
            if w1 < -1e-6 or w2 < -1e-6 or w3 < -1e-6:
                continue

            u = w1 * texcoords[0][0] + w2 * texcoords[1][0] + w3 * texcoords[2][0]
            v = w1 * texcoords[0][1] + w2 * texcoords[1][1] + w3 * texcoords[2][1]
            tx = max(
                0, min(texture.width - 1, int(round(max(0.0, min(1.0, u)) * (texture.width - 1))))
            )
            ty = max(
                0,
                min(
                    texture.height - 1,
                    int(round((1.0 - max(0.0, min(1.0, v))) * (texture.height - 1))),
                ),
            )
            sampled = texture._pixel(tx, ty)
            shaded = (
                int(round(sampled[0] * modulation[0])),
                int(round(sampled[1] * modulation[1])),
                int(round(sampled[2] * modulation[2])),
                int(round(sampled[3] * modulation[3])),
            )
            target._put_pixel(px, py, _alpha_over(target._pixel(px, py), shaded))


def _draw_polygon(
    target: P5Image,
    points: tuple[ScreenPoint, ...],
    color: tuple[int, int, int, int],
) -> None:
    if len(points) < 3:
        return
    min_x = max(0, int(math.floor(min(point[0] for point in points))))
    max_x = min(target.width - 1, int(math.ceil(max(point[0] for point in points))))
    min_y = max(0, int(math.floor(min(point[1] for point in points))))
    max_y = min(target.height - 1, int(math.ceil(max(point[1] for point in points))))
    for py in range(min_y, max_y + 1):
        for px in range(min_x, max_x + 1):
            if _point_in_polygon(px + 0.5, py + 0.5, points):
                target._put_pixel(px, py, _alpha_over(target._pixel(px, py), color))


def _point_in_polygon(x: float, y: float, points: tuple[ScreenPoint, ...]) -> bool:
    inside = False
    previous = points[-1]
    for current in points:
        xi, yi = current
        xj, yj = previous
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        previous = current
    return inside


def _alpha_over(
    destination: tuple[int, int, int, int],
    source: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    source_alpha = source[3] / 255.0
    if source_alpha <= 0.0:
        return destination
    destination_alpha = destination[3] / 255.0
    output_alpha = source_alpha + destination_alpha * (1.0 - source_alpha)
    if output_alpha <= 0.0:
        return (0, 0, 0, 0)

    blended = []
    for index in range(3):
        value = (
            source[index] * source_alpha
            + destination[index] * destination_alpha * (1.0 - source_alpha)
        ) / output_alpha
        blended.append(int(round(value)))
    blended.append(int(round(output_alpha * 255.0)))
    return cast(tuple[int, int, int, int], tuple(blended))


def _rgba_to_int(color: RGBAFloat) -> tuple[int, int, int, int]:
    return cast(
        tuple[int, int, int, int],
        tuple(int(round(max(0.0, min(1.0, component)) * 255.0)) for component in color),
    )


def _texture_image(material: Material3D) -> P5Image | None:
    texture = material.texture
    if texture is None:
        return None
    source = texture.source
    return source if isinstance(source, P5Image) else None


def base_material_component(r: float, g: float, b: float, index: int) -> float:
    return (r, g, b)[index]


def _light_direction(light: Light3D, center: Vec3) -> Vec3 | None:
    if light.kind == "directional":
        if light.direction is None:
            return None
        return _normalize(Vec3(-light.direction.x, -light.direction.y, -light.direction.z))
    if light.kind == "point":
        if light.position is None:
            return None
        return _normalize(_sub(light.position, center))
    return None


def _clamp_rgba(color: RGBAFloat) -> RGBAFloat:
    return tuple(max(0.0, min(1.0, component)) for component in color)  # type: ignore[return-value]


def _visible(point: Vec3, projection: Projection3D) -> bool:
    return projection.near <= point.z <= projection.far


def _project_camera_point(
    point: Vec3,
    projection: Projection3D,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    if isinstance(projection, PerspectiveProjection):
        return _project_perspective(point, projection, viewport_width, viewport_height)
    return _project_orthographic(point, projection, viewport_width, viewport_height)


def _project_perspective(
    point: Vec3,
    projection: PerspectiveProjection,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    if not _visible(point, projection):
        return None
    aspect = projection.aspect or viewport_width / viewport_height
    half_fov = math.radians(projection.fov_y) / 2.0
    scale_y = math.tan(half_fov) * point.z
    if scale_y == 0:
        return None
    scale_x = scale_y * aspect
    if scale_x == 0:
        return None
    x_ndc = point.x / scale_x
    y_ndc = point.y / scale_y
    return _ndc_to_screen(x_ndc, y_ndc, viewport_width, viewport_height)


def _project_orthographic(
    point: Vec3,
    projection: OrthographicProjection,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    if not _visible(point, projection):
        return None
    x_ndc = point.x / (projection.width / 2.0)
    y_ndc = point.y / (projection.height / 2.0)
    return _ndc_to_screen(x_ndc, y_ndc, viewport_width, viewport_height)


def _ndc_to_screen(
    x_ndc: float,
    y_ndc: float,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint:
    x = (x_ndc + 1.0) * 0.5 * viewport_width
    y = (1.0 - (y_ndc + 1.0) * 0.5) * viewport_height
    return (x, y)


def _camera_space(point: Vec3, camera: Camera3D) -> Vec3:
    forward = _normalize(_sub(camera.target, camera.eye))
    right = _normalize(_cross(forward, camera.up))
    true_up = _cross(right, forward)
    relative = _sub(point, camera.eye)
    return Vec3(_dot(relative, right), _dot(relative, true_up), _dot(relative, forward))


def _validate_projection(projection: Projection3D) -> None:
    if projection.near <= 0:
        raise ArgumentValidationError("projection near plane must be positive.")
    if projection.far <= projection.near:
        raise ArgumentValidationError("projection far plane must be greater than the near plane.")
    if isinstance(projection, PerspectiveProjection):
        if projection.fov_y <= 0 or projection.fov_y >= 180:
            raise ArgumentValidationError("perspective fov_y must be between 0 and 180 degrees.")
        if projection.aspect is not None and projection.aspect <= 0:
            raise ArgumentValidationError("perspective aspect must be positive when provided.")
    else:
        if projection.width <= 0 or projection.height <= 0:
            raise ArgumentValidationError("orthographic width and height must be positive.")


def _face_center(points: list[Vec3]) -> Vec3:
    scale = 1.0 / len(points)
    return Vec3(
        sum(point.x for point in points) * scale,
        sum(point.y for point in points) * scale,
        sum(point.z for point in points) * scale,
    )


def _face_normal(points: list[Vec3]) -> Vec3 | None:
    if len(points) < 3:
        return None
    a = points[0]
    b = points[1]
    c = points[2]
    normal = _cross(_sub(b, a), _sub(c, a))
    if _dot(normal, normal) == 0:
        return None
    return normal


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)


def _add(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x + b.x, a.y + b.y, a.z + b.z)


def _dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _normalize(value: Vec3) -> Vec3:
    length = math.sqrt(_dot(value, value))
    if length == 0:
        raise ArgumentValidationError("3D vectors must have non-zero length.")
    return Vec3(value.x / length, value.y / length, value.z / length)


__all__ = [
    "ProjectedFace",
    "ShadedFace",
    "box_model",
    "plane_model",
    "project_model_faces",
    "rasterize_faces_image",
    "shade_model_faces",
    "sphere_model",
]
