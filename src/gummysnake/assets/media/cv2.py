"""OpenCV capture helper functions for media assets."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


def set_capture_dimensions(
    capture: Any, cv2_module: Any, *, width: int | None, height: int | None
) -> None:
    """Set the capture dimensions value.
    
    Args:
        capture: The capture value. Expected type: `Any`.
        cv2_module: The cv2 module value. Expected type: `Any`.
        width: The width value. Expected type: `int | None`.
        height: The height value. Expected type: `int | None`.
    
    Returns:
        None.
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


def capture_is_open(capture: Any) -> bool:
    """Capture is open using the active media context.
    
    Args:
        capture: The capture value. Expected type: `Any`.
    
    Returns:
        The return value. Type: `bool`.
    """
    is_opened = getattr(capture, "isOpened", None)
    return bool(is_opened()) if callable(is_opened) else False


def release_capture(capture: Any) -> None:
    """Release capture using the active media context.
    
    Args:
        capture: The capture value. Expected type: `Any`.
    
    Returns:
        None.
    """
    release = getattr(capture, "release", None)
    if callable(release):
        release()


def load_cv2_module() -> Any:
    """Load and return cv2 module.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `Any`.
    """
    try:
        return import_module("cv2")
    except Exception as exc:  # pragma: no cover - import failure depends on environment
        raise BackendCapabilityError(
            "Video playback/capture requires the optional media extra. Install it with "
            '`uv sync --extra media` for this project or `pip install "gummy-snake[media]"`.'
        ) from exc


__all__ = ["capture_is_open", "load_cv2_module", "release_capture", "set_capture_dimensions"]
