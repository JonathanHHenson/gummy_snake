"""Backend-neutral 3D model loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.drawing.renderer3d import Mesh3D, Model3D, Vec3
from gummysnake.exceptions import ArgumentValidationError

type VertexRef = tuple[int, int | None, int | None]


@dataclass(slots=True)
class _ObjParseState:
    positions: list[Vec3]
    texcoords: list[tuple[float, float]]
    normals: list[Vec3]
    vertices: list[Vec3]
    vertex_texcoords: list[tuple[float, float] | None]
    vertex_normals: list[Vec3 | None]
    faces: list[tuple[int, ...]]
    vertex_map: dict[VertexRef, int]


def load_model(
    path: str | Path,
    normalize: bool = False,
    *,
    package: str | None = None,
) -> Model3D:
    """Load a Wavefront OBJ asset into backend-neutral mesh data.

    The first milestone supports local filesystem paths and importable package
    resources. OBJ material libraries are ignored for now, and only geometry,
    optional vertex normals, and optional texture coordinates are loaded.
    """

    obj_text, source = _read_text_asset(path, package=package)
    return _parse_obj_rust(obj_text, source=source, normalize=normalize)


async def load_model_async(
    path: str | Path,
    normalize: bool = False,
    *,
    package: str | None = None,
) -> Model3D:
    return load_model(path, normalize, package=package)


def _read_text_asset(path: str | Path, *, package: str | None) -> tuple[str, Path]:
    if package is None:
        source = resolve_asset_path(path)
        if not source.exists():
            raise ArgumentValidationError(f"Model file does not exist: {source!s}.")
        try:
            return source.read_text(encoding="utf-8"), source
        except OSError as exc:
            raise ArgumentValidationError(f"Could not load model {source!s}.") from exc

    resource = resources.files(package).joinpath(str(path))
    if not resource.is_file():
        raise ArgumentValidationError(
            f"Model resource {str(path)!r} was not found in package {package!r}."
        )
    try:
        return resource.read_text(encoding="utf-8"), Path(f"{package}:{path}")
    except OSError as exc:
        raise ArgumentValidationError(
            f"Could not load model resource {str(path)!r} from package {package!r}."
        ) from exc


def _parse_obj(text: str, *, source: Path) -> Model3D:
    state = _ObjParseState(
        positions=[],
        texcoords=[],
        normals=[],
        vertices=[],
        vertex_texcoords=[],
        vertex_normals=[],
        faces=[],
        vertex_map={},
    )

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        keyword, *values = line.split()
        if keyword == "v":
            if len(values) < 3:
                raise ArgumentValidationError(
                    f"OBJ vertex on line {line_number} in {source!s} requires x y z."
                )
            state.positions.append(Vec3(float(values[0]), float(values[1]), float(values[2])))
            continue
        if keyword == "vt":
            if len(values) < 2:
                raise ArgumentValidationError(
                    f"OBJ texcoord on line {line_number} in {source!s} requires u v."
                )
            state.texcoords.append((float(values[0]), float(values[1])))
            continue
        if keyword == "vn":
            if len(values) < 3:
                raise ArgumentValidationError(
                    f"OBJ normal on line {line_number} in {source!s} requires x y z."
                )
            state.normals.append(Vec3(float(values[0]), float(values[1]), float(values[2])))
            continue
        if keyword == "f":
            if len(values) < 3:
                raise ArgumentValidationError(
                    f"OBJ face on line {line_number} in {source!s} requires at least 3 vertices."
                )
            face = tuple(
                _resolve_face_vertex(token, state, line_number, source) for token in values
            )
            state.faces.append(face)
            continue
        if keyword in {"o", "g", "s", "mtllib", "usemtl"}:
            continue

    if not state.vertices or not state.faces:
        raise ArgumentValidationError(f"OBJ model {source!s} contained no drawable faces.")

    texcoords: tuple[tuple[float, float], ...] = ()
    if state.vertex_texcoords and all(value is not None for value in state.vertex_texcoords):
        texcoords = tuple(value for value in state.vertex_texcoords if value is not None)

    normals: tuple[Vec3, ...] = ()
    if state.vertex_normals and all(value is not None for value in state.vertex_normals):
        normals = tuple(value for value in state.vertex_normals if value is not None)

    mesh = Mesh3D(
        vertices=tuple(state.vertices),
        faces=tuple(state.faces),
        normals=normals,
        texcoords=texcoords,
    )
    return Model3D(meshes=(mesh,), source=source)


def _parse_obj_rust(text: str, *, source: Path, normalize: bool) -> Model3D:
    from gummysnake.rust.canvas import require_canvas_extension

    try:
        payload = require_canvas_extension().parse_obj_model(text, str(source), normalize)
    except ValueError as exc:
        raise ArgumentValidationError(str(exc)) from exc

    vertices = tuple(Vec3(float(x), float(y), float(z)) for x, y, z in payload["vertices"])
    faces = tuple(tuple(int(index) for index in face) for face in payload["faces"])
    texcoords = tuple((float(u), float(v)) for u, v in payload.get("texcoords", ()))
    normals = tuple(Vec3(float(x), float(y), float(z)) for x, y, z in payload.get("normals", ()))
    mesh = Mesh3D(vertices=vertices, faces=faces, normals=normals, texcoords=texcoords)
    return Model3D(meshes=(mesh,), source=source)


def _resolve_face_vertex(token: str, state: _ObjParseState, line_number: int, source: Path) -> int:
    ref = _parse_vertex_ref(token, state, line_number, source)
    existing = state.vertex_map.get(ref)
    if existing is not None:
        return existing

    position_index, texcoord_index, normal_index = ref
    state.vertices.append(state.positions[position_index])
    state.vertex_texcoords.append(
        None if texcoord_index is None else state.texcoords[texcoord_index]
    )
    state.vertex_normals.append(None if normal_index is None else state.normals[normal_index])
    index = len(state.vertices) - 1
    state.vertex_map[ref] = index
    return index


def _parse_vertex_ref(
    token: str,
    state: _ObjParseState,
    line_number: int,
    source: Path,
) -> VertexRef:
    parts = token.split("/")
    if not parts or parts[0] == "":
        raise ArgumentValidationError(
            f"OBJ face vertex {token!r} on line {line_number} in {source!s} is invalid."
        )
    position_index = _resolve_index(parts[0], len(state.positions), "position", line_number, source)
    texcoord_index = None
    normal_index = None
    if len(parts) >= 2 and parts[1] != "":
        texcoord_index = _resolve_index(
            parts[1], len(state.texcoords), "texcoord", line_number, source
        )
    if len(parts) >= 3 and parts[2] != "":
        normal_index = _resolve_index(parts[2], len(state.normals), "normal", line_number, source)
    return position_index, texcoord_index, normal_index


def _resolve_index(
    raw_index: str,
    length: int,
    kind: str,
    line_number: int,
    source: Path,
) -> int:
    if length == 0:
        raise ArgumentValidationError(
            f"OBJ references a {kind} before any {kind}s were defined "
            f"on line {line_number} in {source!s}."
        )
    try:
        index = int(raw_index)
    except ValueError as exc:
        raise ArgumentValidationError(
            f"OBJ {kind} index {raw_index!r} on line {line_number} in {source!s} is invalid."
        ) from exc
    resolved = index - 1 if index > 0 else length + index
    if not 0 <= resolved < length:
        raise ArgumentValidationError(
            f"OBJ {kind} index {raw_index!r} on line {line_number} in {source!s} is out of range."
        )
    return resolved


def _normalize_model(model: Model3D) -> Model3D:
    vertices = [vertex for mesh in model.meshes for vertex in mesh.vertices]
    if not vertices:
        return model
    min_x = min(vertex.x for vertex in vertices)
    max_x = max(vertex.x for vertex in vertices)
    min_y = min(vertex.y for vertex in vertices)
    max_y = max(vertex.y for vertex in vertices)
    min_z = min(vertex.z for vertex in vertices)
    max_z = max(vertex.z for vertex in vertices)
    span = max(max_x - min_x, max_y - min_y, max_z - min_z)
    if span <= 0:
        return model
    center = Vec3((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0)
    scale = 2.0 / span
    meshes = []
    for mesh in model.meshes:
        normalized_vertices = tuple(
            Vec3(
                (vertex.x - center.x) * scale,
                (vertex.y - center.y) * scale,
                (vertex.z - center.z) * scale,
            )
            for vertex in mesh.vertices
        )
        meshes.append(
            Mesh3D(
                vertices=normalized_vertices,
                faces=mesh.faces,
                normals=mesh.normals,
                texcoords=mesh.texcoords,
                material=mesh.material,
            )
        )
    return Model3D(meshes=tuple(meshes), source=model.source)


__all__ = ["load_model", "load_model_async"]
