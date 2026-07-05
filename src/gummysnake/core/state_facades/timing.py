"""Timing and frame-counter state facade."""

from __future__ import annotations

from typing import Any


class TimingState:
    """Compatibility facade for Rust-owned timing and frame counters."""

    __slots__ = ("_rust",)

    def __init__(self, rust_state: Any) -> None:
        self._rust = rust_state

    @property
    def delta_time(self) -> float:
        return float(self._rust.delta_time)

    @property
    def frame_count(self) -> int:
        return int(self._rust.frame_count)

    @frame_count.setter
    def frame_count(self, value: int) -> None:
        self._rust.frame_count = int(value)

    @property
    def target_frame_rate(self) -> float:
        return float(self._rust.target_frame_rate)

    @target_frame_rate.setter
    def target_frame_rate(self, value: float) -> None:
        self._rust.target_frame_rate = float(value)

    def begin_frame(self) -> None:
        self._rust.begin_frame_timing()

    def millis(self) -> float:
        return float(self._rust.millis())
