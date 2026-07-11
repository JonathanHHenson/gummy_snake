"""3D material and texture forwards for object-mode sketches."""

from __future__ import annotations

from typing import overload

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.sketch.facade_mixins.base import ColorValue, Number, SketchFacadeBaseMixin
from gummysnake.sketch.facade_mixins.three_d_facade.lighting import ColorArg


class SketchFacadeMaterialsMixin(SketchFacadeBaseMixin):
    """Configure materials and textures through the active 3D context."""

    __facade_doc_topic__ = "Configure materials or textures for this sketch's active 3D scene."

    def normal_material(self) -> None:
        self._ctx.normal_material()

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

    def ambient_material(self, *args: ColorArg) -> None:
        self._ctx_call("ambient_material", *args)

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

    def specular_material(self, *args: ColorArg) -> None:
        self._ctx_call("specular_material", *args)

    def shininess(self, value: float) -> None:
        self._ctx.shininess(value)

    def emissive_material(self, *args: ColorArg) -> None:
        self._ctx_call("emissive_material", *args)

    def metalness(self, value: float) -> None:
        self._ctx.metalness(value)

    def texture_mode(
        self, mode: c.TextureCoordinateMode | str | None = None
    ) -> c.TextureCoordinateMode:
        return self._ctx.texture_mode(mode)

    def texture_wrap(
        self,
        wrap_x: c.TextureWrapMode | str | None = None,
        wrap_y: c.TextureWrapMode | str | None = None,
    ) -> tuple[c.TextureWrapMode, c.TextureWrapMode]:
        return self._ctx.texture_wrap(wrap_x, wrap_y)

    def texture(self, image: Image) -> None:
        self._ctx.texture(image)
