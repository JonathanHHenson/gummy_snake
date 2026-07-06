"""Global-mode 3D model loading and export wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.api.current import require_context
from gummysnake.assets.model import load_model as _load_model
from gummysnake.assets.model import load_model_async as _load_model_async
from gummysnake.drawing.renderer3d import Model3D


def save_obj(model_value: Model3D, path: str | Path) -> Path:
    """Export a 3D model as a Wavefront OBJ file.

    Args:
        model_value: Model to export.
        path: Destination file path.

    Returns:
        The final path that was written.
    """

    return require_context().save_obj(model_value, path)


def save_stl(model_value: Model3D, path: str | Path) -> Path:
    """Export a 3D model as an STL file.

    Args:
        model_value: Model to export.
        path: Destination file path.

    Returns:
        The final path that was written.
    """

    return require_context().save_stl(model_value, path)


def load_model(path: str | Path, normalize: bool = False, *, package: str | None = None) -> Model3D:
    """Load a 3D model from disk or a package resource.

    Args:
        path: File path or package-resource path for the model.
        normalize: Whether to scale and center the model for easier drawing.
        package: Optional package name when loading from package resources.

    Returns:
        A ``Model3D`` ready for ``model()`` or geometry helpers.
    """

    return _load_model(path, normalize, package=package)


async def load_model_async(
    path: str | Path, normalize: bool = False, *, package: str | None = None
) -> Model3D:
    """Load a 3D model without blocking an async sketch callback.

    Args:
        path: File path or package-resource path for the model.
        normalize: Whether to scale and center the model for easier drawing.
        package: Optional package name when loading from package resources.

    Returns:
        A ``Model3D`` ready for ``model()`` or geometry helpers.
    """

    return await _load_model_async(path, normalize, package=package)


__all__ = [
    "save_obj",
    "save_stl",
    "load_model",
    "load_model_async",
]
