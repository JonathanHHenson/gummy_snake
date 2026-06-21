"""Backend-neutral 3D model loading helpers."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.drawing.renderer3d import Model3D
from gummysnake.exceptions import ArgumentValidationError


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


def _parse_obj_rust(text: str, *, source: Path, normalize: bool) -> Model3D:
    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
    try:
        handle = runtime.parse_obj_model_handle(text, str(source), normalize)
    except ValueError as exc:
        raise ArgumentValidationError(str(exc)) from exc
    return Model3D(meshes=None, source=source, rust_handle=handle)


__all__ = ["load_model", "load_model_async"]
