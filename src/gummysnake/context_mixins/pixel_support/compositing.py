"""Compositing, blend, and erase helpers for SketchContext pixel APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gummysnake import constants as c
from gummysnake.context_mixins.helpers import BlendArg, blend_args

if TYPE_CHECKING:
    from gummysnake.context_mixins.pixels import PixelContextMixin


def filter_pixels(ctx: PixelContextMixin, mode: c.ImageFilter, value: float | None = None) -> None:
    """Apply an image filter to the current canvas pixels."""
    ctx._record_performance_diagnostic("gpu_region_effect_pass")
    ctx.renderer.filter_pixels(mode, value)
    ctx.pixels = []


def blend_mode(ctx: PixelContextMixin, mode: c.BlendMode) -> None:
    """Set the blend mode after checking backend support."""
    if mode not in ctx.backend.capabilities.blend_modes:
        from gummysnake.exceptions import ArgumentValidationError

        raise ArgumentValidationError(
            f"Unsupported blend mode {mode!r} for backend {ctx.backend.name!r}."
        )
    ctx.state.style.blend_mode = mode
    ctx._mark_style_changed()


def blend(ctx: PixelContextMixin, *args: BlendArg) -> None:
    """Blend a source region into a destination region on the canvas."""
    parsed = blend_args(
        args,
        ctx.backend.capabilities.blend_modes,
        backend_name=ctx.backend.name,
    )
    ctx.renderer.blend_region(
        parsed.source_image,
        parsed.source_rect,
        parsed.dest_rect,
        parsed.mode,
    )


def erase(ctx: PixelContextMixin) -> None:
    """Enable erase mode for later drawing operations."""
    ctx.state.style.erasing = True
    ctx._mark_style_changed()


def no_erase(ctx: PixelContextMixin) -> None:
    """Disable erase mode for later drawing operations."""
    ctx.state.style.erasing = False
    ctx._mark_style_changed()
