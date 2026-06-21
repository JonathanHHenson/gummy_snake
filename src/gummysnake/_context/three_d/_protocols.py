"""Structural protocols for composed 3D SketchContext mixins."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from gummysnake.core.color import Color
from gummysnake.drawing.renderer3d import Material3D, Texture3D


class ThreeDContextHost(Protocol):
    renderer: Any
    backend: Any
    state: Any

    def _require_webgl_mode(self, api_name: str) -> None: ...
    def _numeric_values(self, values: Sequence[object]) -> tuple[float, ...]: ...
    def _angle(self, value: float) -> float: ...
    def _color_to_rgba(self, color: Color) -> tuple[float, float, float, float]: ...
    def color(self, *args: object) -> Color: ...
    def _split_color_args(
        self, args: Sequence[object], *, tail_count: int
    ) -> tuple[Color, tuple[float, ...]]: ...
    def _replace_material(
        self,
        *,
        base_color: tuple[float, float, float, float] | None = None,
        specular_color: tuple[float, float, float, float] | None = None,
        shininess: float | None = None,
        texture: Texture3D | None | object = None,
    ) -> Material3D: ...
    def _effective_3d_material(self) -> Material3D: ...
    def model(self, shape: object) -> None: ...
