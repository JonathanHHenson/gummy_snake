"""Compatibility shim for shared synth value foundations.

The canonical foundation now lives with lazy values. Keeping this module minimal
prevents composition, rendering, playback, and export imports from accumulating
in a shared pseudo-runtime module.
"""

import sys
from typing import Any

from gummysnake.synth.synth_runtime.values import foundation as _implementation


def __getattr__(name: str) -> Any:
    """Forward legacy private foundation constants for static and dynamic callers."""

    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
