"""Optional NumPy helpers for 3D value objects."""

from __future__ import annotations

from typing import Any, Protocol, cast


class NumpyArrayFlags(Protocol):
    """Small subset of NumPy array flags used by public tests and callers."""

    writeable: bool


class NumpyArray(Protocol):
    """Small runtime protocol for arrays returned by optional NumPy exports."""

    @property
    def shape(self) -> tuple[int, ...]:
        """Array dimensions."""
        ...

    @property
    def flags(self) -> NumpyArrayFlags:
        """Mutable array flags, including whether the array can be written to."""
        ...

    def copy(self) -> NumpyArray:
        """Return a new writable array with the same values."""
        ...

    def setflags(self, *, write: bool) -> None:
        """Change whether the array can be written to."""
        ...

    def tolist(self) -> list[object]:
        """Return the array values as nested Python lists."""
        ...


def _require_numpy(feature: str) -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            f"{feature} requires the optional numpy dependency. "
            "Install gummy-snake with the `numpy` extra."
        ) from exc
    return np


def _readonly_numpy_array(value: object, *, dtype: str, copy: bool) -> NumpyArray:
    np = _require_numpy("Mesh3D ndarray export")
    array = np.ascontiguousarray(value, dtype=getattr(np, dtype))
    if not copy:
        array.setflags(write=False)
        return cast(NumpyArray, array)
    return cast(NumpyArray, array.copy())
