"""Frame-local fast drawing facade."""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Protocol

from gummysnake.drawing.software3d.payloads import _IDENTITY4

if TYPE_CHECKING:
    from gummysnake.fast_draw_runtime.scope import FastDrawScope


class SupportsText(Protocol):
    def __str__(self) -> str: ...


class _FastPushedScope:
    __slots__ = ("_scope",)

    def __init__(self, scope: FastDrawScope) -> None:
        self._scope = scope

    def __enter__(self) -> None:
        scope = self._scope
        if scope._transform3d_active:
            scope.push()
        else:
            scope._transform3d_stack.append(None)
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        scope = self._scope
        transform = scope._transform3d_stack.pop()
        if transform is None:
            scope._transform3d = _IDENTITY4
            scope._transform3d_active = False
            scope._transform3d_compact = 0
        else:
            scope._transform3d = transform
            scope._transform3d_active = True
            scope._transform3d_compact = 0
        return None
