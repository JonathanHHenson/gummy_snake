"""Image drawing forwards for object-mode sketches."""

from __future__ import annotations

from typing import overload

from gummysnake.assets.image import CanvasImage, Image
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin

type ImageCallArg = Image | CanvasImage | float


class SketchFacadeImageMixin(SketchFacadeBaseMixin):
    """Draw image assets through the active object-mode context."""

    __facade_doc_topic__ = "Draw image assets using this sketch's active canvas."

    @overload
    def image(self, image: Image | CanvasImage, x: float, y: float, /) -> None: ...

    @overload
    def image(
        self, image: Image | CanvasImage, x: float, y: float, width: float, height: float, /
    ) -> None: ...

    @overload
    def image(
        self,
        image: Image | CanvasImage,
        x: float,
        y: float,
        width: float,
        height: float,
        sx: float,
        sy: float,
        sw: float,
        sh: float,
        /,
    ) -> None: ...

    def image(self, *args: ImageCallArg) -> None:
        self._ctx_call("image", *args)
