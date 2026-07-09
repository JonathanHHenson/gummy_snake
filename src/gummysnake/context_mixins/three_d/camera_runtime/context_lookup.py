# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
"""3D camera and projection methods for SketchContext."""

from __future__ import annotations

import math
from typing import Any, cast, overload

from gummysnake.context_mixins.three_d._protocols import ThreeDContextHost
from gummysnake.drawing.renderer3d import Camera3D, Vec3
from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
)
from gummysnake.exceptions import ArgumentValidationError

Number = int | float


def _three_d(self: Any) -> ThreeDContextHost:
    return cast(ThreeDContextHost, self)
