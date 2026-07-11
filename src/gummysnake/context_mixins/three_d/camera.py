"""3D camera mixin compatibility module."""

from __future__ import annotations

from gummysnake.context_mixins.three_d._protocols import ThreeDContextHost
from gummysnake.context_mixins.three_d.camera_runtime.context_lookup import _three_d
from gummysnake.context_mixins.three_d.camera_runtime.math import (
    _add,
    _camera_basis,
    _camera_to_world,
    _cross,
    _dot,
    _length,
    _normalize,
    _rotate_around_axis,
    _scale,
    _sub,
    _world_to_camera,
)
from gummysnake.context_mixins.three_d.camera_runtime.mixin import ThreeDCameraMixin

__all__ = [
    "ThreeDCameraMixin",
    "ThreeDContextHost",
    "_add",
    "_camera_basis",
    "_camera_to_world",
    "_cross",
    "_dot",
    "_length",
    "_normalize",
    "_rotate_around_axis",
    "_scale",
    "_sub",
    "_three_d",
    "_world_to_camera",
]
