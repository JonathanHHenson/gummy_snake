"""Compatibility alias for track playback internals.

The canonical area is named ``playback_export`` to avoid a same-stem collision.
Aliasing the module preserves legacy hook-patching behavior.
"""

from __future__ import annotations

import sys
from typing import Any

from gummysnake.synth.synth_runtime.playback_export import playback as _implementation


def __getattr__(name: str) -> Any:
    """Forward legacy private runtime hooks for static and dynamic callers."""

    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
