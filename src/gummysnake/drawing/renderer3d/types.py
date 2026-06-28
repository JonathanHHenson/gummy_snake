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
        """To array.
        
        Args:
            copy: The copy value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            The return value. Type: `Any`.
        """
        np = _require_numpy("Vec3.to_array()")
        array = np.array((self.x, self.y, self.z), dtype=np.float64)
        return array.copy() if copy else array

    @classmethod
    def from_array(cls, value: Any) -> Vec3:
        """From array.
        
        Args:
            value: The value value. Expected type: `Any`.
        
        Returns:
            The return value. Type: `Vec3`.
        """
        np = _require_numpy("Vec3.from_array()")
        array = np.asarray(value, dtype=np.float64)
        if array.shape != (3,):
            raise ValueError("Vec3 arrays must have shape (3,).")
        return cls(float(array[0]), float(array[1]), float(array[2]))


@dataclass(frozen=True, slots=True)
class Camera3D:
    """Camera orientation for WEBGL-style renderers."""

    eye: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 500.0))
    target: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 0.0))
    up: Vec3 = field(default_factory=lambda: Vec3(0.0, 1.0, 0.0))

    @property
    def center(self) -> Vec3:
        """Center.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Vec3`.
        """
        return self.target

    def copy(self) -> Camera3D:
        """Copy.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        return Camera3D(eye=self.eye, target=self.target, up=self.up)

    def set(
        self, *, eye: Vec3 | None = None, target: Vec3 | None = None, up: Vec3 | None = None
    ) -> Camera3D:
        """Set.
        
        Args:
            eye: The eye value. Expected type: `Vec3 | None`. Defaults to `None`.
            target: The target value. Expected type: `Vec3 | None`. Defaults to `None`.
            up: The up value. Expected type: `Vec3 | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        return Camera3D(
            eye=self.eye if eye is None else eye,
            target=self.target if target is None else target,
            up=self.up if up is None else up,
        )

    def look_at(self, x: float, y: float, z: float) -> Camera3D:
        """Look at.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            z: The z value. Expected type: `float`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        return self.set(target=Vec3(float(x), float(y), float(z)))

    def move(self, x: float, y: float, z: float) -> Camera3D:
        """Move.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            z: The z value. Expected type: `float`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        delta = Vec3(float(x), float(y), float(z))
        return Camera3D(
            eye=Vec3(self.eye.x + delta.x, self.eye.y + delta.y, self.eye.z + delta.z),
            target=Vec3(self.target.x + delta.x, self.target.y + delta.y, self.target.z + delta.z),
            up=self.up,
        )

    def interpolate(self, other: Camera3D, amount: float) -> Camera3D:
        """Interpolate.
        
        Args:
            other: The other value. Expected type: `Camera3D`.
            amount: The amount value. Expected type: `float`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        t = float(amount)
        return Camera3D(
            eye=_lerp_vec3(self.eye, other.eye, t),
            target=_lerp_vec3(self.target, other.target, t),
            up=_lerp_vec3(self.up, other.up, t),
        )


@dataclass(frozen=True, slots=True)
class PerspectiveProjection:
    """Perspective projection described in Gummy Snake-style degrees."""

    fov_y: float = 60.0
    aspect: float | None = None
    near: float = 0.1
    far: float = 10_000.0


@dataclass(frozen=True, slots=True)
class FrustumProjection:
    """Perspective frustum described by near-plane extents."""

    left: float
    right: float
    bottom: float
    top: float
    near: float = 0.1
    far: float = 10_000.0


@dataclass(frozen=True, slots=True)
class OrthographicProjection:
    """Orthographic projection dimensions in logical canvas units."""

    width: float
    height: float
    near: float = 0.1
    far: float = 10_000.0


type Projection3D = PerspectiveProjection | OrthographicProjection | FrustumProjection


def _lerp_vec3(a: Vec3, b: Vec3, t: float) -> Vec3:
    return Vec3(
        a.x + (b.x - a.x) * t,
        a.y + (b.y - a.y) * t,
        a.z + (b.z - a.z) * t,
    )
