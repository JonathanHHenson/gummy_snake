"""Compositing, blend, and erase helpers for SketchContext pixel APIs."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c
from gummysnake.context_mixins.helpers import blend_args


def filter_pixels(ctx: Any, mode: c.ImageFilter, value: float | None = None) -> None:
    ctx._record_performance_diagnostic("cpu_compositing_fallback")
    ctx._record_performance_diagnostic("pixel_upload")
    ctx.renderer.filter_pixels(mode, value)
    ctx.pixels = []


def blend_mode(ctx: Any, mode: c.BlendMode) -> None:
    if mode not in ctx.backend.capabilities.blend_modes:
        from gummysnake.exceptions import ArgumentValidationError

        raise ArgumentValidationError(
            f"Unsupported blend mode {mode!r} for backend {ctx.backend.name!r}."
        )
    ctx.state.style.blend_mode = mode
    ctx._mark_style_changed()


def blend(ctx: Any, *args: Any) -> None:
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


def erase(ctx: Any) -> None:
    ctx.state.style.erasing = True
    ctx._mark_style_changed()


def no_erase(ctx: Any) -> None:
    ctx.state.style.erasing = False
    ctx._mark_style_changed()
