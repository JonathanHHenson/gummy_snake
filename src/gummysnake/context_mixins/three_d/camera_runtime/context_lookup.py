"""3D camera and projection methods for SketchContext."""

from __future__ import annotations

from typing import Any, cast

from gummysnake.context_mixins.three_d._protocols import ThreeDContextHost

Number = int | float


def _three_d(self: Any) -> ThreeDContextHost:
    return cast(ThreeDContextHost, self)
