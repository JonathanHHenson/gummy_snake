"""Backend-neutral shader loading helpers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.drawing.renderer3d import Shader3D
from gummysnake.exceptions import ArgumentValidationError


def load_shader(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    """Load and return shader.
    
    Args:
        vertex_path: The vertex path value. Expected type: `str | Path`.
        fragment_path: The fragment path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Shader3D`.
    """
    vertex_file = resolve_asset_path(vertex_path)
    fragment_file = resolve_asset_path(fragment_path)
    try:
        vertex_source = vertex_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArgumentValidationError(
            f"Could not read vertex shader source from {vertex_file!s}."
        ) from exc
    try:
        fragment_source = fragment_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArgumentValidationError(
            f"Could not read fragment shader source from {fragment_file!s}."
        ) from exc
    return Shader3D(
        vertex_source=vertex_source,
        fragment_source=fragment_source,
        vertex_path=vertex_file,
        fragment_path=fragment_file,
    )


async def load_shader_async(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    """Load and return a shader asynchronously.
    
    Args:
        vertex_path: The vertex path value. Expected type: `str | Path`.
        fragment_path: The fragment path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Shader3D`.
    """
    return load_shader(vertex_path, fragment_path)


def create_shader(vertex_source: str, fragment_source: str) -> Shader3D:
    """Create and return a shader value.
    
    Args:
        vertex_source: The vertex source value. Expected type: `str`.
        fragment_source: The fragment source value. Expected type: `str`.
    
    Returns:
        The return value. Type: `Shader3D`.
    """
    if not isinstance(vertex_source, str) or not vertex_source.strip():
        raise ArgumentValidationError("create_shader() requires non-empty vertex shader source.")
    if not isinstance(fragment_source, str) or not fragment_source.strip():
        raise ArgumentValidationError("create_shader() requires non-empty fragment shader source.")
    return Shader3D(vertex_source=vertex_source, fragment_source=fragment_source)


__all__ = ["create_shader", "load_shader", "load_shader_async"]
