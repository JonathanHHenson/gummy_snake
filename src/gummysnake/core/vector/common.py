"""Shared helpers for vector modules."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol, Self, TypeGuard, cast

Number = int | float
_VECTOR_TYPE: type[Any] | None = None


class _VectorLike(Protocol):
    x: float
    y: float
    z: float


class _VectorBasicOps(_VectorLike, Protocol):
    def div(self, vector_or_value: Any, value: Number | None = None) -> Self: ...
    def mult(self, vector_or_value: Any, value: Number | None = None) -> Self: ...
    def sub(self, value: Any, other: Any = None, z: Number | None = None) -> Self: ...


class _VectorFullOps(_VectorBasicOps, Protocol):
    def mag(self) -> float: ...
    def copy(self) -> Self: ...
    def set(self, value: Any, y: Number | None = None, z: Number | None = None) -> Self: ...
    def add(self, value: Any, other: Any = None, z: Number | None = None) -> Self: ...
    def normalize(self) -> Self: ...
    def dot(self, value: Any, other: Any = None, z: Number | None = None) -> float: ...
    def lerp(self, value: Any, other: Any, amount: Number | None = None) -> Self: ...


def _is_registered_vector(value: Any) -> TypeGuard[_VectorLike]:
    return _VECTOR_TYPE is not None and isinstance(value, _VECTOR_TYPE)


class _DualMethod:
    """Public DualMethod value for Gummy Snake vector features."""

    def __init__(self, func: Callable[..., Any]) -> None:
        """Create a descriptor that works as both instance and class method."""
        self.func = func

    def __get__(self, obj: object | None, owner: type) -> Callable[..., Any]:
        def bound(*args: Any, **kwargs: Any) -> Any:
            return self.func(obj, *args, **kwargs)

        return bound


def register_vector_type(vector_type: type[Any]) -> None:
    """Register the concrete Vector class used by shared vector helpers."""
    global _VECTOR_TYPE
    _VECTOR_TYPE = vector_type


def make_vector(*args: Any) -> _VectorFullOps:
    """Create a Vector using the registered concrete Vector class."""
    if _VECTOR_TYPE is None:
        raise RuntimeError("Vector type has not been registered.")
    return cast(_VectorFullOps, _VECTOR_TYPE(*args))


def _components(
    value: Any | Iterable[Number] | Number,
    y: Number | None = None,
    z: Number | None = None,
) -> tuple[float, float, float]:
    """Normalize vector-like input into three float components."""
    if _is_registered_vector(value):
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


__all__ = ["Number", "make_vector", "register_vector_type", "_DualMethod", "_components"]
