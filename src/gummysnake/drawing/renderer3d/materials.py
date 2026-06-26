"""3D light, texture, and material value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gummysnake.drawing.renderer3d.types import RGBA, Vec3


class LightKind(StrEnum):
    """3D light source kinds."""

    AMBIENT = "ambient"
    DIRECTIONAL = "directional"
    POINT = "point"


@dataclass(frozen=True, slots=True)
class Light3D:
    """Light description independent of a concrete shader implementation."""

    kind: LightKind
    color: RGBA = (1.0, 1.0, 1.0, 1.0)
    intensity: float = 1.0
    position: Vec3 | None = None
    direction: Vec3 | None = None


@dataclass(frozen=True, slots=True)
class Texture3D:
    """Texture handle placeholder for future 3D renderers."""

    source: object
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class Material3D:
    """Material values shared by model, primitive, and shader workflows."""

    base_color: RGBA = (1.0, 1.0, 1.0, 1.0)
    emissive_color: RGBA = (0.0, 0.0, 0.0, 1.0)
    specular_color: RGBA = (1.0, 1.0, 1.0, 1.0)
    shininess: float = 32.0
    texture: Texture3D | None = None
