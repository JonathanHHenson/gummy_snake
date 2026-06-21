"""Shared software 3D public value types."""

from __future__ import annotations

from dataclasses import dataclass

from gummysnake.assets.image import Image as CanvasImage
from gummysnake.drawing.renderer3d import Vec3

type ScreenPoint = tuple[float, float]
type RGBAFloat = tuple[float, float, float, float]
type UVCoord = tuple[float, float]


@dataclass(frozen=True, slots=True)
class ProjectedFace:
    points: tuple[ScreenPoint, ...]
    depth: float
    normal: Vec3
    center: Vec3
    texcoords: tuple[UVCoord, ...] | None = None
    texture: CanvasImage | None = None


@dataclass(frozen=True, slots=True)
class ShadedFace:
    points: tuple[ScreenPoint, ...]
    color: RGBAFloat
    depth: float
    texcoords: tuple[UVCoord, ...] | None = None
    texture: CanvasImage | None = None
