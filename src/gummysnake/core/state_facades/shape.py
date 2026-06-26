"""Shape capture state facade."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c


class ShapeState:
    """Compatibility facade for Rust-owned begin_shape capture buffers."""

    __slots__ = ("_rust",)

    def __init__(self, rust_state: Any) -> None:
        self._rust = rust_state

    @property
    def active(self) -> bool:
        return bool(self._rust.shape_active)

    @active.setter
    def active(self, value: bool) -> None:
        if not value:
            self._rust.reset_shape_capture()

    @property
    def vertices(self) -> list[tuple[float, float]]:
        return [tuple(point) for point in self._rust.shape_vertices()]

    @property
    def contours(self) -> list[list[tuple[float, float]]]:
        return [[tuple(point) for point in contour] for contour in self._rust.shape_contours()]

    @property
    def contour_active(self) -> bool:
        return bool(self._rust.contour_active)

    @contour_active.setter
    def contour_active(self, value: bool) -> None:
        if not value:
            self._rust.reset_contour_capture()

    @property
    def contour_vertices(self) -> list[tuple[float, float]]:
        if not self.contour_active:
            return []
        return [tuple(point) for point in self._rust.active_vertices()]

    @property
    def kind(self) -> c.ShapeKind | None:
        value = self._rust.shape_kind
        return None if value is None else c.ShapeKind(value)
