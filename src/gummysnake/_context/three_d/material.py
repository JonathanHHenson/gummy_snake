# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""3D lighting, material, texture, and shader methods for SketchContext."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from gummysnake.assets.image import Image
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


class ThreeDMaterialMixin:
    backend: Any
    renderer: Any
    _lights3d: list[Light3D]
    _material3d: Material3D | None
    _normal_material3d: bool
    _shader3d: Shader3D | None

    def ambient_light(self, *args: object) -> None:
        self._require_webgl_mode("ambient_light")
        self._lights3d.append(
            Light3D(kind=LightKind.AMBIENT, color=self._color_to_rgba(self.color(*args)))
        )

    def directional_light(self, *args: object) -> None:
        self._require_webgl_mode("directional_light")
        color, tail = self._split_color_args(args, tail_count=3)
        self._lights3d.append(
            Light3D(
                kind=LightKind.DIRECTIONAL,
                color=self._color_to_rgba(color),
                direction=Vec3(float(tail[0]), float(tail[1]), float(tail[2])),
            )
        )

    def point_light(self, *args: object) -> None:
        self._require_webgl_mode("point_light")
        color, tail = self._split_color_args(args, tail_count=3)
        self._lights3d.append(
            Light3D(
                kind=LightKind.POINT,
                color=self._color_to_rgba(color),
                position=Vec3(float(tail[0]), float(tail[1]), float(tail[2])),
            )
        )

    def normal_material(self) -> None:
        self._require_webgl_mode("normal_material")
        self._material3d = None
        self._normal_material3d = True

    def ambient_material(self, *args: object) -> None:
        self._require_webgl_mode("ambient_material")
        self._material3d = self._replace_material(
            base_color=self._color_to_rgba(self.color(*args)), texture=None
        )
        self._normal_material3d = False

    def specular_material(self, *args: object) -> None:
        self._require_webgl_mode("specular_material")
        color = self._color_to_rgba(self.color(*args))
        self._material3d = self._replace_material(
            base_color=color, specular_color=color, texture=None
        )
        self._normal_material3d = False

    def shininess(self, value: float) -> None:
        self._require_webgl_mode("shininess")
        if value <= 0:
            raise ArgumentValidationError("shininess() must be positive.")
        self._material3d = self._replace_material(shininess=float(value))

    def texture(self, image: Image) -> None:
        self._require_webgl_mode("texture")
        if not isinstance(image, Image):
            raise ArgumentValidationError("texture() requires a Gummy Snake Image object.")
        self._material3d = self._replace_material(
            texture=Texture3D(source=image, width=image.width, height=image.height)
        )
        self._normal_material3d = False

    def load_shader(self, vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
        from gummysnake.assets.shader import load_shader as _load_shader

        return _load_shader(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str) -> Shader3D:
        from gummysnake.assets.shader import create_shader as _create_shader

        return _create_shader(vertex_source, fragment_source)

    def shader(self, shader: Shader3D) -> None:
        self._require_webgl_mode("shader")
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
        self._require_webgl_mode("reset_shader")
        self._shader3d = None

    def set_shader_uniform(self, name: str, value: object) -> None:
        self._require_webgl_mode("set_shader_uniform")
        if self._shader3d is None:
            raise ShaderUniformError(
                f"Cannot set uniform {name!r} without an active shader. Call shader(...) first."
            )
        self._shader3d.set_uniform(name, cast("ShaderUniformValue", value))
