# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
"""Frame-local fast drawing facade."""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import TYPE_CHECKING, Any, Protocol, overload

from gummysnake import constants as c
from gummysnake._fast_draw_math import (
    _mat4_axis_angle,
    _mat4_is_translation,
    _mat4_multiply,
    _mat4_post_rotate_x,
    _mat4_post_rotate_y,
    _mat4_post_rotate_z,
    _mat4_post_scale,
    _mat4_post_translate,
    _mat4_quaternion,
    _mat4_scale,
    _mat4_translation,
    _mat4_translation_then_rotation,
    _sequence3,
    _sequence4,
)
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.core.geometry import resolve_ellipse, resolve_rect
from gummysnake.drawing.primitive_fast_path import (
    PRIMITIVE_ELLIPSE,
    PRIMITIVE_RECT,
    PRIMITIVE_TRIANGLE,
    queue_fill_primitive,
)
from gummysnake.drawing.renderer3d import Mesh3D, Model3D
from gummysnake.drawing.software3d.payloads import (
    _IDENTITY4,
    Matrix4Payload,
    _coerce_matrix4_payload,
)

if TYPE_CHECKING:
    from gummysnake.context import SketchContext


class SupportsText(Protocol):
    def __str__(self) -> str: ...


class _FastPushedScope:
    __slots__ = ("_scope",)

    def __init__(self, scope: FastDrawScope) -> None:
        self._scope = scope

    def __enter__(self) -> None:
        self._scope.push()
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._scope.pop()
        return None
