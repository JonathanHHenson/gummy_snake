"""Compatibility shim for builder-context internals.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.composition.builder_context`.
"""

import sys
from typing import Any

from gummysnake.synth.synth_runtime.composition import builder_context as _implementation
from gummysnake.synth.synth_runtime.composition.builder_context import _NODE_COUNTER

__all__ = ("_NODE_COUNTER",)


def __getattr__(name: str) -> Any:
    """Forward legacy private builder state for static and dynamic callers."""

    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
