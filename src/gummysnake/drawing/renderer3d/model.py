"""Model storage helpers for 3D rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gummysnake.drawing.renderer3d.mesh_model import Mesh3D, _mesh_rust_handle


class Model3D:
    """Loaded or generated model made of one or more meshes.

    Models loaded by the canvas runtime keep a Rust-owned model handle for hot
    render/export paths. The public ``meshes`` view stays available and is
    materialized lazily when Python code inspects geometry.
    """

    __slots__ = ("_meshes", "_rust_handle", "source")

    def __init__(
        self,
        meshes: tuple[Mesh3D, ...] | None = None,
        source: Path | None = None,
        *,
        rust_handle: Any | None = None,
    ) -> None:
        self._meshes = meshes
        self._rust_handle = rust_handle
        self.source = source

    @property
    def meshes(self) -> tuple[Mesh3D, ...]:
        if self._meshes is None:
            self._meshes = self._materialize_rust_meshes()
        return self._meshes

    def _materialize_rust_meshes(self) -> tuple[Mesh3D, ...]:
        if self._rust_handle is None:
            return ()
        return (Mesh3D.from_rust_handle(self._rust_handle.to_mesh_handle()),)


def _model_rust_handle(model: Model3D) -> Any | None:
    return model._rust_handle


def _ensure_model_rust_handle(model: Model3D) -> Any | None:
    """Return or create a Rust model handle when all meshes are Rust-backed."""
    if model._rust_handle is not None:
        return model._rust_handle
    meshes = model._meshes
    if not meshes:
        return None
    handles: list[Any] = []
    for mesh in meshes:
        handle = _mesh_rust_handle(mesh)
        if handle is None:
            return None
        handles.append(handle)

    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
    factory = getattr(runtime, "create_model3d_handle", None)
    if not callable(factory):
        raise RuntimeError(
            "The installed canvas runtime does not provide create_model3d_handle(). "
            "Rebuild gummy_canvas."
        )
    model._rust_handle = factory(handles, str(model.source or "gummy_snake_model"))
    return model._rust_handle
