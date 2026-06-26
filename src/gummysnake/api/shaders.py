"""Global-mode shader loading and binding wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.api.current import require_context
from gummysnake.assets.shader import create_shader as _create_shader
from gummysnake.assets.shader import load_shader as _load_shader
from gummysnake.assets.shader import load_shader_async as _load_shader_async
from gummysnake.drawing.renderer3d import Shader3D


def load_shader(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    return _load_shader(vertex_path, fragment_path)


async def load_shader_async(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
    return await _load_shader_async(vertex_path, fragment_path)


def create_shader(vertex_source: str, fragment_source: str) -> Shader3D:
    return _create_shader(vertex_source, fragment_source)


def shader(shader_program: Shader3D) -> None:
    require_context().shader(shader_program)


def reset_shader() -> None:
    require_context().reset_shader()


__all__ = [
    "load_shader",
    "load_shader_async",
    "create_shader",
    "shader",
    "reset_shader",
]
