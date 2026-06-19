"""Backend-neutral shader loading helpers."""

from __future__ import annotations

from pathlib import Path

from p5.assets._paths import resolve_asset_path
from p5.drawing.renderer3d import Shader3D
from p5.exceptions import ArgumentValidationError


def load_shader(vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
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


def create_shader(vertex_source: str, fragment_source: str) -> Shader3D:
    if not isinstance(vertex_source, str) or not vertex_source.strip():
        raise ArgumentValidationError("create_shader() requires non-empty vertex shader source.")
    if not isinstance(fragment_source, str) or not fragment_source.strip():
        raise ArgumentValidationError("create_shader() requires non-empty fragment shader source.")
    return Shader3D(vertex_source=vertex_source, fragment_source=fragment_source)


loadShader = load_shader
createShader = create_shader


__all__ = ["create_shader", "createShader", "load_shader", "loadShader"]
