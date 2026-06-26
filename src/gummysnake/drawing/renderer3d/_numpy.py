"""Optional NumPy helpers for 3D value objects."""

from __future__ import annotations

from typing import Any


def _require_numpy(feature: str) -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            f"{feature} requires the optional numpy dependency. "
            "Install gummy-snake with the `numpy` extra."
        ) from exc
    return np


def _readonly_numpy_array(value: Any, *, dtype: str, copy: bool) -> Any:
    np = _require_numpy("Mesh3D ndarray export")
    array = np.ascontiguousarray(value, dtype=getattr(np, dtype))
    if not copy:
        array.setflags(write=False)
        return array
    return array.copy()
