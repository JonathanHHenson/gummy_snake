"""Image drawing methods for SketchContext."""

from __future__ import annotations

from typing import Any, cast, overload

from gummysnake._context._protocols import SketchContextHost
from gummysnake._context.helpers import image_draw_args
from gummysnake.assets.image import CanvasImage, Image


class ImageContextMixin:
    renderer: Any
    state: Any
    _performance_diagnostics_enabled: bool
    _performance_diagnostic_image_versions: dict[int, int]

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

    def image(self, image: Image | CanvasImage, x: float, y: float, *args: float) -> None:
        self._draw_image_fast(image, x, y, *args)

    def _draw_image_fast(
        self, image: Image | CanvasImage, x: float, y: float, *args: float
    ) -> None:
        draw_args = image_draw_args(image, x, y, args, image_mode=self.state.style.image_mode)
        self._record_image_diagnostics(image)
        self.renderer.draw_image(
            image,
            draw_args.dx,
            draw_args.dy,
            draw_args.dw,
            draw_args.dh,
            self.state.style,
            self.state.transform.matrix,
            source=draw_args.source,
        )

    def _record_image_diagnostics(self, image: Image | CanvasImage) -> None:
        if not self._performance_diagnostics_enabled or not isinstance(image, Image):
            return
        cached_version = self._performance_diagnostic_image_versions.get(image.cache_key)
        if cached_version == image.version:
            cast(SketchContextHost, self)._record_performance_diagnostic("texture_cache_hit")
        else:
            cast(SketchContextHost, self)._record_performance_diagnostic("texture_upload")
            self._performance_diagnostic_image_versions[image.cache_key] = image.version
