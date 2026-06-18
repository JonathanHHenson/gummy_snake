"""Backend registration and lazy loading."""

from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from p5.backends.base import Backend
from p5.exceptions import BackendCapabilityError

type BackendEntry = type[Any] | str

_BACKENDS: dict[str, BackendEntry] = {
    "canvas": "p5.backends.canvas:CanvasBackend",
    "headless": "p5.backends.headless:HeadlessBackend",
    "pillow": "p5.backends.headless:HeadlessBackend",
    "pyglet": "p5.backends.pyglet:PygletBackend",
}

DEFAULT_BACKEND = "pyglet"
CANVAS_DEFAULT_PARITY_READY = False


def register_backend(name: str, backend: BackendEntry) -> None:
    if not name:
        raise ValueError("Backend name cannot be empty.")
    _BACKENDS[name] = backend


def available_backends() -> tuple[str, ...]:
    return tuple(sorted(_BACKENDS))


def canvas_default_eligibility() -> tuple[bool, str]:
    """Return whether ``canvas`` may replace the interactive default backend.

    The migration gate is intentionally conservative. Importability alone is
    not enough: the renderer must have documented parity sign-off, a working GPU
    adapter path, and native window/surface support before automatic selection
    can move away from the current Pyglet default.
    """

    if not CANVAS_DEFAULT_PARITY_READY:
        return False, "canvas GPU parity criteria are not marked complete"

    try:
        canvas_bridge = import_module("p5.rust.canvas")
    except ImportError as exc:
        return False, f"canvas bridge import failed: {exc}"

    if not bool(canvas_bridge.is_canvas_available()):
        return False, "p5.rust._canvas is unavailable"
    if not bool(canvas_bridge.canvas_gpu_available()):
        return False, "p5_canvas did not report an available GPU adapter"
    if not bool(canvas_bridge.canvas_native_window_available()):
        return False, "p5_canvas did not report native window/surface support"
    return True, "canvas GPU parity criteria and native runtime checks passed"


def select_default_backend() -> str:
    """Select the backend used when a sketch does not request one explicitly."""

    eligible, _reason = canvas_default_eligibility()
    if eligible:
        return "canvas"
    return DEFAULT_BACKEND


def get_backend_class(name: str) -> type[Backend]:
    try:
        entry = _BACKENDS[name]
    except KeyError as exc:
        available = ", ".join(available_backends())
        raise BackendCapabilityError(
            f"Unknown backend {name!r}. Available backends: {available}."
        ) from exc
    if isinstance(entry, str):
        module_name, class_name = entry.split(":", 1)
        module = import_module(module_name)
        backend_class = cast(type[Backend], getattr(module, class_name))
        _BACKENDS[name] = backend_class
        return backend_class
    return cast(type[Backend], entry)


def create_backend(name: str) -> Backend:
    if name == "auto":
        name = select_default_backend()
    backend_class = get_backend_class(name)
    return backend_class()
