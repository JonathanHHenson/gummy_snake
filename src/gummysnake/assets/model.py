"""Backend-neutral 3D model loading helpers."""

from __future__ import annotations

import struct
from importlib import resources
from pathlib import Path

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.drawing.renderer3d import Mesh3D, Model3D, Vec3
from gummysnake.exceptions import ArgumentValidationError


def load_model(
    path: str | Path,
    normalize: bool = False,
    *,
    package: str | None = None,
) -> Model3D:
    """Load a Wavefront OBJ asset into backend-neutral mesh data.
    
    Args:
        path: The path value. Expected type: `str | Path`.
        normalize: The normalize value. Expected type: `bool`. Defaults to `False`.
        package: The package value. Expected type: `str | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Model3D`.
    """

    source_path = Path(str(path))
    if source_path.suffix.lower() == ".stl":
        payload, source = _read_binary_asset(path, package=package)
        return _parse_stl(payload, source=source, normalize=normalize)
    obj_text, source = _read_text_asset(path, package=package)
    return _parse_obj_rust(obj_text, source=source, normalize=normalize)


async def load_model_async(
    path: str | Path,
    normalize: bool = False,
    *,
    package: str | None = None,
) -> Model3D:
    """Load and return a model asynchronously.
    
    Args:
        path: The path value. Expected type: `str | Path`.
        normalize: The normalize value. Expected type: `bool`. Defaults to `False`.
        package: The package value. Expected type: `str | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
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


def _read_binary_asset(path: str | Path, *, package: str | None) -> tuple[bytes, Path]:
    if package is None:
        source = resolve_asset_path(path)
        if not source.exists():
            raise ArgumentValidationError(f"Model file does not exist: {source!s}.")
        try:
            return source.read_bytes(), source
        except OSError as exc:
            raise ArgumentValidationError(f"Could not load model {source!s}.") from exc

    resource = resources.files(package).joinpath(str(path))
    if not resource.is_file():
        raise ArgumentValidationError(
            f"Model resource {str(path)!r} was not found in package {package!r}."
        )
    try:
        return resource.read_bytes(), Path(f"{package}:{path}")
    except OSError as exc:
        raise ArgumentValidationError(
            f"Could not load model resource {str(path)!r} from package {package!r}."
        ) from exc


def _parse_stl(payload: bytes, *, source: Path, normalize: bool) -> Model3D:
    try:
        model = _parse_binary_stl(payload, source=source)
    except ArgumentValidationError:
        model = _parse_ascii_stl(payload, source=source)
    if normalize:
        model = Model3D(meshes=tuple(mesh.normalized() for mesh in model.meshes), source=source)
    return model


def _parse_binary_stl(payload: bytes, *, source: Path) -> Model3D:
    if len(payload) < 84:
        raise ArgumentValidationError(f"STL model {source!s} is too small to be binary STL.")
    triangle_count = struct.unpack_from("<I", payload, 80)[0]
    expected = 84 + triangle_count * 50
    if expected != len(payload):
        raise ArgumentValidationError(f"STL model {source!s} is not a valid binary STL payload.")
    vertices: list[Vec3] = []
    faces: list[tuple[int, int, int]] = []
    normals: list[Vec3] = []
    offset = 84
    for _ in range(triangle_count):
        nx, ny, nz = struct.unpack_from("<fff", payload, offset)
        offset += 12
        face = []
        for _ in range(3):
            x, y, z = struct.unpack_from("<fff", payload, offset)
            offset += 12
            vertices.append(Vec3(float(x), float(y), float(z)))
            normals.append(Vec3(float(nx), float(ny), float(nz)))
            face.append(len(vertices) - 1)
        faces.append((face[0], face[1], face[2]))
        offset += 2
    return Model3D(meshes=(Mesh3D(vertices=vertices, faces=faces, normals=normals),), source=source)


def _parse_ascii_stl(payload: bytes, *, source: Path) -> Model3D:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArgumentValidationError(f"STL model {source!s} is not valid ASCII STL.") from exc
    vertices: list[Vec3] = []
    faces: list[tuple[int, int, int]] = []
    current: list[int] = []
    for raw_line in text.splitlines():
        parts = raw_line.strip().split()
        if len(parts) == 4 and parts[0].lower() == "vertex":
            try:
                vertex = Vec3(float(parts[1]), float(parts[2]), float(parts[3]))
            except ValueError as exc:
                raise ArgumentValidationError(f"Invalid STL vertex in {source!s}.") from exc
            vertices.append(vertex)
            current.append(len(vertices) - 1)
            if len(current) == 3:
                faces.append((current[0], current[1], current[2]))
                current = []
    if not faces:
        raise ArgumentValidationError(f"STL model {source!s} contains no facets.")
    mesh = Mesh3D(vertices=vertices, faces=faces).with_computed_normals()
    return Model3D(meshes=(mesh,), source=source)


def _parse_obj_rust(text: str, *, source: Path, normalize: bool) -> Model3D:
    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
    try:
        handle = runtime.parse_obj_model_handle(text, str(source), normalize)
    except ValueError as exc:
        raise ArgumentValidationError(str(exc)) from exc
    return Model3D(meshes=None, source=source, rust_handle=handle)


__all__ = ["load_model", "load_model_async"]
