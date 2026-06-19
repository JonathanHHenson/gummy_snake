"""Canvas runtime construction."""

from __future__ import annotations

from typing import cast

from p5.backends.base import Backend
from p5.backends.canvas import CanvasBackend


def canvas_default_eligibility() -> tuple[bool, str]:
    """Return whether the required canvas runtime can be constructed."""

    from p5.rust import canvas as canvas_bridge

    if not bool(canvas_bridge.is_canvas_available()):
        return False, "p5.rust._canvas is unavailable"
    if not bool(canvas_bridge.canvas_gpu_available()):
        return False, "p5_canvas did not report an available GPU adapter"
    return True, "canvas runtime is available"


def create_backend(*, headless: bool | None = None) -> Backend:
    return cast(Backend, CanvasBackend(interactive=headless is False))
