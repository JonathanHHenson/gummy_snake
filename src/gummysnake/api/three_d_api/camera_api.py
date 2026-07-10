"""Global-mode WEBGL-style 3D camera, lighting, material, and primitive wrappers."""

from __future__ import annotations

from collections.abc import Callable
from typing import overload

from gummysnake import constants as c
from gummysnake.api._context_call import context_call as _context_call
from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.drawing.renderer3d import Camera3D, Mesh3D, Model3D, Vec3
from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
    VertexPropertyValue,
)

Number = int | float
ColorValue = Color | str
CameraArg = Camera3D | Number
ColorArg = ColorValue | Number


@overload
def create_camera() -> Camera3D: ...


@overload
def create_camera(camera: Camera3D, /) -> Camera3D: ...


@overload
def create_camera(
    eye_x: Number,
    eye_y: Number,
    eye_z: Number,
    center_x: Number,
    center_y: Number,
    center_z: Number,
    up_x: Number,
    up_y: Number,
    up_z: Number,
    /,
) -> Camera3D: ...


def create_camera(*args: CameraArg) -> Camera3D:
    """Create and select a 3D camera for the active sketch.

    Args:
        *args: Omit for a default camera, pass an existing ``Camera3D``, or
            pass eye, target, and up-vector coordinates as nine numbers.

    Returns:
        The newly selected ``Camera3D``.
    """

    return require_context().create_camera(*args)


@overload
def camera() -> Camera3D: ...


@overload
def camera(camera: Camera3D, /) -> Camera3D: ...


@overload
def camera(
    eye_x: Number,
    eye_y: Number,
    eye_z: Number,
    center_x: Number,
    center_y: Number,
    center_z: Number,
    up_x: Number,
    up_y: Number,
    up_z: Number,
    /,
) -> Camera3D: ...


def camera(*args: CameraArg) -> Camera3D:
    """Create or replace the current 3D camera.

    Args:
        *args: Omit for a default camera, pass an existing ``Camera3D``, or
            pass eye, target, and up-vector coordinates as nine numbers.

    Returns:
        The current ``Camera3D`` after the change.
    """

    return require_context().camera(*args)


def set_camera(camera_value: Camera3D) -> Camera3D:
    """Make an existing camera the active 3D camera.

    Args:
        camera_value: The ``Camera3D`` to use for later 3D drawing.

    Returns:
        The same camera that was selected.
    """

    return require_context().set_camera(camera_value)


def roll(angle: Number) -> Camera3D:
    """Rotate the active camera around the direction it is looking.

    Args:
        angle: Amount to roll, using the sketch's current angle mode.

    Returns:
        The updated active ``Camera3D``.
    """

    return require_context().roll(angle)


def world_to_screen(x: Number, y: Number, z: Number) -> tuple[float, float, float]:
    """Convert a 3D world position to logical screen coordinates.

    Args:
        x: World-space x coordinate.
        y: World-space y coordinate.
        z: World-space z coordinate.

    Returns:
        ``(screen_x, screen_y, depth)`` for the current camera and projection.
    """

    return require_context().world_to_screen(x, y, z)


def screen_to_world(x: Number, y: Number, depth: Number = 0.0) -> Vec3:
    """Convert logical screen coordinates back into 3D world space.

    Args:
        x: Screen x coordinate in logical sketch pixels.
        y: Screen y coordinate in logical sketch pixels.
        depth: Depth between the near plane (``0``) and far plane (``1``).

    Returns:
        A ``Vec3`` position in world coordinates.
    """

    return require_context().screen_to_world(x, y, depth)


@overload
def perspective() -> PerspectiveProjection: ...


@overload
def perspective(fov: Number, /) -> PerspectiveProjection: ...


@overload
def perspective(fov: Number, aspect: Number, /) -> PerspectiveProjection: ...


@overload
def perspective(fov: Number, aspect: Number, near: Number, /) -> PerspectiveProjection: ...


@overload
def perspective(
    fov: Number, aspect: Number, near: Number, far: Number, /
) -> PerspectiveProjection: ...


def perspective(*args: Number) -> PerspectiveProjection:
    """Use a perspective projection for 3D drawing.

    Args:
        *args: Optional ``fov``, ``aspect``, ``near``, and ``far`` values.
            ``fov`` uses the sketch's current angle mode.

    Returns:
        The active ``PerspectiveProjection``.
    """

    return require_context().perspective(*args)


@overload
def ortho() -> OrthographicProjection: ...


@overload
def ortho(width: Number, height: Number, /) -> OrthographicProjection: ...


@overload
def ortho(
    width: Number, height: Number, near: Number, far: Number, /
) -> OrthographicProjection: ...


def ortho(*args: Number) -> OrthographicProjection:
    """Use an orthographic projection for 3D drawing.

    Args:
        *args: Omit to use the canvas size, pass ``width`` and ``height``,
            or pass ``width``, ``height``, ``near``, and ``far``.

    Returns:
        The active ``OrthographicProjection``.
    """

    return require_context().ortho(*args)


def frustum(
    left: Number,
    right: Number,
    bottom: Number,
    top: Number,
    near: Number = 0.1,
    far: Number = 10_000.0,
) -> FrustumProjection:
    """Use a custom perspective viewing frustum.

    Args:
        left: Left edge of the near clipping plane.
        right: Right edge of the near clipping plane.
        bottom: Bottom edge of the near clipping plane.
        top: Top edge of the near clipping plane.
        near: Distance to the near clipping plane.
        far: Distance to the far clipping plane.

    Returns:
        The active ``FrustumProjection``.
    """

    return require_context().frustum(left, right, bottom, top, near, far)
