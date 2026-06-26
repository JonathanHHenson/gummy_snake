"""Backend-agnostic 3D value types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gummysnake.drawing.renderer3d._numpy import _require_numpy

type RGBA = tuple[float, float, float, float]
type Matrix4 = tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class Vec3:
    """Simple immutable 3D vector used by renderer contracts and prototypes."""

    x: float
    y: float
    z: float

    def __array__(self, dtype: Any = None, copy: bool | None = None) -> Any:
        np = _require_numpy("Vec3.__array__()")
        array = np.array((self.x, self.y, self.z), dtype=np.float64)
        if dtype is not None:
            return array.astype(dtype, copy=False if copy is None else copy)
        if copy is False:
            return array
        return array.copy() if copy else array

    def to_array(self, *, copy: bool = True) -> Any:
        np = _require_numpy("Vec3.to_array()")
        array = np.array((self.x, self.y, self.z), dtype=np.float64)
        return array.copy() if copy else array

    @classmethod
    def from_array(cls, value: Any) -> Vec3:
        np = _require_numpy("Vec3.from_array()")
        array = np.asarray(value, dtype=np.float64)
        if array.shape != (3,):
            raise ValueError("Vec3 arrays must have shape (3,).")
        return cls(float(array[0]), float(array[1]), float(array[2]))


@dataclass(frozen=True, slots=True)
class Camera3D:
    """Camera orientation for future WEBGL-like renderers."""

    eye: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 500.0))
    target: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 0.0))
    up: Vec3 = field(default_factory=lambda: Vec3(0.0, 1.0, 0.0))


@dataclass(frozen=True, slots=True)
class PerspectiveProjection:
    """Perspective projection described in Gummy Snake-style degrees."""

    fov_y: float = 60.0
    aspect: float | None = None
    near: float = 0.1
    far: float = 10_000.0


@dataclass(frozen=True, slots=True)
class OrthographicProjection:
    """Orthographic projection dimensions in logical canvas units."""

    width: float
    height: float
    near: float = 0.1
    far: float = 10_000.0


type Projection3D = PerspectiveProjection | OrthographicProjection
