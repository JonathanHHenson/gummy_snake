"""Backend registration APIs."""

from p5_py.backends.base import Backend, BackendCapabilities
from p5_py.backends.registry import (
    available_backends,
    create_backend,
    get_backend_class,
    register_backend,
)

__all__ = [
    "Backend",
    "BackendCapabilities",
    "available_backends",
    "create_backend",
    "get_backend_class",
    "register_backend",
]
