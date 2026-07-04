"""Compositing, blend, and erase helpers for SketchContext pixel APIs."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c
from gummysnake.context_mixins.helpers import blend_args


def filter_pixels(ctx: Any, mode: c.ImageFilter, value: float | None = None) -> None:
    """Filter pixels.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        mode: The mode value. Expected type: `c.ImageFilter`.
        value: The value value. Expected type: `float | None`. Defaults to `None`.

    Returns:
        None.
    """
    ctx._record_performance_diagnostic("gpu_region_effect_pass")
    ctx.renderer.filter_pixels(mode, value)
    ctx.pixels = []


def blend_mode(ctx: Any, mode: c.BlendMode) -> None:
    """Blend mode.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        mode: The mode value. Expected type: `c.BlendMode`.

    Returns:
        None.
    """
    if mode not in ctx.backend.capabilities.blend_modes:
        from gummysnake.exceptions import ArgumentValidationError

        raise ArgumentValidationError(
            f"Unsupported blend mode {mode!r} for backend {ctx.backend.name!r}."
        )
    ctx.state.style.blend_mode = mode
    ctx._mark_style_changed()


def blend(ctx: Any, *args: Any) -> None:
    """Blend.

    Args:
        ctx: The ctx value. Expected type: `Any`.
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        None.
    """
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
    """Erase.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        None.
    """
    ctx.state.style.erasing = True
    ctx._mark_style_changed()


def no_erase(ctx: Any) -> None:
    """No erase.

    Args:
        ctx: The ctx value. Expected type: `Any`.

    Returns:
        None.
    """
    ctx.state.style.erasing = False
    ctx._mark_style_changed()
