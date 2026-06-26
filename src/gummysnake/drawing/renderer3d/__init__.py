"""Backend-agnostic 3D renderer protocol and value objects.

Concrete 3D support lives in backend-specific renderers, while public APIs can
depend on these Python-native data structures without importing OpenGL, Pyglet,
NumPy, or any other rendering package.
"""

from __future__ import annotations

from gummysnake.drawing.renderer3d.materials import (
    Light3D,
    LightKind,
    Material3D,
    Texture3D,
)
from gummysnake.drawing.renderer3d.mesh import Mesh3D, _mesh_rust_handle
from gummysnake.drawing.renderer3d.model import Model3D, _model_rust_handle
from gummysnake.drawing.renderer3d.protocols import Renderer3D
from gummysnake.drawing.renderer3d.shader import Shader3D, ShaderUniformValue
from gummysnake.drawing.renderer3d.types import (
    RGBA,
    Camera3D,
    Matrix4,
    OrthographicProjection,
    PerspectiveProjection,
    Projection3D,
    Vec3,
)

__all__ = [
    "Camera3D",
    "Light3D",
    "LightKind",
    "Material3D",
    "Matrix4",
    "Mesh3D",
    "Model3D",
    "OrthographicProjection",
    "PerspectiveProjection",
    "Projection3D",
    "RGBA",
    "Renderer3D",
    "Shader3D",
    "ShaderUniformValue",
    "Texture3D",
    "Vec3",
    "_mesh_rust_handle",
    "_model_rust_handle",
]
