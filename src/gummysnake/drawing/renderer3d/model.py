"""Model storage helpers for 3D rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gummysnake.drawing.renderer3d.mesh import Mesh3D
from gummysnake.drawing.renderer3d.types import Vec3


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
        """Meshes.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[Mesh3D, ...]`.
        """
        if self._meshes is None:
            self._meshes = self._materialize_rust_meshes()
        return self._meshes

    def _materialize_rust_meshes(self) -> tuple[Mesh3D, ...]:
        if self._rust_handle is None:
            return ()
        if hasattr(self._rust_handle, "to_mesh_handle"):
            return (Mesh3D.from_rust_handle(self._rust_handle.to_mesh_handle()),)
        payload = self._rust_handle.to_mesh_payload()
        vertices = tuple(Vec3(float(x), float(y), float(z)) for x, y, z in payload["vertices"])
        faces = tuple(tuple(int(index) for index in face) for face in payload["faces"])
        texcoords = tuple((float(u), float(v)) for u, v in payload.get("texcoords", ()))
        normals = tuple(
            Vec3(float(x), float(y), float(z)) for x, y, z in payload.get("normals", ())
        )
        return (Mesh3D(vertices=vertices, faces=faces, normals=normals, texcoords=texcoords),)


def _model_rust_handle(model: Model3D) -> Any | None:
    return model._rust_handle
