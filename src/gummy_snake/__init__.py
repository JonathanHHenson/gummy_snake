"""Compatibility import alias for :mod:`gummysnake`."""

# pyright: reportUnsupportedDunderAll=false, reportWildcardImportFromLibrary=false

from __future__ import annotations

import sys

import gummysnake as _gummysnake
from gummysnake import *  # noqa: F403
from gummysnake import ecs as ecs

sys.modules["gummy_snake.ecs"] = ecs
sys.modules["gummy_snake.ecs.canvas"] = ecs.canvas

__all__ = _gummysnake.__all__
