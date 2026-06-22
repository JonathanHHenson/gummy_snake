"""2D affine transform utilities."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

_MATRIX_HANDLE_TYPE: type[Any] | None = None


def _matrix_handle_type() -> type[Any]:
    global _MATRIX_HANDLE_TYPE
    if _MATRIX_HANDLE_TYPE is not None:
        return _MATRIX_HANDLE_TYPE
    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
    matrix_type = getattr(runtime, "Matrix2D", None)
    if not isinstance(matrix_type, type):
        raise RuntimeError(
            "The installed canvas runtime does not provide Matrix2D. Rebuild gummy_canvas."
        )
    _MATRIX_HANDLE_TYPE = matrix_type
    return matrix_type


class Matrix2D:
    """Canvas-style affine matrix: x' = ax + cy + e, y' = bx + dy + f.

    Matrix operations are backed by the required Rust canvas runtime.
    ``to_ndarray()``/``from_ndarray()`` provide optional NumPy interchange without
    making NumPy a required runtime dependency.
    """

    __slots__ = ("_handle", "_tuple")

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
            self._tuple: tuple[float, float, float, float, float, float] | None = None
            return
        matrix_type = _matrix_handle_type()
        self._handle = matrix_type(float(a), float(b), float(c), float(d), float(e), float(f))
        self._tuple = None

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
        return float(getattr(self._handle, name))

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        """Return the compact affine tuple ``(a, b, c, d, e, f)``."""

        as_tuple = getattr(self._handle, "as_tuple", None)
        if not callable(as_tuple):
            raise RuntimeError("The installed canvas runtime Matrix2D does not provide as_tuple().")
        if self._tuple is None:
            self._tuple = tuple(float(value) for value in as_tuple())  # type: ignore[assignment]
        result = self._tuple
        if result is None:
            raise RuntimeError("Matrix2D tuple cache was not initialized.")
        return result

    def multiply(self, other: Matrix2D) -> Matrix2D:
        if not isinstance(other, Matrix2D):
            return NotImplemented
        multiply = getattr(self._handle, "multiply", None)
        if not callable(multiply):
            raise RuntimeError("The installed canvas runtime Matrix2D does not provide multiply().")
        return Matrix2D(_handle=multiply(other._handle))

    def transform_point(self, x: float, y: float) -> tuple[float, float]:
        transform_point = getattr(self._handle, "transform_point", None)
        if not callable(transform_point):
            raise RuntimeError(
                "The installed canvas runtime Matrix2D does not provide transform_point()."
            )
        point = cast(Sequence[float], transform_point(float(x), float(y)))
        return (float(point[0]), float(point[1]))

    def inverse(self) -> Matrix2D:
        inverse = getattr(self._handle, "inverse", None)
        if not callable(inverse):
            raise RuntimeError("The installed canvas runtime Matrix2D does not provide inverse().")
        return Matrix2D(_handle=inverse())

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
        return cls(_handle=matrix_type.translation(float(x), float(y)))

    @classmethod
    def rotation(cls, angle: float) -> Matrix2D:
        matrix_type = _matrix_handle_type()
        return cls(_handle=matrix_type.rotation(float(angle)))

    @classmethod
    def scaling(cls, x: float, y: float | None = None) -> Matrix2D:
        matrix_type = _matrix_handle_type()
        return cls(_handle=matrix_type.scaling(float(x), None if y is None else float(y)))

    @classmethod
    def shear_x(cls, angle: float) -> Matrix2D:
        matrix_type = _matrix_handle_type()
        return cls(_handle=matrix_type.shear_x(float(angle)))

    @classmethod
    def shear_y(cls, angle: float) -> Matrix2D:
        matrix_type = _matrix_handle_type()
        return cls(_handle=matrix_type.shear_y(float(angle)))

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
