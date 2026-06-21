"""Renderer, blending, and image-processing enum values."""

from __future__ import annotations

from enum import StrEnum


class RendererMode(StrEnum):
    """Renderer modes accepted by ``create_canvas()``."""

    P2D = "p2d"
    WEBGL = "webgl"


class BlendMode(StrEnum):
    """Canvas compositing modes."""

    BLEND = "blend"
    ADD = "add"
    DARKEST = "darkest"
    LIGHTEST = "lightest"
    DIFFERENCE = "difference"
    EXCLUSION = "exclusion"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    REPLACE = "replace"


class ImageSampling(StrEnum):
    """Image sampling modes."""

    LINEAR = "linear"
    NEAREST = "nearest"


class ImageFilter(StrEnum):
    """Image filter modes."""

    THRESHOLD = "threshold"
    GRAY = "gray"
    INVERT = "invert"
    BLUR = "blur"
    POSTERIZE = "posterize"
    ERODE = "erode"
    DILATE = "dilate"


__all__ = ["BlendMode", "ImageFilter", "ImageSampling", "RendererMode"]
