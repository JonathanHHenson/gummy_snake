"""Global-mode 3D model loading and export wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.api.current import require_context
from gummysnake.assets.model import load_model as _load_model
from gummysnake.assets.model import load_model_async as _load_model_async
from gummysnake.drawing.renderer3d import Model3D


def save_obj(model_value: Model3D, path: str | Path) -> Path:
    """Save obj data to the requested destination.
    
    Args:
        model_value: The model value value. Expected type: `Model3D`.
        path: The path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Path`.
    """
    return require_context().save_obj(model_value, path)


def save_stl(model_value: Model3D, path: str | Path) -> Path:
    """Save stl data to the requested destination.
    
    Args:
        model_value: The model value value. Expected type: `Model3D`.
        path: The path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Path`.
    """
    return require_context().save_stl(model_value, path)


def load_model(path: str | Path, normalize: bool = False, *, package: str | None = None) -> Model3D:
    """Load and return model.
    
    Args:
        path: The path value. Expected type: `str | Path`.
        normalize: The normalize value. Expected type: `bool`. Defaults to `False`.
        package: The package value. Expected type: `str | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
    return _load_model(path, normalize, package=package)


async def load_model_async(
    path: str | Path, normalize: bool = False, *, package: str | None = None
) -> Model3D:
    """Load and return a model asynchronously.
    
    Args:
        path: The path value. Expected type: `str | Path`.
        normalize: The normalize value. Expected type: `bool`. Defaults to `False`.
        package: The package value. Expected type: `str | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
    return await _load_model_async(path, normalize, package=package)


__all__ = [
    "save_obj",
    "save_stl",
    "load_model",
    "load_model_async",
]
