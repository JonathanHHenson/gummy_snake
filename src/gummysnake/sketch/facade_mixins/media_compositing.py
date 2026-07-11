"""Compositing and erase forwards for object-mode sketches."""

from __future__ import annotations

from typing import overload

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin

type BlendArg = Image | int | c.BlendMode


class SketchFacadeCompositingMixin(SketchFacadeBaseMixin):
    """Configure blending and erasing through the active object-mode context."""

    __facade_doc_topic__ = "Control blending or erase drawing on this sketch's active canvas."

    def blend_mode(self, mode: c.BlendMode) -> None:
        self._ctx.blend_mode(mode)

    @overload
    def blend(
        self,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        mode: c.BlendMode,
        /,
    ) -> None: ...

    @overload
    def blend(
        self,
        image: Image,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        mode: c.BlendMode,
        /,
    ) -> None: ...

    def blend(self, *args: BlendArg) -> None:
        self._ctx_call("blend", *args)

    def erase(self) -> None:
        self._ctx.erase()

    def no_erase(self) -> None:
        self._ctx.no_erase()
