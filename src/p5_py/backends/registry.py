"""Backend registration and lazy loading."""

from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from p5_py.backends.base import Backend
from p5_py.exceptions import BackendCapabilityError

type BackendEntry = type[Any] | str

_BACKENDS: dict[str, BackendEntry] = {
    "headless": "p5_py.backends.headless:HeadlessBackend",
    "pillow": "p5_py.backends.headless:HeadlessBackend",
    "pyglet": "p5_py.backends.pyglet:PygletBackend",
}


def register_backend(name: str, backend: BackendEntry) -> None:
    if not name:
        raise ValueError("Backend name cannot be empty.")
    _BACKENDS[name] = backend


def available_backends() -> tuple[str, ...]:
    return tuple(sorted(_BACKENDS))


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
    backend_class = get_backend_class(name)
    return backend_class()
