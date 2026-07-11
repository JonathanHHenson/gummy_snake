"""Stable composition module for object-mode media capabilities.

The focused media modules keep capture, audio, image, text/accessibility,
pixel/export, and compositing forwards independently navigable while this module
preserves the established ``SketchFacadeMediaMixin`` import and composition
surface.
"""

from __future__ import annotations

from gummysnake.sketch.facade_mixins.media_audio import SketchFacadeAudioMixin
from gummysnake.sketch.facade_mixins.media_capture import SketchFacadeCaptureMixin
from gummysnake.sketch.facade_mixins.media_compositing import SketchFacadeCompositingMixin
from gummysnake.sketch.facade_mixins.media_image import ImageCallArg, SketchFacadeImageMixin
from gummysnake.sketch.facade_mixins.media_pixels import (
    CopyArg,
    PixelValue,
    SketchFacadePixelsMixin,
)
from gummysnake.sketch.facade_mixins.media_text import SketchFacadeTextMixin, TextProperties


class SketchFacadeMediaMixin(
    SketchFacadeCaptureMixin,
    SketchFacadeAudioMixin,
    SketchFacadeImageMixin,
    SketchFacadeTextMixin,
    SketchFacadePixelsMixin,
    SketchFacadeCompositingMixin,
):
    """Stable object-mode composition of all media-related capabilities."""


__all__ = [
    "CopyArg",
    "ImageCallArg",
    "PixelValue",
    "SketchFacadeMediaMixin",
    "TextProperties",
]
