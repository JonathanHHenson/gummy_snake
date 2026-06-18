"""Backend registration APIs."""

from p5.backends.base import Backend, BackendCapabilities
from p5.backends.registry import (
    available_backends,
    canvas_default_eligibility,
    create_backend,
    get_backend_class,
    register_backend,
    select_default_backend,
)

__all__ = [
    "Backend",
    "BackendCapabilities",
    "available_backends",
    "canvas_default_eligibility",
    "create_backend",
    "get_backend_class",
    "register_backend",
    "select_default_backend",
]
