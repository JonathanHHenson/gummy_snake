"""Shared projection validation rules with caller-owned public errors."""

from __future__ import annotations

from collections.abc import Callable

from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    PerspectiveProjection,
    Projection3D,
)


def validate_projection_rules(
    projection: Projection3D,
    *,
    error: Callable[[str], Exception],
) -> None:
    """Validate shared projection invariants using the requested error type."""
    if projection.near <= 0:
        raise error("projection near plane must be positive.")
    if projection.far <= projection.near:
        raise error("projection far plane must be greater than the near plane.")
    if isinstance(projection, PerspectiveProjection):
        if projection.fov_y <= 0 or projection.fov_y >= 180:
            raise error("perspective fov_y must be between 0 and 180 degrees.")
        if projection.aspect is not None and projection.aspect <= 0:
            raise error("perspective aspect must be positive when provided.")
    elif isinstance(projection, FrustumProjection):
        if projection.left >= projection.right:
            raise error("frustum left must be less than right.")
        if projection.bottom >= projection.top:
            raise error("frustum bottom must be less than top.")
    elif projection.width <= 0 or projection.height <= 0:
        raise error("orthographic width and height must be positive.")
