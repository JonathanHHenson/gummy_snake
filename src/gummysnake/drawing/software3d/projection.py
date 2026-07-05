"""Projection validation helpers for software 3D."""

from __future__ import annotations

from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    PerspectiveProjection,
    Projection3D,
)
from gummysnake.exceptions import ArgumentValidationError


def validate_projection(projection: Projection3D) -> None:
    if projection.near <= 0:
        raise ArgumentValidationError("projection near plane must be positive.")
    if projection.far <= projection.near:
        raise ArgumentValidationError("projection far plane must be greater than the near plane.")
    if isinstance(projection, PerspectiveProjection):
        if projection.fov_y <= 0 or projection.fov_y >= 180:
            raise ArgumentValidationError("perspective fov_y must be between 0 and 180 degrees.")
        if projection.aspect is not None and projection.aspect <= 0:
            raise ArgumentValidationError("perspective aspect must be positive when provided.")
    elif isinstance(projection, FrustumProjection):
        if projection.left >= projection.right:
            raise ArgumentValidationError("frustum left must be less than right.")
        if projection.bottom >= projection.top:
            raise ArgumentValidationError("frustum bottom must be less than top.")
    elif projection.width <= 0 or projection.height <= 0:
        raise ArgumentValidationError("orthographic width and height must be positive.")
