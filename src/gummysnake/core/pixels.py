"""Public pixel buffer type and internal dirty-region helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class PixelBuffer(bytearray):
    """Mutable RGBA byte buffer returned by ``load_pixels()``.

    ``PixelBuffer`` preserves Gummy Snake's list-like slice/equality behavior,
    supports the Python buffer protocol, and tracks a conservative dirty byte
    range so ``update_pixels()`` can upload only changed physical RGBA regions
    when the runtime supports it.
    """

    _dirty_start: int | None
    _dirty_end: int | None

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        self._dirty_start = None
        self._dirty_end = None

    def __setitem__(self, key: Any, value: Any) -> None:
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            changed = range(start, stop, step)
            super().__setitem__(key, value)
            if len(changed) > 0:
                first = changed[0]
                last = changed[-1]
                self._mark_dirty(min(first, last), max(first, last) + 1)
            return
        super().__setitem__(key, value)
        index = key if key >= 0 else len(self) + key
        self._mark_dirty(index, index + 1)

    def __getitem__(self, key: Any) -> Any:
        value = super().__getitem__(key)
        if isinstance(key, slice):
            return list(value)
        return value

    def __eq__(self, value: object) -> bool:
        if isinstance(value, list | tuple):
            return len(self) == len(value) and all(
                left == right for left, right in zip(self, value, strict=True)
            )
        return super().__eq__(value)

    def dirty_range(self) -> tuple[int, int] | None:
        if self._dirty_start is None or self._dirty_end is None:
            return None
        return self._dirty_start, self._dirty_end

    def clear_dirty(self) -> None:
        self._dirty_start = None
        self._dirty_end = None

    def _mark_dirty(self, start: int, end: int) -> None:
        if end <= start:
            return
        self._dirty_start = start if self._dirty_start is None else min(self._dirty_start, start)
        self._dirty_end = end if self._dirty_end is None else max(self._dirty_end, end)


@dataclass(frozen=True, slots=True)
class DirtyPixelRegion:
    byte_start: int
    byte_end: int
    x: int
    y: int
    width: int
    height: int
    valid: bool
    empty: bool

    @property
    def byte_slice(self) -> slice:
        return slice(self.byte_start, self.byte_end)


def dirty_pixel_region(
    buffer_length: int,
    physical_width: int,
    physical_height: int,
    dirty: tuple[int, int],
) -> DirtyPixelRegion:
    if physical_width <= 0 or physical_height <= 0:
        return _invalid_region()
    total = physical_width * physical_height * 4
    if buffer_length != total:
        return _invalid_region()

    start, end = dirty
    if end <= start:
        return _empty_region()

    pixel_count = physical_width * physical_height
    start_pixel = max(0, start // 4)
    end_pixel = min(pixel_count, (end + 3) // 4)
    if end_pixel <= start_pixel:
        return _empty_region()

    start_row, start_col = divmod(start_pixel, physical_width)
    end_row, end_col = divmod(end_pixel - 1, physical_width)
    if start_row == end_row:
        width = end_col - start_col + 1
        byte_start = (start_row * physical_width + start_col) * 4
        byte_end = byte_start + width * 4
        return DirtyPixelRegion(
            byte_start,
            byte_end,
            start_col,
            start_row,
            width,
            1,
            valid=True,
            empty=False,
        )

    byte_start = start_row * physical_width * 4
    byte_end = (end_row + 1) * physical_width * 4
    return DirtyPixelRegion(
        byte_start,
        byte_end,
        0,
        start_row,
        physical_width,
        end_row - start_row + 1,
        valid=True,
        empty=False,
    )


def _invalid_region() -> DirtyPixelRegion:
    return DirtyPixelRegion(0, 0, 0, 0, 0, 0, valid=False, empty=False)


def _empty_region() -> DirtyPixelRegion:
    return DirtyPixelRegion(0, 0, 0, 0, 0, 0, valid=True, empty=True)
