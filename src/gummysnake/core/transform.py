"""2D affine transform utilities."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, cast


def _matrix_handle_type() -> type[Any] | None:
    try:
        from gummysnake.rust.canvas import is_canvas_runtime_available, require_canvas_runtime
    except Exception:
        return None
    if not is_canvas_runtime_available():
        return None
    runtime = require_canvas_runtime()
    matrix_type = getattr(runtime, "Matrix2D", None)
    return matrix_type if isinstance(matrix_type, type) else None


class Matrix2D:
    """Canvas-style affine matrix: x' = ax + cy + e, y' = bx + dy + f.

    Matrix operations are backed by the Rust canvas runtime when it is available.
    ``to_ndarray()``/``from_ndarray()`` provide optional NumPy interchange without
    making NumPy a required runtime dependency.
    """

    __slots__ = ("_handle",)

    def __init__(
        self,
        a: float = 1.0,
        b: float = 0.0,
        c: float = 0.0,
        d: float = 1.0,
        e: float = 0.0,
        f: float = 0.0,
        *,
        _handle: Any | None = None,
    ) -> None:
        if _handle is not None:
            self._handle = _handle
            return
        matrix_type = _matrix_handle_type()
        if matrix_type is None:
            self._handle = (float(a), float(b), float(c), float(d), float(e), float(f))
        else:
            self._handle = matrix_type(float(a), float(b), float(c), float(d), float(e), float(f))

    @property
    def a(self) -> float:
        return float(self._component(0, "a"))

    @property
    def b(self) -> float:
        return float(self._component(1, "b"))

    @property
    def c(self) -> float:
        return float(self._component(2, "c"))

    @property
    def d(self) -> float:
        return float(self._component(3, "d"))

    @property
    def e(self) -> float:
        return float(self._component(4, "e"))

    @property
    def f(self) -> float:
        return float(self._component(5, "f"))

    def _component(self, index: int, name: str) -> float:
        if isinstance(self._handle, tuple):
            return self._handle[index]
        return float(getattr(self._handle, name))

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        """Return the compact affine tuple ``(a, b, c, d, e, f)``."""

        if isinstance(self._handle, tuple):
            return self._handle
        as_tuple = getattr(self._handle, "as_tuple", None)
        if callable(as_tuple):
            return tuple(float(value) for value in as_tuple())  # type: ignore[return-value]
        return (self.a, self.b, self.c, self.d, self.e, self.f)

    def multiply(self, other: Matrix2D) -> Matrix2D:
        if not isinstance(other, Matrix2D):
            return NotImplemented
        if not isinstance(self._handle, tuple) and not isinstance(other._handle, tuple):
            multiply = getattr(self._handle, "multiply", None)
            if callable(multiply):
                return Matrix2D(_handle=multiply(other._handle))
        a1, b1, c1, d1, e1, f1 = self.as_tuple()
        a2, b2, c2, d2, e2, f2 = other.as_tuple()
        return Matrix2D(
            a1 * a2 + c1 * b2,
            b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2,
            b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1,
            b1 * e2 + d1 * f2 + f1,
        )

    def transform_point(self, x: float, y: float) -> tuple[float, float]:
        transform_point = getattr(self._handle, "transform_point", None)
        if callable(transform_point):
            point = cast(Sequence[float], transform_point(float(x), float(y)))
            return (float(point[0]), float(point[1]))
        a, b, c, d, e, f = self.as_tuple()
        return a * x + c * y + e, b * x + d * y + f

    def inverse(self) -> Matrix2D:
        inverse = getattr(self._handle, "inverse", None)
        if callable(inverse):
            try:
                return Matrix2D(_handle=inverse())
            except ValueError:
                raise
        a, b, c, d, e, f = self.as_tuple()
        determinant = a * d - b * c
        if abs(determinant) < 1e-12:
            raise ValueError("Matrix is not invertible.")
        return Matrix2D(
            d / determinant,
            -b / determinant,
            -c / determinant,
            a / determinant,
            (c * f - d * e) / determinant,
            (b * e - a * f) / determinant,
        )

    def to_ndarray(self, *, shape: tuple[int, int] = (3, 3), copy: bool = True) -> Any:
        """Export this matrix as a NumPy ``ndarray``.

        ``shape=(3, 3)`` returns the full homogeneous matrix. ``shape=(2, 3)``
        returns the affine rows ``[[a, c, e], [b, d, f]]``. NumPy is optional;
        calling this method without NumPy installed raises an actionable error.
        """

        try:
            import numpy as np
        except ImportError as exc:
            raise ImportError(
                "Matrix2D.to_ndarray() requires the optional numpy dependency. "
                "Install gummy-snake with the `numpy` extra."
            ) from exc
        a, b, c, d, e, f = self.as_tuple()
        if shape == (3, 3):
            array = np.array(((a, c, e), (b, d, f), (0.0, 0.0, 1.0)), dtype=np.float64)
        elif shape == (2, 3):
            array = np.array(((a, c, e), (b, d, f)), dtype=np.float64)
        else:
            raise ValueError("Matrix2D ndarray shape must be (3, 3) or (2, 3).")
        return array.copy() if copy else array

    def __array__(self, dtype: Any = None, copy: bool | None = None) -> Any:
        array = self.to_ndarray(copy=False)
        if dtype is not None:
            return array.astype(dtype, copy=False if copy is None else copy)
        return array.copy() if copy else array

    @classmethod
    def from_ndarray(cls, value: Any) -> Matrix2D:
        """Create a matrix from a NumPy-compatible array with shape ``(3, 3)`` or ``(2, 3)``."""

        try:
            import numpy as np
        except ImportError as exc:
            raise ImportError(
                "Matrix2D.from_ndarray() requires the optional numpy dependency. "
                "Install gummy-snake with the `numpy` extra."
            ) from exc
        array = np.asarray(value, dtype=np.float64)
        if array.shape == (3, 3):
            if not np.allclose(array[2], (0.0, 0.0, 1.0)):
                raise ValueError("Matrix2D homogeneous ndarray bottom row must be [0, 0, 1].")
            return cls(
                float(array[0, 0]),
                float(array[1, 0]),
                float(array[0, 1]),
                float(array[1, 1]),
                float(array[0, 2]),
                float(array[1, 2]),
            )
        if array.shape == (2, 3):
            return cls(
                float(array[0, 0]),
                float(array[1, 0]),
                float(array[0, 1]),
                float(array[1, 1]),
                float(array[0, 2]),
                float(array[1, 2]),
            )
        raise ValueError("Matrix2D ndarray input must have shape (3, 3) or (2, 3).")

    @classmethod
    def identity(cls) -> Matrix2D:
        return cls()

    @classmethod
    def translation(cls, x: float, y: float) -> Matrix2D:
        matrix_type = _matrix_handle_type()
        if matrix_type is not None and hasattr(matrix_type, "translation"):
            return cls(_handle=matrix_type.translation(float(x), float(y)))
        return cls(1.0, 0.0, 0.0, 1.0, x, y)

    @classmethod
    def rotation(cls, angle: float) -> Matrix2D:
        matrix_type = _matrix_handle_type()
        if matrix_type is not None and hasattr(matrix_type, "rotation"):
            return cls(_handle=matrix_type.rotation(float(angle)))
        cosine = math.cos(angle)
        sine = math.sin(angle)
        return cls(cosine, sine, -sine, cosine, 0.0, 0.0)

    @classmethod
    def scaling(cls, x: float, y: float | None = None) -> Matrix2D:
        matrix_type = _matrix_handle_type()
        if matrix_type is not None and hasattr(matrix_type, "scaling"):
            return cls(_handle=matrix_type.scaling(float(x), None if y is None else float(y)))
        sy = x if y is None else y
        return cls(x, 0.0, 0.0, sy, 0.0, 0.0)

    @classmethod
    def shear_x(cls, angle: float) -> Matrix2D:
        matrix_type = _matrix_handle_type()
        if matrix_type is not None and hasattr(matrix_type, "shear_x"):
            return cls(_handle=matrix_type.shear_x(float(angle)))
        return cls(1.0, 0.0, math.tan(angle), 1.0, 0.0, 0.0)

    @classmethod
    def shear_y(cls, angle: float) -> Matrix2D:
        matrix_type = _matrix_handle_type()
        if matrix_type is not None and hasattr(matrix_type, "shear_y"):
            return cls(_handle=matrix_type.shear_y(float(angle)))
        return cls(1.0, math.tan(angle), 0.0, 1.0, 0.0, 0.0)

    def __iter__(self):
        return iter(self.as_tuple())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Matrix2D):
            return NotImplemented
        return self.as_tuple() == other.as_tuple()

    def __hash__(self) -> int:
        return hash(self.as_tuple())

    def __repr__(self) -> str:
        return (
            f"Matrix2D(a={self.a!r}, b={self.b!r}, c={self.c!r}, "
            f"d={self.d!r}, e={self.e!r}, f={self.f!r})"
        )
