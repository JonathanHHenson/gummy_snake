"""Global-mode timing and loop-control wrappers."""

from __future__ import annotations

from gummysnake.api.current import require_context


def frame_rate(value: float | None = None) -> float:
    """Frame rate using the active timing context.
    
    Args:
        value: The value value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().frame_rate(value)


def frame_count() -> int:
    """Frame count using the active timing context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `int`.
    """
    return require_context().frame_count


def delta_time() -> float:
    """Delta time using the active timing context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().delta_time


def millis() -> float:
    """Millis using the active timing context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().millis()


def no_loop() -> None:
    """Disable loop for subsequent operations.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().no_loop()


def loop() -> None:
    """Loop this object.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().loop()


def redraw() -> None:
    """Redraw using the active timing context.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().redraw()


def is_looping() -> bool:
    """Return whether looping is active.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `bool`.
    """
    return require_context().is_looping()


def get_target_frame_rate() -> float:
    """Return the current target frame rate value.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().frame_rate()


__all__ = [
    "frame_rate",
    "frame_count",
    "delta_time",
    "millis",
    "no_loop",
    "loop",
    "redraw",
    "is_looping",
    "get_target_frame_rate",
]
