"""3D mesh compatibility module."""

from __future__ import annotations

from gummysnake.drawing.renderer3d.mesh_model.geometry import _mesh_rust_handle
from gummysnake.drawing.renderer3d.mesh_model.mesh import Mesh3D
from gummysnake.drawing.renderer3d.mesh_model.python_data import MeshPythonData

__all__ = ["Mesh3D", "MeshPythonData", "_mesh_rust_handle"]
