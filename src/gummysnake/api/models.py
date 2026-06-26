"""Global-mode 3D model loading and export wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.api.current import require_context
from gummysnake.assets.model import load_model as _load_model
from gummysnake.assets.model import load_model_async as _load_model_async
from gummysnake.drawing.renderer3d import Model3D


def save_obj(model_value: Model3D, path: str | Path) -> Path:
    return require_context().save_obj(model_value, path)


def save_stl(model_value: Model3D, path: str | Path) -> Path:
    return require_context().save_stl(model_value, path)


def load_model(path: str | Path, normalize: bool = False, *, package: str | None = None) -> Model3D:
    return _load_model(path, normalize, package=package)


async def load_model_async(
    path: str | Path, normalize: bool = False, *, package: str | None = None
) -> Model3D:
    return await _load_model_async(path, normalize, package=package)


__all__ = [
    "save_obj",
    "save_stl",
    "load_model",
    "load_model_async",
]
