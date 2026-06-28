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
        """Delta time.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._rust.delta_time)

    @property
    def frame_count(self) -> int:
        """Frame count.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust.frame_count)

    @frame_count.setter
    def frame_count(self, value: int) -> None:
        """Frame count.
        
        Args:
            value: The value value. Expected type: `int`.
        
        Returns:
            None.
        """
        self._rust.frame_count = int(value)

    @property
    def target_frame_rate(self) -> float:
        """Target frame rate.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._rust.target_frame_rate)

    @target_frame_rate.setter
    def target_frame_rate(self, value: float) -> None:
        """Target frame rate.
        
        Args:
            value: The value value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._rust.target_frame_rate = float(value)

    def begin_frame(self) -> None:
        """Begin frame.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._rust.begin_frame_timing()

    def millis(self) -> float:
        """Millis.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._rust.millis())
