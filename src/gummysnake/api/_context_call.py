"""Typed helper for forwarding global-mode calls to the active context."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from gummysnake.api.current import require_context


def context_call(name: str, *args: object, **kwargs: object) -> object:
    """Call a named method on the active sketch context."""
    method = cast(Callable[..., object], getattr(require_context(), name))
    return method(*args, **kwargs)
