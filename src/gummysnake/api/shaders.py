"""Global-mode shader loading and binding wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.api.current import require_context
from gummysnake.assets.shader import create_shader as _create_shader
from gummysnake.assets.shader import load_shader as _load_shader
from gummysnake.assets.shader import load_shader_async as _load_shader_async
from gummysnake.drawing.renderer3d import Shader3D, ShaderUniformValue


def load_shader(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    """Load a vertex/fragment shader pair from files.

    Args:
        vertex_path: Path to the vertex shader source file.
        fragment_path: Path to the fragment shader source file.

    Returns:
        A shader object that can be passed to ``shader()``.
    """

    return _load_shader(vertex_path, fragment_path)


async def load_shader_async(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    """Load a shader pair without blocking an async sketch callback.

    Args:
        vertex_path: Path to the vertex shader source file.
        fragment_path: Path to the fragment shader source file.

    Returns:
        A shader object that can be passed to ``shader()``.
    """

    return await _load_shader_async(vertex_path, fragment_path)


def create_shader(vertex_source: str, fragment_source: str) -> Shader3D:
    """Create a shader object from source strings.

    Args:
        vertex_source: Vertex shader source code.
        fragment_source: Fragment shader source code.

    Returns:
        A shader object that can be passed to ``shader()``.
    """

    return _create_shader(vertex_source, fragment_source)


def shader(shader_program: Shader3D) -> None:
    """Set the shader used by later 3D drawing calls.

    Args:
        shader_program: Shader object returned by ``load_shader()`` or ``create_shader()``.
    """

    require_context().shader(shader_program)


def reset_shader() -> None:
    """Return later 3D drawing calls to the default shader."""

    require_context().reset_shader()


def set_shader_uniform(name: str, value: ShaderUniformValue) -> None:
    """Set one uniform value on the active shader.

    Args:
        name: Uniform variable name in the shader.
        value: Uniform value to send to the renderer.
    """

    require_context().set_shader_uniform(name, value)


__all__ = [
    "load_shader",
    "load_shader_async",
    "create_shader",
    "shader",
    "reset_shader",
    "set_shader_uniform",
]
