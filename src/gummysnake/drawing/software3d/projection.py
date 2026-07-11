"""Projection validation helpers for software 3D."""

from __future__ import annotations

from gummysnake.drawing.renderer3d._projection_validation import validate_projection_rules
from gummysnake.drawing.renderer3d.types import Projection3D
from gummysnake.exceptions import ArgumentValidationError


def validate_projection(projection: Projection3D) -> None:
    """Validate projections with software-3D's public error contract."""
    validate_projection_rules(projection, error=ArgumentValidationError)
