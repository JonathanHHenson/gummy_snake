"""Canvas runtime construction."""

from __future__ import annotations

from typing import cast

from gummysnake.backend.base import Backend
from gummysnake.backend.canvas import CanvasBackend


def canvas_default_eligibility() -> tuple[bool, str]:
    """Return whether the required canvas runtime can be constructed."""

    from gummysnake.rust import canvas as canvas_bridge

    if not bool(canvas_bridge.is_canvas_runtime_available()):
        return False, "gummysnake.rust._canvas is unavailable"
    if not bool(canvas_bridge.canvas_gpu_available()):
        return False, "gummy_canvas did not report an available GPU adapter"
    return True, "canvas runtime is available"


def create_backend(*, headless: bool | None = None) -> Backend:
    return cast(Backend, CanvasBackend(headless=headless))
