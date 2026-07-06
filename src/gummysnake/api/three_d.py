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


@overload
def orbit_control() -> Camera3D: ...


@overload
def orbit_control(sensitivity_x: Number, /) -> Camera3D: ...


@overload
def orbit_control(sensitivity_x: Number, sensitivity_y: Number, /) -> Camera3D: ...


@overload
def orbit_control(
    sensitivity_x: Number, sensitivity_y: Number, sensitivity_z: Number, /
) -> Camera3D: ...


def orbit_control(*args: Number) -> Camera3D:
    """Update the camera from mouse drag and scroll input.

    Args:
        *args: Optional x, y, and zoom sensitivity values. Higher values make
            the orbit controls respond more quickly.

    Returns:
        The updated active ``Camera3D``.
    """

    return require_context().orbit_control(*args)


@overload
def ambient_light(value: ColorValue, /) -> None: ...


@overload
def ambient_light(gray: Number, /) -> None: ...


@overload
def ambient_light(gray: Number, alpha: Number, /) -> None: ...


@overload
def ambient_light(v1: Number, v2: Number, v3: Number, /) -> None: ...


@overload
def ambient_light(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...


def ambient_light(*args: ColorArg) -> None:
    """Add soft light that reaches every side of 3D shapes."""

    _context_call("ambient_light", *args)


def lights() -> None:
    """Turn on a simple default 3D lighting setup."""

    require_context().lights()


def no_lights() -> None:
    """Remove all 3D lights from the active sketch."""

    require_context().no_lights()


@overload
def directional_light(value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def directional_light(gray: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def directional_light(gray: Number, alpha: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def directional_light(
    v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
) -> None: ...


@overload
def directional_light(
    v1: Number,
    v2: Number,
    v3: Number,
    alpha: Number,
    x: Number,
    y: Number,
    z: Number,
    /,
) -> None: ...


def directional_light(*args: ColorArg) -> None:
    """Add light that shines in one direction from far away."""

    _context_call("directional_light", *args)


@overload
def point_light(value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def point_light(gray: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def point_light(gray: Number, alpha: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def point_light(v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /) -> None: ...


@overload
def point_light(
    v1: Number,
    v2: Number,
    v3: Number,
    alpha: Number,
    x: Number,
    y: Number,
    z: Number,
    /,
) -> None: ...


def point_light(*args: ColorArg) -> None:
    """Add light that shines outward from a point in 3D space."""

    _context_call("point_light", *args)


def spot_light(*args: ColorArg) -> None:
    """Add cone-shaped light from a position toward a direction."""

    _context_call("spot_light", *args)


def image_light(image: Image, intensity: float = 1.0) -> None:
    """Add image-based lighting for reflective 3D materials."""

    require_context().image_light(image, intensity)


def panorama(image: Image | None = None) -> Image | None:
    """Set or read the panorama image used by the 3D scene.

    Args:
        image: Optional ``Image`` to use as the panorama. Omit to read the
            current panorama without changing it.

    Returns:
        The current panorama image, or ``None`` if no panorama is set.
    """

    return require_context().panorama(image)


def light_falloff(constant: float, linear: float, quadratic: float) -> None:
    """Set how point and spot lights fade with distance."""

    require_context().light_falloff(constant, linear, quadratic)


def specular_color(*args: ColorArg) -> None:
    """Set the highlight color for shiny 3D materials."""

    _context_call("specular_color", *args)


def normal_material() -> None:
    """Color each 3D surface by the direction it faces."""

    require_context().normal_material()


@overload
def ambient_material(value: ColorValue, /) -> None: ...


@overload
def ambient_material(gray: Number, /) -> None: ...


@overload
def ambient_material(gray: Number, alpha: Number, /) -> None: ...


@overload
def ambient_material(v1: Number, v2: Number, v3: Number, /) -> None: ...


@overload
def ambient_material(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...


def ambient_material(*args: ColorArg) -> None:
    """Set the base color for a material lit mostly by ambient light."""

    _context_call("ambient_material", *args)


@overload
def specular_material(value: ColorValue, /) -> None: ...


@overload
def specular_material(gray: Number, /) -> None: ...


@overload
def specular_material(gray: Number, alpha: Number, /) -> None: ...


@overload
def specular_material(v1: Number, v2: Number, v3: Number, /) -> None: ...


@overload
def specular_material(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...


def specular_material(*args: ColorArg) -> None:
    """Set a shiny material color for later 3D shapes."""

    _context_call("specular_material", *args)


def shininess(value: float) -> None:
    """Set how tight and bright specular highlights appear."""

    require_context().shininess(value)


def emissive_material(*args: ColorArg) -> None:
    """Set a self-lit material color that does not need lights."""

    _context_call("emissive_material", *args)


def metalness(value: float) -> None:
    """Set how metallic later 3D materials appear."""

    require_context().metalness(value)


def texture_mode(mode: c.TextureCoordinateMode | str | None = None) -> c.TextureCoordinateMode:
    """Set or read how texture coordinates are interpreted.

    Args:
        mode: ``NORMALIZED`` for 0-to-1 UVs, ``IMAGE`` for image-pixel
            coordinates, or ``None`` to read the current mode.

    Returns:
        The active texture coordinate mode.
    """

    return require_context().texture_mode(mode)


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
    "create_camera",
    "camera",
    "set_camera",
    "roll",
    "world_to_screen",
    "screen_to_world",
    "perspective",
    "frustum",
    "ortho",
    "orbit_control",
    "ambient_light",
    "lights",
    "no_lights",
    "directional_light",
    "point_light",
    "spot_light",
    "image_light",
    "panorama",
    "light_falloff",
    "specular_color",
    "normal_material",
    "ambient_material",
    "specular_material",
    "shininess",
    "emissive_material",
    "metalness",
    "texture_mode",
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
