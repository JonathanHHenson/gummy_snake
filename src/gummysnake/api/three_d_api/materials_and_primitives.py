"""Global-mode WEBGL material and primitive wrappers."""

from __future__ import annotations

from collections.abc import Callable

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.drawing.renderer3d import Mesh3D, Model3D
from gummysnake.drawing.renderer3d.types import VertexPropertyValue


def texture_wrap(
    wrap_x: c.TextureWrapMode | str | None = None,
    wrap_y: c.TextureWrapMode | str | None = None,
) -> tuple[c.TextureWrapMode, c.TextureWrapMode]:
    """Set or read how textures behave outside their normal range.

    Args:
        wrap_x: Horizontal wrap mode such as ``CLAMP``, ``REPEAT``, or
            ``MIRROR``. Omit to read the current modes.
        wrap_y: Optional vertical wrap mode. If omitted while ``wrap_x`` is
            provided, the horizontal mode is used for both directions.

    Returns:
        ``(wrap_x, wrap_y)`` texture wrap modes.
    """

    return require_context().texture_wrap(wrap_x, wrap_y)


def texture(image: Image) -> None:
    """Apply an image texture to later 3D geometry."""

    require_context().texture(image)


def plane(width: float, height: float | None = None) -> None:
    """Draw a flat rectangular 3D plane."""

    require_context().plane(width, height)


def box(width: float, height: float | None = None, depth: float | None = None) -> None:
    """Draw a 3D box."""

    require_context().box(width, height, depth)


def sphere(radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
    """Draw a 3D sphere."""

    require_context().sphere(radius, detail_x, detail_y)


def ellipsoid(
    radius_x: float,
    radius_y: float | None = None,
    radius_z: float | None = None,
    detail_x: int = 24,
    detail_y: int = 16,
) -> None:
    """Draw a stretched sphere with separate radii per axis."""

    require_context().ellipsoid(radius_x, radius_y, radius_z, detail_x, detail_y)


def cylinder(
    radius: float,
    height: float,
    detail_x: int = 24,
    detail_y: int = 1,
    *,
    bottom_cap: bool = True,
    top_cap: bool = True,
) -> None:
    """Draw a 3D cylinder."""

    require_context().cylinder(
        radius, height, detail_x, detail_y, bottom_cap=bottom_cap, top_cap=top_cap
    )


def cone(
    radius: float,
    height: float,
    detail_x: int = 24,
    detail_y: int = 1,
    *,
    cap: bool = True,
) -> None:
    """Draw a 3D cone."""

    require_context().cone(radius, height, detail_x, detail_y, cap=cap)


def torus(
    radius: float,
    tube_radius: float | None = None,
    detail_x: int = 24,
    detail_y: int = 12,
) -> None:
    """Draw a donut-shaped 3D torus."""

    require_context().torus(radius, tube_radius, detail_x, detail_y)


def create_model(mesh: Mesh3D | Model3D) -> Model3D:
    """Create a drawable 3D model from a mesh or model.

    Args:
        mesh: A ``Mesh3D`` to wrap, or an existing ``Model3D`` to reuse.

    Returns:
        A ``Model3D`` ready to draw with ``model()``.
    """

    return require_context().create_model(mesh)


def normal(x: float, y: float, z: float) -> None:
    """Set the current normal direction for custom 3D geometry."""

    require_context().normal(x, y, z)


def vertex_property(name: str, value: VertexPropertyValue) -> None:
    """Set a named property for custom 3D vertices."""

    require_context().vertex_property(name, value)


def build_geometry(callback: Callable[[], object]) -> Model3D:
    """Capture 3D drawing commands from a callback into a model.

    Args:
        callback: Function that creates 3D geometry, such as ``box()`` or
            ``model()`` calls, or returns a ``Mesh3D`` or ``Model3D``.

    Returns:
        The captured geometry as a ``Model3D``.
    """

    return require_context().build_geometry(callback)


def free_geometry(model_value: Model3D) -> None:
    """Release retained runtime resources for a model."""

    require_context().free_geometry(model_value)


def flip_u(mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
    """Flip texture coordinates horizontally on a mesh or model.

    Args:
        mesh_or_model: The ``Mesh3D`` or ``Model3D`` to adjust.

    Returns:
        A mesh or model of the same kind with U coordinates flipped.
    """

    return require_context().flip_u(mesh_or_model)


def flip_v(mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
    """Flip texture coordinates vertically on a mesh or model.

    Args:
        mesh_or_model: The ``Mesh3D`` or ``Model3D`` to adjust.

    Returns:
        A mesh or model of the same kind with V coordinates flipped.
    """

    return require_context().flip_v(mesh_or_model)


def model(shape: Mesh3D | Model3D) -> None:
    """Draw a 3D mesh or model with the current transform and material."""

    require_context().model(shape)


__all__ = [
    "texture_wrap",
    "texture",
    "plane",
    "box",
    "sphere",
    "ellipsoid",
    "cylinder",
    "cone",
    "torus",
    "create_model",
    "normal",
    "vertex_property",
    "build_geometry",
    "free_geometry",
    "flip_u",
    "flip_v",
    "model",
]
