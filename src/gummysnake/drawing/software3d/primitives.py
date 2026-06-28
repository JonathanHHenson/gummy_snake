"""Generated primitive meshes for software 3D."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol, cast

from gummysnake.drawing.renderer3d import Model3D
from gummysnake.exceptions import ArgumentValidationError

_MESH_CACHE_SIZE = 256


class _CachedModelFactory(Protocol):
    def cache_clear(self) -> None: ...
    def cache_info(self) -> Any: ...


def _rust_primitive_model(function_name: str, *args: object) -> Model3D:
    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
    factory = getattr(runtime, function_name, None)
    if not callable(factory):
        raise ArgumentValidationError(
            f"The installed canvas runtime does not provide {function_name}(). "
            "Rebuild gummy_canvas."
        )
    try:
        return Model3D(meshes=None, rust_handle=factory(*args))
    except ValueError as exc:
        raise ArgumentValidationError(str(exc)) from exc


def clear_primitive_model_cache() -> None:
    """Clear primitive model cache.
    
    Args:
        None.
    
    Returns:
        None.
    """
    for fn in (
        plane_model,
        box_model,
        sphere_model,
        ellipsoid_model,
        cylinder_model,
        cone_model,
        torus_model,
    ):
        cast(_CachedModelFactory, fn).cache_clear()


def primitive_model_cache_info() -> dict[str, Any]:
    """Primitive model cache info.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `dict[str, Any]`.
    """
    return {
        "plane": cast(_CachedModelFactory, plane_model).cache_info(),
        "box": cast(_CachedModelFactory, box_model).cache_info(),
        "sphere": cast(_CachedModelFactory, sphere_model).cache_info(),
        "ellipsoid": cast(_CachedModelFactory, ellipsoid_model).cache_info(),
        "cylinder": cast(_CachedModelFactory, cylinder_model).cache_info(),
        "cone": cast(_CachedModelFactory, cone_model).cache_info(),
        "torus": cast(_CachedModelFactory, torus_model).cache_info(),
    }


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def plane_model(width: float, height: float | None = None) -> Model3D:
    """Plane model.
    
    Args:
        width: The width value. Expected type: `float`.
        height: The height value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
    return _rust_primitive_model("create_plane_model_handle", width, height)


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def box_model(width: float, height: float | None = None, depth: float | None = None) -> Model3D:
    """Box model.
    
    Args:
        width: The width value. Expected type: `float`.
        height: The height value. Expected type: `float | None`. Defaults to `None`.
        depth: The depth value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
    return _rust_primitive_model("create_box_model_handle", width, height, depth)


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def sphere_model(radius: float, detail_x: int = 24, detail_y: int = 16) -> Model3D:
    """Sphere model.
    
    Args:
        radius: The radius value. Expected type: `float`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `16`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
    return _rust_primitive_model("create_sphere_model_handle", radius, detail_x, detail_y)


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def ellipsoid_model(
    radius_x: float,
    radius_y: float | None = None,
    radius_z: float | None = None,
    detail_x: int = 24,
    detail_y: int = 16,
) -> Model3D:
    """Ellipsoid model.
    
    Args:
        radius_x: The radius x value. Expected type: `float`.
        radius_y: The radius y value. Expected type: `float | None`. Defaults to `None`.
        radius_z: The radius z value. Expected type: `float | None`. Defaults to `None`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `16`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
    return _rust_primitive_model(
        "create_ellipsoid_model_handle", radius_x, radius_y, radius_z, detail_x, detail_y
    )


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def cylinder_model(
    radius: float,
    height: float,
    detail_x: int = 24,
    detail_y: int = 1,
    *,
    bottom_cap: bool = True,
    top_cap: bool = True,
) -> Model3D:
    """Cylinder model.
    
    Args:
        radius: The radius value. Expected type: `float`.
        height: The height value. Expected type: `float`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `1`.
        bottom_cap: The bottom cap value. Expected type: `bool`. Defaults to `True`.
        top_cap: The top cap value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
    return _rust_primitive_model(
        "create_cylinder_model_handle", radius, height, detail_x, detail_y, bottom_cap, top_cap
    )


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def cone_model(
    radius: float, height: float, detail_x: int = 24, detail_y: int = 1, *, cap: bool = True
) -> Model3D:
    """Cone model.
    
    Args:
        radius: The radius value. Expected type: `float`.
        height: The height value. Expected type: `float`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `1`.
        cap: The cap value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
    return _rust_primitive_model(
        "create_cone_model_handle", radius, height, detail_x, detail_y, cap
    )


@lru_cache(maxsize=_MESH_CACHE_SIZE)
def torus_model(
    radius: float, tube_radius: float | None = None, detail_x: int = 24, detail_y: int = 12
) -> Model3D:
    """Torus model.
    
    Args:
        radius: The radius value. Expected type: `float`.
        tube_radius: The tube radius value. Expected type: `float | None`. Defaults to `None`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `12`.
    
    Returns:
        The return value. Type: `Model3D`.
    """
    return _rust_primitive_model(
        "create_torus_model_handle", radius, tube_radius, detail_x, detail_y
    )
