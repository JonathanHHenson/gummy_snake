"""OpenCV capture helper functions for media assets."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Protocol

from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


class CaptureLike(Protocol):
    """Subset of OpenCV capture objects used by Gummy Snake."""

    def set(self, prop: int, value: int) -> object:
        """Set a capture property by OpenCV property id."""
        ...

    def isOpened(self) -> bool:
        """Return whether the capture is open."""
        ...

    def release(self) -> object:
        """Release the capture device or file."""
        ...


def set_capture_dimensions(
    capture: CaptureLike, cv2_module: ModuleType, *, width: int | None, height: int | None
) -> None:
    """Request capture dimensions on an OpenCV capture object.

    Args:
        capture: OpenCV-style capture object.
        cv2_module: Imported ``cv2`` module used for property constants.
        width: Optional requested frame width.
        height: Optional requested frame height.
    """
    set_prop = getattr(capture, "set", None)
    if not callable(set_prop):
        return
    if width is not None:
        if width <= 0:
            raise ArgumentValidationError("create_capture() width must be positive when provided.")
        prop = getattr(cv2_module, "CAP_PROP_FRAME_WIDTH", None)
        if prop is not None:
            set_prop(prop, int(width))
    if height is not None:
        if height <= 0:
            raise ArgumentValidationError("create_capture() height must be positive when provided.")
        prop = getattr(cv2_module, "CAP_PROP_FRAME_HEIGHT", None)
        if prop is not None:
            set_prop(prop, int(height))


def capture_is_open(capture: CaptureLike) -> bool:
    """Return whether an OpenCV capture object is open.

    Args:
        capture: OpenCV-style capture object.

    Returns:
        ``True`` when the capture reports that it is open.
    """
    is_opened = getattr(capture, "isOpened", None)
    return bool(is_opened()) if callable(is_opened) else False


def release_capture(capture: CaptureLike) -> None:
    """Release an OpenCV capture object if it supports release.

    Args:
        capture: OpenCV-style capture object.
    """
    release = getattr(capture, "release", None)
    if callable(release):
        release()


def load_cv2_module() -> ModuleType:
    """Import OpenCV or raise a Gummy Snake capability error.

    Returns:
        The imported ``cv2`` module.
    """
    try:
        return import_module("cv2")
    except Exception as exc:  # pragma: no cover - import failure depends on environment
        raise BackendCapabilityError(
            "Video playback/capture requires the optional media extra. Install it with "
            '`uv sync --extra media` for this project or `pip install "gummy-snake[media]"`.'
        ) from exc


__all__ = [
    "CaptureLike",
    "capture_is_open",
    "load_cv2_module",
    "release_capture",
    "set_capture_dimensions",
]
