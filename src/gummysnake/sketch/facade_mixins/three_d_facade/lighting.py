"""3D lighting forwards for object-mode sketches."""

from __future__ import annotations

from typing import overload

from gummysnake.assets.image import Image
from gummysnake.sketch.facade_mixins.base import ColorValue, Number, SketchFacadeBaseMixin

type ColorArg = ColorValue | Number


class SketchFacadeLightingMixin(SketchFacadeBaseMixin):
    """Configure lights and lighting environment through the active context."""

    __facade_doc_topic__ = "Configure lighting for this sketch's active 3D scene."

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

    def ambient_light(self, *args: ColorArg) -> None:
        self._ctx_call("ambient_light", *args)

    def lights(self) -> None:
        self._ctx.lights()

    def no_lights(self) -> None:
        self._ctx.no_lights()

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

    def directional_light(self, *args: ColorArg) -> None:
        self._ctx_call("directional_light", *args)

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

    def point_light(self, *args: ColorArg) -> None:
        self._ctx_call("point_light", *args)

    def spot_light(self, *args: ColorArg) -> None:
        self._ctx_call("spot_light", *args)

    def image_light(self, image: Image, intensity: float = 1.0) -> None:
        self._ctx.image_light(image, intensity)

    def panorama(self, image: Image | None = None) -> Image | None:
        return self._ctx.panorama(image)

    def light_falloff(self, constant: float, linear: float, quadratic: float) -> None:
        self._ctx.light_falloff(constant, linear, quadratic)

    def specular_color(self, *args: ColorArg) -> None:
        self._ctx_call("specular_color", *args)
