# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
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
