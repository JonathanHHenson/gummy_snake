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
        """A.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._component(0, "a"))

    @property
    def b(self) -> float:
        """B.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._component(1, "b"))

    @property
    def c(self) -> float:
        """C.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._component(2, "c"))

    @property
    def d(self) -> float:
        """D.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._component(3, "d"))

    @property
    def e(self) -> float:
        """E.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._component(4, "e"))

    @property
    def f(self) -> float:
        """F.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._component(5, "f"))

    def _component(self, index: int, name: str) -> float:
        return float(getattr(self._handle, name))

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        """Return the compact affine tuple ``(a, b, c, d, e, f)``.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[float, float, float, float, float, float]`.
        """

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
        """Multiply.
        
        Args:
            other: The other value. Expected type: `Matrix2D`.
        
        Returns:
            The return value. Type: `Matrix2D`.
        """
        if not isinstance(other, Matrix2D):
            return NotImplemented
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
        """Transform point.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
        
        Returns:
            The return value. Type: `tuple[float, float]`.
        """
        transform_point = getattr(self._handle, "transform_point", None)
        if callable(transform_point):
            point = cast(Sequence[float], transform_point(float(x), float(y)))
            return (float(point[0]), float(point[1]))
        a, b, c, d, e, f = self.as_tuple()
        x = float(x)
        y = float(y)
        return (a * x + c * y + e, b * x + d * y + f)

    def inverse(self) -> Matrix2D:
        """Inverse.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Matrix2D`.
        """
        inverse = getattr(self._handle, "inverse", None)
        if callable(inverse):
            return Matrix2D(_handle=inverse())
        a, b, c, d, e, f = self.as_tuple()
        determinant = a * d - b * c
        if determinant == 0:
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
        
        Args:
            shape: The shape value. Expected type: `tuple[int, int]`. Defaults to `(3, 3)`.
            copy: The copy value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            The return value. Type: `Any`.
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
        """Create a matrix from a NumPy-compatible array with shape ``(3, 3)`` or ``(2, 3)``.
        
        Args:
            value: The value value. Expected type: `Any`.
        
        Returns:
            The return value. Type: `Matrix2D`.
        """

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
        """Identity.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Matrix2D`.
        """
        return cls()

    @classmethod
    def translation(cls, x: float, y: float) -> Matrix2D:
        """Translation.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
        
        Returns:
            The return value. Type: `Matrix2D`.
        """
        matrix_type = _matrix_handle_type()
        translation = getattr(matrix_type, "translation", None)
        if callable(translation):
            return cls(_handle=translation(float(x), float(y)))
        return cls(1.0, 0.0, 0.0, 1.0, float(x), float(y))

    @classmethod
    def rotation(cls, angle: float) -> Matrix2D:
        """Rotation.
        
        Args:
            angle: The angle value. Expected type: `float`.
        
        Returns:
            The return value. Type: `Matrix2D`.
        """
        matrix_type = _matrix_handle_type()
        rotation = getattr(matrix_type, "rotation", None)
        if callable(rotation):
            return cls(_handle=rotation(float(angle)))
        import math

        cosine = math.cos(float(angle))
        sine = math.sin(float(angle))
        return cls(cosine, sine, -sine, cosine, 0.0, 0.0)

    @classmethod
    def scaling(cls, x: float, y: float | None = None) -> Matrix2D:
        """Scaling.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Matrix2D`.
        """
        matrix_type = _matrix_handle_type()
        scaling = getattr(matrix_type, "scaling", None)
        if callable(scaling):
            return cls(_handle=scaling(float(x), None if y is None else float(y)))
        scale_y = float(x) if y is None else float(y)
        return cls(float(x), 0.0, 0.0, scale_y, 0.0, 0.0)

    @classmethod
    def shear_x(cls, angle: float) -> Matrix2D:
        """Shear x.
        
        Args:
            angle: The angle value. Expected type: `float`.
        
        Returns:
            The return value. Type: `Matrix2D`.
        """
        matrix_type = _matrix_handle_type()
        shear_x = getattr(matrix_type, "shear_x", None)
        if callable(shear_x):
            return cls(_handle=shear_x(float(angle)))
        import math

        return cls(1.0, 0.0, math.tan(float(angle)), 1.0, 0.0, 0.0)

    @classmethod
    def shear_y(cls, angle: float) -> Matrix2D:
        """Shear y.
        
        Args:
            angle: The angle value. Expected type: `float`.
        
        Returns:
            The return value. Type: `Matrix2D`.
        """
        matrix_type = _matrix_handle_type()
        shear_y = getattr(matrix_type, "shear_y", None)
        if callable(shear_y):
            return cls(_handle=shear_y(float(angle)))
        import math

        return cls(1.0, math.tan(float(angle)), 0.0, 1.0, 0.0, 0.0)

    def __iter__(self):
        """Iter.
        
        Args:
            None.
        
        Returns:
            The return value.
        """
        return iter(self.as_tuple())

    def __eq__(self, other: object) -> bool:
        """Eq.
        
        Args:
            other: The other value. Expected type: `object`.
        
        Returns:
            The return value. Type: `bool`.
        """
        if not isinstance(other, Matrix2D):
            return NotImplemented
        return self.as_tuple() == other.as_tuple()

    def __hash__(self) -> int:
        """Hash.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return hash(self.as_tuple())

    def __repr__(self) -> str:
        """Repr.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str`.
        """
        return (
            f"Matrix2D(a={self.a!r}, b={self.b!r}, c={self.c!r}, "
            f"d={self.d!r}, e={self.e!r}, f={self.f!r})"
        )
