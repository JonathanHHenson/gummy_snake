"""Compatibility import alias for :mod:`gummysnake.ecs`."""

# pyright: reportUnsupportedDunderAll=false

from __future__ import annotations

import sys

import gummysnake.ecs as _ecs
from gummysnake.ecs import canvas as canvas

sys.modules[__name__] = _ecs
sys.modules[__name__ + ".canvas"] = canvas

__all__ = _ecs.__all__
