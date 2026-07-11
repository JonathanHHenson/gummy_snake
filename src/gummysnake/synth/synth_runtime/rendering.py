"""Compatibility alias for physical rendering and Rust bridge functions.

The module object is intentionally aliased so legacy test and integration code
that patches runtime bridge hooks affects the canonical implementation.
"""

from __future__ import annotations

import sys
from typing import Any

from gummysnake.synth.synth_runtime.physical import rendering as _implementation


def __getattr__(name: str) -> Any:
    """Forward legacy private runtime hooks for static and dynamic callers."""

    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
