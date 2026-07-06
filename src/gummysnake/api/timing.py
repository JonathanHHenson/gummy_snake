"""Global-mode timing and loop-control wrappers."""

from __future__ import annotations

from gummysnake.api.current import require_context


def frame_rate(value: float | None = None) -> float:
    """Get or set the target sketch frame rate.

    Args:
        value: Optional frames-per-second target to request.

    Returns:
        The active target frame rate in frames per second.
    """

    return require_context().frame_rate(value)


def frame_count() -> int:
    """Return how many frames the active sketch has started.

    Returns:
        The current frame counter value.
    """

    return require_context().frame_count


def delta_time() -> float:
    """Return elapsed time between the current and previous frame.

    Returns:
        Frame delta time in seconds.
    """

    return require_context().delta_time


def millis() -> float:
    """Return elapsed sketch runtime in milliseconds.

    Returns:
        Milliseconds since the active sketch started running.
    """

    return require_context().millis()


def no_loop() -> None:
    """Stop automatic calls to ``draw()`` after the current frame."""

    require_context().no_loop()


def loop() -> None:
    """Resume automatic calls to ``draw()`` after ``no_loop()``."""

    require_context().loop()


def redraw() -> None:
    """Request one more ``draw()`` call for a non-looping sketch."""

    require_context().redraw()


def is_looping() -> bool:
    """Return whether the active sketch is drawing continuously.

    Returns:
        ``True`` when the sketch will keep scheduling ``draw()`` calls.
    """

    return require_context().is_looping()


def get_target_frame_rate() -> float:
    """Return the configured target frame rate.

    Returns:
        The target frames per second without changing it.
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
