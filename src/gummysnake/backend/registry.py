"""Canvas runtime construction."""

from __future__ import annotations

from typing import cast

from gummysnake.backend.base import Backend
from gummysnake.backend.canvas import CanvasBackend


def canvas_default_eligibility() -> tuple[bool, str]:
    from gummysnake.rust import canvas as canvas_bridge

    canvas_bridge.require_canvas_runtime()
    if not bool(canvas_bridge.canvas_gpu_available()):
        return (
            True,
            "canvas runtime is available for bounded headless rendering; GPU-accelerated "
            "drawing and native interactive presentation may be unavailable",
        )
    return True, "canvas runtime and GPU adapter are available"


def create_backend(*, headless: bool | None = None) -> Backend:
    return cast(Backend, CanvasBackend(headless=headless))
