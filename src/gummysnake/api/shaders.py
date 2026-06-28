"""Global-mode shader loading and binding wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.api.current import require_context
from gummysnake.assets.shader import create_shader as _create_shader
from gummysnake.assets.shader import load_shader as _load_shader
from gummysnake.assets.shader import load_shader_async as _load_shader_async
from gummysnake.drawing.renderer3d import Shader3D, ShaderUniformValue


def load_shader(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    """Load and return shader.
    
    Args:
        vertex_path: The vertex path value. Expected type: `str | Path`.
        fragment_path: The fragment path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Shader3D`.
    """
    return _load_shader(vertex_path, fragment_path)


async def load_shader_async(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    """Load and return a shader asynchronously.
    
    Args:
        vertex_path: The vertex path value. Expected type: `str | Path`.
        fragment_path: The fragment path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Shader3D`.
    """
    return await _load_shader_async(vertex_path, fragment_path)


def create_shader(vertex_source: str, fragment_source: str) -> Shader3D:
    """Create and return a shader value.
    
    Args:
        vertex_source: The vertex source value. Expected type: `str`.
        fragment_source: The fragment source value. Expected type: `str`.
    
    Returns:
        The return value. Type: `Shader3D`.
    """
    return _create_shader(vertex_source, fragment_source)


def shader(shader_program: Shader3D) -> None:
    """Shader using the active shaders context.
    
    Args:
        shader_program: The shader program value. Expected type: `Shader3D`.
    
    Returns:
        None.
    """
    require_context().shader(shader_program)


def reset_shader() -> None:
    """Reset shader using the active shaders context.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().reset_shader()


def set_shader_uniform(name: str, value: ShaderUniformValue) -> None:
    """Set the shader uniform value.
    
    Args:
        name: The name value. Expected type: `str`.
        value: The value value. Expected type: `ShaderUniformValue`.
    
    Returns:
        None.
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
