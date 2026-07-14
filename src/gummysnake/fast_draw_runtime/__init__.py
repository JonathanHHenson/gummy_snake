"""Frame-local fast drawing facade."""

from gummysnake.fast_draw_runtime.scope import FastDrawScope
from gummysnake.fast_draw_runtime.scope_helpers import SupportsText, _FastPushedScope

__all__ = ["FastDrawScope", "SupportsText", "_FastPushedScope"]
