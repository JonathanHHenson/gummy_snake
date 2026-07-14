"""3D lighting, material, texture, and shader methods for SketchContext."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.context_mixins.three_d._protocols import _three_d
from gummysnake.core.color import Color
from gummysnake.drawing.renderer3d import (
    Light3D,
    LightKind,
    Material3D,
    Shader3D,
    ShaderUniformValue,
    Texture3D,
    Vec3,
)
from gummysnake.exceptions import (
    ArgumentValidationError,
    BackendCapabilityError,
    ShaderUniformError,
)

Number = int | float
ColorValue = Color | str


class ThreeDMaterialMixin:
    backend: Any
    renderer: Any
    _lights3d: list[Light3D]
    _light_falloff3d: tuple[float, float, float]
    _specular_color3d: tuple[float, float, float, float]
    _texture_mode3d: c.TextureCoordinateMode | None
    _texture_wrap3d: tuple[c.TextureWrapMode, c.TextureWrapMode] | None
    _panorama3d: object | None
    _material3d: Material3D | None
    _normal_material3d: bool
    _shader3d: Shader3D | None

    @overload
    def ambient_light(self, value: ColorValue, /) -> None: ...

    @overload
    def ambient_light(self, gray: Number, /) -> None: ...

    @overload
    def ambient_light(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def ambient_light(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def ambient_light(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def ambient_light(self, *args: Any) -> None:
        _three_d(self)._require_webgl_mode("ambient_light")
        color = _three_d(self)._color_to_rgba(_three_d(self).color(*args))
        self._lights3d.append(Light3D(kind=LightKind.AMBIENT, color=color))

    def lights(self) -> None:
        _three_d(self)._require_webgl_mode("lights")
        self.no_lights()
        self.ambient_light(128)
        self.directional_light(255, 0, 0, -1)

    def no_lights(self) -> None:
        _three_d(self)._require_webgl_mode("no_lights")
        self._lights3d = []

    @overload
    def directional_light(self, value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def directional_light(self, gray: Number, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def directional_light(
        self, gray: Number, alpha: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def directional_light(
        self, v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def directional_light(
        self,
        v1: Number,
        v2: Number,
        v3: Number,
        alpha: Number,
        x: Number,
        y: Number,
        z: Number,
        /,
    ) -> None: ...

    def directional_light(self, *args: Any) -> None:
        _three_d(self)._require_webgl_mode("directional_light")
        color, tail = _three_d(self)._split_color_args(args, tail_count=3)
        self._lights3d.append(
            Light3D(
                kind=LightKind.DIRECTIONAL,
                color=_three_d(self)._color_to_rgba(color),
                direction=Vec3(float(tail[0]), float(tail[1]), float(tail[2])),
            )
        )

    @overload
    def point_light(self, value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def point_light(self, gray: Number, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def point_light(
        self, gray: Number, alpha: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def point_light(
        self, v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def point_light(
        self,
        v1: Number,
        v2: Number,
        v3: Number,
        alpha: Number,
        x: Number,
        y: Number,
        z: Number,
        /,
    ) -> None: ...

    def point_light(self, *args: Any) -> None:
        _three_d(self)._require_webgl_mode("point_light")
        color, tail = _three_d(self)._split_color_args(args, tail_count=3)
        self._lights3d.append(
            Light3D(
                kind=LightKind.POINT,
                color=_three_d(self)._color_to_rgba(color),
                position=Vec3(float(tail[0]), float(tail[1]), float(tail[2])),
                falloff=self._light_falloff3d,
            )
        )

    def spot_light(self, *args: Any) -> None:
        _three_d(self)._require_webgl_mode("spot_light")
        try:
            color, tail = _three_d(self)._split_color_args(args, tail_count=8)
        except ArgumentValidationError:
            color, tail = _three_d(self)._split_color_args(args, tail_count=7)
            tail = (*tail, 1.0)
        self._lights3d.append(
            Light3D(
                kind=LightKind.SPOT,
                color=_three_d(self)._color_to_rgba(color),
                position=Vec3(float(tail[0]), float(tail[1]), float(tail[2])),
                direction=Vec3(float(tail[3]), float(tail[4]), float(tail[5])),
                angle=float(tail[6]),
                concentration=float(tail[7]),
                falloff=self._light_falloff3d,
            )
        )

    def image_light(self, image: Image, intensity: float = 1.0) -> None:
        _three_d(self)._require_webgl_mode("image_light")
        if not isinstance(image, Image):
            raise ArgumentValidationError("image_light() requires a Gummy Snake Image object.")
        self._lights3d.append(
            Light3D(kind=LightKind.IMAGE, intensity=float(intensity), source=image)
        )

    def panorama(self, image: Image | None = None) -> Image | None:
        _three_d(self)._require_webgl_mode("panorama")
        if image is not None and not isinstance(image, Image):
            raise ArgumentValidationError("panorama() requires a Gummy Snake Image object.")
        if image is not None:
            self._panorama3d = image
        return cast(Image | None, self._panorama3d)

    def light_falloff(self, constant: float, linear: float, quadratic: float) -> None:
        _three_d(self)._require_webgl_mode("light_falloff")
        if constant < 0 or linear < 0 or quadratic < 0:
            raise ArgumentValidationError("light_falloff() values cannot be negative.")
        self._light_falloff3d = (float(constant), float(linear), float(quadratic))

    def specular_color(self, *args: Any) -> None:
        _three_d(self)._require_webgl_mode("specular_color")
        self._specular_color3d = _three_d(self)._color_to_rgba(_three_d(self).color(*args))
        self._material3d = _three_d(self)._replace_material(specular_color=self._specular_color3d)

    def normal_material(self) -> None:
        _three_d(self)._require_webgl_mode("normal_material")
        self._material3d = None
        self._normal_material3d = True

    @overload
    def ambient_material(self, value: ColorValue, /) -> None: ...

    @overload
    def ambient_material(self, gray: Number, /) -> None: ...

    @overload
    def ambient_material(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def ambient_material(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def ambient_material(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def ambient_material(self, *args: Any) -> None:
        _three_d(self)._require_webgl_mode("ambient_material")
        self._material3d = _three_d(self)._replace_material(
            base_color=_three_d(self)._color_to_rgba(_three_d(self).color(*args)), texture=None
        )
        self._normal_material3d = False

    @overload
    def specular_material(self, value: ColorValue, /) -> None: ...

    @overload
    def specular_material(self, gray: Number, /) -> None: ...

    @overload
    def specular_material(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def specular_material(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def specular_material(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def specular_material(self, *args: Any) -> None:
        _three_d(self)._require_webgl_mode("specular_material")
        color = _three_d(self)._color_to_rgba(_three_d(self).color(*args))
        self._material3d = _three_d(self)._replace_material(
            base_color=color, specular_color=self._specular_color3d, texture=None
        )
        self._normal_material3d = False

    def shininess(self, value: float) -> None:
        _three_d(self)._require_webgl_mode("shininess")
        if value <= 0:
            raise ArgumentValidationError("shininess() must be positive.")
        self._material3d = _three_d(self)._replace_material(shininess=float(value))

    def emissive_material(self, *args: Any) -> None:
        _three_d(self)._require_webgl_mode("emissive_material")
        emissive = _three_d(self)._color_to_rgba(_three_d(self).color(*args))
        self._material3d = _three_d(self)._replace_material(
            base_color=emissive, emissive_color=emissive, texture=None
        )
        self._normal_material3d = False

    def metalness(self, value: float) -> None:
        _three_d(self)._require_webgl_mode("metalness")
        if not 0.0 <= value <= 1.0:
            raise ArgumentValidationError("metalness() must be between 0 and 1.")
        self._material3d = _three_d(self)._replace_material(metalness=float(value))

    def texture_mode(
        self, mode: c.TextureCoordinateMode | str | None = None
    ) -> c.TextureCoordinateMode:
        _three_d(self)._require_webgl_mode("texture_mode")
        if mode is not None:
            self._texture_mode3d = c.TextureCoordinateMode(mode)
        return self._texture_mode3d or c.NORMALIZED

    def texture_wrap(
        self,
        wrap_x: c.TextureWrapMode | str | None = None,
        wrap_y: c.TextureWrapMode | str | None = None,
    ) -> tuple[c.TextureWrapMode, c.TextureWrapMode]:
        _three_d(self)._require_webgl_mode("texture_wrap")
        if wrap_x is not None:
            x_mode = c.TextureWrapMode(wrap_x)
            y_mode = x_mode if wrap_y is None else c.TextureWrapMode(wrap_y)
            self._texture_wrap3d = (x_mode, y_mode)
        return self._texture_wrap3d or (c.CLAMP, c.CLAMP)

    def texture(self, image: Image) -> None:
        _three_d(self)._require_webgl_mode("texture")
        if not isinstance(image, Image):
            raise ArgumentValidationError("texture() requires a Gummy Snake Image object.")
        wrap_x, wrap_y = self.texture_wrap()
        self._material3d = _three_d(self)._replace_material(
            texture=Texture3D(
                source=image,
                width=image.width,
                height=image.height,
                coordinate_mode=self.texture_mode(),
                wrap_x=wrap_x,
                wrap_y=wrap_y,
            )
        )
        self._normal_material3d = False

    def load_shader(self, vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
        from gummysnake.assets.shader import load_shader as _load_shader

        return _load_shader(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str) -> Shader3D:
        from gummysnake.assets.shader import create_shader as _create_shader

        return _create_shader(vertex_source, fragment_source)

    def shader(self, shader: Shader3D) -> None:
        _three_d(self)._require_webgl_mode("shader")
        if not self.backend.capabilities.shaders:
            enable_native_webgl = getattr(self.backend, "enable_native_webgl", None)
            if callable(enable_native_webgl) and enable_native_webgl():
                self.renderer = self.backend.renderer
        if not self.backend.capabilities.shaders:
            raise BackendCapabilityError(
                f"Backend {self.backend.name!r} does not support shader()."
            )
        if not isinstance(shader, Shader3D):
            raise ArgumentValidationError("shader() requires a Shader3D value.")
        self._shader3d = shader

    def reset_shader(self) -> None:
        _three_d(self)._require_webgl_mode("reset_shader")
        self._shader3d = None

    def set_shader_uniform(self, name: str, value: ShaderUniformValue) -> None:
        _three_d(self)._require_webgl_mode("set_shader_uniform")
        if self._shader3d is None:
            raise ShaderUniformError(
                f"Cannot set uniform {name!r} without an active shader. Call shader(...) first."
            )
        self._shader3d.set_uniform(name, value)
