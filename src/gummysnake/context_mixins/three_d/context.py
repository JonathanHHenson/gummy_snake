"""3D camera, lighting, material, shader, and model methods for SketchContext."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, auto
from typing import Any, Literal, cast, overload

from gummysnake import constants as c
from gummysnake.context_mixins.three_d.camera_runtime import ThreeDCameraMixin
from gummysnake.context_mixins.three_d.material import ThreeDMaterialMixin
from gummysnake.context_mixins.three_d.model import ThreeDModelMixin
from gummysnake.context_mixins.three_d.primitives import ThreeDPrimitivesMixin
from gummysnake.core.color import Color
from gummysnake.drawing.renderer3d import Camera3D, Light3D, Material3D, Shader3D, Texture3D
from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
)
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


class _MaterialUnset(Enum):
    TOKEN = auto()


_MATERIAL_UNSET = _MaterialUnset.TOKEN
type MaterialUnset = Literal[_MaterialUnset.TOKEN]
Number = int | float
ColorValue = Color | str


class ThreeDContextMixin(
    ThreeDCameraMixin,
    ThreeDMaterialMixin,
    ThreeDPrimitivesMixin,
    ThreeDModelMixin,
):
    """Composed 3D API surface mixed into SketchContext."""

    state: Any
    _camera3d: Camera3D
    _projection3d: PerspectiveProjection | OrthographicProjection | FrustumProjection
    _lights3d: list[Light3D]
    _light_falloff3d: tuple[float, float, float]
    _specular_color3d: tuple[float, float, float, float]
    _texture_mode3d: c.TextureCoordinateMode | None
    _texture_wrap3d: tuple[c.TextureWrapMode, c.TextureWrapMode] | None
    _material3d: Material3D | None
    _normal_material3d: bool
    _material3d_style_stack: list[tuple[Material3D | None, bool]]
    _shader3d: Shader3D | None
    _frame_mouse_dx: float
    _frame_mouse_dy: float
    _frame_scroll_x: float
    _frame_scroll_y: float

    @overload
    def color(self, value: ColorValue, /) -> Color: ...

    @overload
    def color(self, gray: Number, /) -> Color: ...

    @overload
    def color(self, gray: Number, alpha: Number, /) -> Color: ...

    @overload
    def color(self, v1: Number, v2: Number, v3: Number, /) -> Color: ...

    @overload
    def color(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> Color: ...

    def color(self, *args: Any) -> Color:
        raise NotImplementedError

    def _require_webgl_mode(self, api_name: str) -> None:
        if self.state.canvas.renderer not in {c.WEBGL, c.WEBGPU}:
            raise BackendCapabilityError(
                f"{api_name}() requires create_canvas(..., renderer={c.WEBGL!r} or {c.WEBGPU!r})."
            )

    def _reset_3d_state(self) -> None:
        self._camera3d = Camera3D()
        self._projection3d = PerspectiveProjection()
        self._lights3d = []
        self._light_falloff3d = (1.0, 0.0, 0.0)
        self._specular_color3d = (1.0, 1.0, 1.0, 1.0)
        self._texture_mode3d = c.NORMALIZED
        self._texture_wrap3d = (c.CLAMP, c.CLAMP)
        self._panorama3d = None
        self._material3d = None
        self._normal_material3d = False
        self._material3d_style_stack = []
        self._frame_mouse_dx = 0.0
        self._frame_mouse_dy = 0.0
        self._frame_scroll_x = 0.0
        self._frame_scroll_y = 0.0
        self._shader3d = None

    def _effective_3d_material(self) -> Material3D:
        if self._material3d is not None:
            return self._material3d
        fill = self.state.style.fill_color or Color(255, 255, 255, 255)
        return Material3D(base_color=self._color_to_rgba(fill))

    def _replace_material(
        self,
        *,
        base_color: tuple[float, float, float, float] | None = None,
        emissive_color: tuple[float, float, float, float] | None = None,
        specular_color: tuple[float, float, float, float] | None = None,
        shininess: float | None = None,
        metalness: float | None = None,
        texture: Texture3D | None | MaterialUnset = _MATERIAL_UNSET,
    ) -> Material3D:
        current = self._effective_3d_material()
        return Material3D(
            base_color=current.base_color if base_color is None else base_color,
            emissive_color=current.emissive_color if emissive_color is None else emissive_color,
            specular_color=current.specular_color if specular_color is None else specular_color,
            shininess=current.shininess if shininess is None else shininess,
            metalness=current.metalness if metalness is None else metalness,
            texture=current.texture
            if texture is _MATERIAL_UNSET
            else cast(Texture3D | None, texture),
        )

    def _split_color_args(
        self,
        args: Sequence[Any],
        *,
        tail_count: int,
    ) -> tuple[Color, tuple[float, ...]]:
        for color_count in (4, 3, 2, 1):
            if len(args) != color_count + tail_count:
                continue
            color = cast(Color, cast(Any, self).color(*args[:color_count]))
            tail = args[color_count:]
            if all(isinstance(value, int | float) for value in tail):
                return color, self._numeric_values(tail)
        raise ArgumentValidationError(
            "Light APIs require one to four color values followed by the expected coordinates."
        )

    def _numeric_values(self, values: Sequence[Any]) -> tuple[float, ...]:
        numeric: list[float] = []
        for value in values:
            if not isinstance(value, int | float):
                raise ArgumentValidationError("Expected numeric values.")
            numeric.append(float(value))
        return tuple(numeric)

    def _color_to_rgba(self, color: Color) -> tuple[float, float, float, float]:
        return (color.r / 255.0, color.g / 255.0, color.b / 255.0, color.a / 255.0)

    def _rgba_float_to_color(self, rgba: tuple[float, float, float, float]) -> Color:
        return Color(*(int(round(max(0.0, min(1.0, channel)) * 255.0)) for channel in rgba))
