"""Global-mode WEBGL-style 3D camera, lighting, material, and primitive wrappers."""

from __future__ import annotations

from typing import Any, cast, overload

from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.drawing.renderer3d import Camera3D, Mesh3D, Model3D, Vec3
from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
)

Number = int | float
ColorValue = Color | str


@overload
def create_camera() -> Camera3D:
    ...


@overload
def create_camera(camera: Camera3D, /) -> Camera3D:
    ...


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
) -> Camera3D:
    ...


def create_camera(*args: Any) -> Camera3D:
    """Create and return a camera value.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        The return value. Type: `Camera3D`.
    """
    return require_context().create_camera(*args)


@overload
def camera() -> Camera3D:
    ...


@overload
def camera(camera: Camera3D, /) -> Camera3D:
    ...


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
) -> Camera3D:
    ...


def camera(*args: Any) -> Camera3D:
    """Camera using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        The return value. Type: `Camera3D`.
    """
    return require_context().camera(*args)


def set_camera(camera_value: Camera3D) -> Camera3D:
    """Set the camera value.

    Args:
        camera_value: The camera value value. Expected type: `Camera3D`.

    Returns:
        The return value. Type: `Camera3D`.
    """
    return require_context().set_camera(camera_value)


def roll(angle: Number) -> Camera3D:
    """Roll using the active three d context.

    Args:
        angle: The angle value. Expected type: `Number`.

    Returns:
        The return value. Type: `Camera3D`.
    """
    return require_context().roll(angle)


def world_to_screen(x: Number, y: Number, z: Number) -> tuple[float, float, float]:
    """World to screen using the active three d context.

    Args:
        x: The x value. Expected type: `Number`.
        y: The y value. Expected type: `Number`.
        z: The z value. Expected type: `Number`.

    Returns:
        The return value. Type: `tuple[float, float, float]`.
    """
    return require_context().world_to_screen(x, y, z)


def screen_to_world(x: Number, y: Number, depth: Number = 0.0) -> Vec3:
    """Screen to world using the active three d context.

    Args:
        x: The x value. Expected type: `Number`.
        y: The y value. Expected type: `Number`.
        depth: The depth value. Expected type: `Number`. Defaults to `0.0`.

    Returns:
        The return value. Type: `Vec3`.
    """
    return require_context().screen_to_world(x, y, depth)


@overload
def perspective() -> PerspectiveProjection:
    ...


@overload
def perspective(fov: Number, /) -> PerspectiveProjection:
    ...


@overload
def perspective(fov: Number, aspect: Number, /) -> PerspectiveProjection:
    ...


@overload
def perspective(fov: Number, aspect: Number, near: Number, /) -> PerspectiveProjection:
    ...


@overload
def perspective(fov: Number, aspect: Number, near: Number, far: Number, /) -> PerspectiveProjection:
    ...


def perspective(*args: Any) -> PerspectiveProjection:
    """Set and return the active perspective projection.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        The return value. Type: `PerspectiveProjection`.
    """
    return require_context().perspective(*args)


@overload
def ortho() -> OrthographicProjection:
    ...


@overload
def ortho(width: Number, height: Number, /) -> OrthographicProjection:
    ...


@overload
def ortho(width: Number, height: Number, near: Number, far: Number, /) -> OrthographicProjection:
    ...


def ortho(*args: Any) -> OrthographicProjection:
    """Ortho using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        The return value. Type: `OrthographicProjection`.
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
    """Frustum using the active three d context.

    Args:
        left: The left value. Expected type: `Number`.
        right: The right value. Expected type: `Number`.
        bottom: The bottom value. Expected type: `Number`.
        top: The top value. Expected type: `Number`.
        near: The near value. Expected type: `Number`. Defaults to `0.1`.
        far: The far value. Expected type: `Number`. Defaults to `10000.0`.

    Returns:
        The return value. Type: `FrustumProjection`.
    """
    return require_context().frustum(left, right, bottom, top, near, far)


@overload
def orbit_control() -> Camera3D:
    ...


@overload
def orbit_control(sensitivity_x: Number, /) -> Camera3D:
    ...


@overload
def orbit_control(sensitivity_x: Number, sensitivity_y: Number, /) -> Camera3D:
    ...


@overload
def orbit_control(
    sensitivity_x: Number, sensitivity_y: Number, sensitivity_z: Number, /
) -> Camera3D:
    ...


def orbit_control(*args: Any) -> Camera3D:
    """Orbit control using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        The return value. Type: `Camera3D`.
    """
    return require_context().orbit_control(*args)


@overload
def ambient_light(value: ColorValue, /) -> None:
    ...


@overload
def ambient_light(gray: Number, /) -> None:
    ...


@overload
def ambient_light(gray: Number, alpha: Number, /) -> None:
    ...


@overload
def ambient_light(v1: Number, v2: Number, v3: Number, /) -> None:
    ...


@overload
def ambient_light(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
    ...


def ambient_light(*args: Any) -> None:
    """Ambient light using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        None.
    """
    cast(Any, require_context()).ambient_light(*args)


def lights() -> None:
    """Lights using the active three d context.

    Args:
        None.

    Returns:
        None.
    """
    require_context().lights()


def no_lights() -> None:
    """Disable lights for subsequent operations.

    Args:
        None.

    Returns:
        None.
    """
    require_context().no_lights()


@overload
def directional_light(value: ColorValue, x: Number, y: Number, z: Number, /) -> None:
    ...


@overload
def directional_light(gray: Number, x: Number, y: Number, z: Number, /) -> None:
    ...


@overload
def directional_light(gray: Number, alpha: Number, x: Number, y: Number, z: Number, /) -> None:
    ...


@overload
def directional_light(
    v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
) -> None:
    ...


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
) -> None:
    ...


def directional_light(*args: Any) -> None:
    """Directional light using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        None.
    """
    cast(Any, require_context()).directional_light(*args)


@overload
def point_light(value: ColorValue, x: Number, y: Number, z: Number, /) -> None:
    ...


@overload
def point_light(gray: Number, x: Number, y: Number, z: Number, /) -> None:
    ...


@overload
def point_light(gray: Number, alpha: Number, x: Number, y: Number, z: Number, /) -> None:
    ...


@overload
def point_light(v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /) -> None:
    ...


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
) -> None:
    ...


def point_light(*args: Any) -> None:
    """Add a point light to the active 3D scene.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        None.
    """
    cast(Any, require_context()).point_light(*args)


def spot_light(*args: Any) -> None:
    """Spot light using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        None.
    """
    cast(Any, require_context()).spot_light(*args)


def image_light(image: Image, intensity: float = 1.0) -> None:
    """Image light using the active three d context.

    Args:
        image: The image value. Expected type: `Image`.
        intensity: The intensity value. Expected type: `float`. Defaults to `1.0`.

    Returns:
        None.
    """
    require_context().image_light(image, intensity)


def panorama(image: Image | None = None) -> Image | None:
    """Get or set the active panorama image for 3D lighting.

    Args:
        image: The image value. Expected type: `Image | None`. Defaults to `None`.

    Returns:
        The return value. Type: `Image | None`.
    """
    return require_context().panorama(image)


def light_falloff(constant: float, linear: float, quadratic: float) -> None:
    """Light falloff using the active three d context.

    Args:
        constant: The constant value. Expected type: `float`.
        linear: The linear value. Expected type: `float`.
        quadratic: The quadratic value. Expected type: `float`.

    Returns:
        None.
    """
    require_context().light_falloff(constant, linear, quadratic)


def specular_color(*args: Any) -> None:
    """Specular color using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        None.
    """
    cast(Any, require_context()).specular_color(*args)


def normal_material() -> None:
    """Normal material using the active three d context.

    Args:
        None.

    Returns:
        None.
    """
    require_context().normal_material()


@overload
def ambient_material(value: ColorValue, /) -> None:
    ...


@overload
def ambient_material(gray: Number, /) -> None:
    ...


@overload
def ambient_material(gray: Number, alpha: Number, /) -> None:
    ...


@overload
def ambient_material(v1: Number, v2: Number, v3: Number, /) -> None:
    ...


@overload
def ambient_material(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
    ...


def ambient_material(*args: Any) -> None:
    """Ambient material using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        None.
    """
    cast(Any, require_context()).ambient_material(*args)


@overload
def specular_material(value: ColorValue, /) -> None:
    ...


@overload
def specular_material(gray: Number, /) -> None:
    ...


@overload
def specular_material(gray: Number, alpha: Number, /) -> None:
    ...


@overload
def specular_material(v1: Number, v2: Number, v3: Number, /) -> None:
    ...


@overload
def specular_material(v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
    ...


def specular_material(*args: Any) -> None:
    """Specular material using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        None.
    """
    cast(Any, require_context()).specular_material(*args)


def shininess(value: float) -> None:
    """Shininess using the active three d context.

    Args:
        value: The value value. Expected type: `float`.

    Returns:
        None.
    """
    require_context().shininess(value)


def emissive_material(*args: Any) -> None:
    """Emissive material using the active three d context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        None.
    """
    cast(Any, require_context()).emissive_material(*args)


def metalness(value: float) -> None:
    """Metalness using the active three d context.

    Args:
        value: The value value. Expected type: `float`.

    Returns:
        None.
    """
    require_context().metalness(value)


def texture_mode(mode: Any = None) -> Any:
    """Texture mode using the active three d context.

    Args:
        mode: The mode value. Expected type: `Any`. Defaults to `None`.

    Returns:
        The return value. Type: `Any`.
    """
    return require_context().texture_mode(mode)


def texture_wrap(wrap_x: Any = None, wrap_y: Any = None) -> Any:
    """Texture wrap using the active three d context.

    Args:
        wrap_x: The wrap x value. Expected type: `Any`. Defaults to `None`.
        wrap_y: The wrap y value. Expected type: `Any`. Defaults to `None`.

    Returns:
        The return value. Type: `Any`.
    """
    return require_context().texture_wrap(wrap_x, wrap_y)


def texture(image: Image) -> None:
    """Texture using the active three d context.

    Args:
        image: The image value. Expected type: `Image`.

    Returns:
        None.
    """
    require_context().texture(image)


def plane(width: float, height: float | None = None) -> None:
    """Draw a 3D plane primitive.

    Args:
        width: The width value. Expected type: `float`.
        height: The height value. Expected type: `float | None`. Defaults to `None`.

    Returns:
        None.
    """
    require_context().plane(width, height)


def box(width: float, height: float | None = None, depth: float | None = None) -> None:
    """Box using the active three d context.

    Args:
        width: The width value. Expected type: `float`.
        height: The height value. Expected type: `float | None`. Defaults to `None`.
        depth: The depth value. Expected type: `float | None`. Defaults to `None`.

    Returns:
        None.
    """
    require_context().box(width, height, depth)


def sphere(radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
    """Sphere using the active three d context.

    Args:
        radius: The radius value. Expected type: `float`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `16`.

    Returns:
        None.
    """
    require_context().sphere(radius, detail_x, detail_y)


def ellipsoid(
    radius_x: float,
    radius_y: float | None = None,
    radius_z: float | None = None,
    detail_x: int = 24,
    detail_y: int = 16,
) -> None:
    """Ellipsoid using the active three d context.

    Args:
        radius_x: The radius x value. Expected type: `float`.
        radius_y: The radius y value. Expected type: `float | None`. Defaults to `None`.
        radius_z: The radius z value. Expected type: `float | None`. Defaults to `None`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `16`.

    Returns:
        None.
    """
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
    """Cylinder using the active three d context.

    Args:
        radius: The radius value. Expected type: `float`.
        height: The height value. Expected type: `float`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `1`.
        bottom_cap: The bottom cap value. Expected type: `bool`. Defaults to `True`.
        top_cap: The top cap value. Expected type: `bool`. Defaults to `True`.

    Returns:
        None.
    """
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
    """Cone using the active three d context.

    Args:
        radius: The radius value. Expected type: `float`.
        height: The height value. Expected type: `float`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `1`.
        cap: The cap value. Expected type: `bool`. Defaults to `True`.

    Returns:
        None.
    """
    require_context().cone(radius, height, detail_x, detail_y, cap=cap)


def torus(
    radius: float,
    tube_radius: float | None = None,
    detail_x: int = 24,
    detail_y: int = 12,
) -> None:
    """Torus using the active three d context.

    Args:
        radius: The radius value. Expected type: `float`.
        tube_radius: The tube radius value. Expected type: `float | None`. Defaults to `None`.
        detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
        detail_y: The detail y value. Expected type: `int`. Defaults to `12`.

    Returns:
        None.
    """
    require_context().torus(radius, tube_radius, detail_x, detail_y)


def create_model(mesh: Mesh3D | Model3D) -> Model3D:
    """Create and return a model value.

    Args:
        mesh: The mesh value. Expected type: `Mesh3D | Model3D`.

    Returns:
        The return value. Type: `Model3D`.
    """
    return require_context().create_model(mesh)


def normal(x: float, y: float, z: float) -> None:
    """Normal using the active three d context.

    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        z: The z value. Expected type: `float`.

    Returns:
        None.
    """
    require_context().normal(x, y, z)


def vertex_property(name: str, value: object) -> None:
    """Vertex property using the active three d context.

    Args:
        name: The name value. Expected type: `str`.
        value: The value value. Expected type: `object`.

    Returns:
        None.
    """
    require_context().vertex_property(name, value)


def build_geometry(callback: Any) -> Model3D:
    """Build geometry using the active three d context.

    Args:
        callback: The callback value. Expected type: `Any`.

    Returns:
        The return value. Type: `Model3D`.
    """
    return require_context().build_geometry(callback)


def free_geometry(model_value: Model3D) -> None:
    """Free geometry using the active three d context.

    Args:
        model_value: The model value value. Expected type: `Model3D`.

    Returns:
        None.
    """
    require_context().free_geometry(model_value)


def flip_u(mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
    """Flip u using the active three d context.

    Args:
        mesh_or_model: The mesh or model value. Expected type: `Mesh3D | Model3D`.

    Returns:
        The return value. Type: `Mesh3D | Model3D`.
    """
    return require_context().flip_u(mesh_or_model)


def flip_v(mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
    """Flip v using the active three d context.

    Args:
        mesh_or_model: The mesh or model value. Expected type: `Mesh3D | Model3D`.

    Returns:
        The return value. Type: `Mesh3D | Model3D`.
    """
    return require_context().flip_v(mesh_or_model)


def model(shape: Mesh3D | Model3D) -> None:
    """Model using the active three d context.

    Args:
        shape: The shape value. Expected type: `Mesh3D | Model3D`.

    Returns:
        None.
    """
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
