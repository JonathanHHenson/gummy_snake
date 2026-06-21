# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""Shared helpers for vector modules."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, cast

Number = int | float
_VECTOR_TYPE: type[Any] | None = None


class _DualMethod:
    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __get__(self, obj: object | None, owner: type) -> Callable[..., Any]:
        def bound(*args: Any, **kwargs: Any) -> Any:
            return self.func(obj, *args, **kwargs)

        return bound


def register_vector_type(vector_type: type[Any]) -> None:
    global _VECTOR_TYPE
    _VECTOR_TYPE = vector_type


def make_vector(*args: Any) -> Any:
    if _VECTOR_TYPE is None:
        raise RuntimeError("Vector type has not been registered.")
    return _VECTOR_TYPE(*args)


def _components(
    value: Any | Iterable[Number] | Number,
    y: Number | None = None,
    z: Number | None = None,
) -> tuple[float, float, float]:
    if _VECTOR_TYPE is not None and isinstance(value, _VECTOR_TYPE):
        return value.x, value.y, value.z
    if y is not None or z is not None:
        scalar = cast(Number, value)
        return float(scalar), float(0 if y is None else y), float(0 if z is None else z)
    if isinstance(value, int | float):
        return float(value), float(value), float(value)
    items = tuple(value)
    if len(items) == 2:
        return float(items[0]), float(items[1]), 0.0
    if len(items) == 3:
        return float(items[0]), float(items[1]), float(items[2])
    msg = "Vector operands must be a scalar, Vector, or 2/3-item iterable."
    raise TypeError(msg)
