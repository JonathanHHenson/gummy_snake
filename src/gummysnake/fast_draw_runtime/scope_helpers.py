"""Frame-local fast drawing facade."""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from gummysnake.fast_draw_runtime.scope import FastDrawScope


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
