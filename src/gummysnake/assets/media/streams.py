"""Media stream compatibility module.

Helper modules keep this public module path stable while tests and older code can
still patch the optional OpenCV loader through this module.
"""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets.audio import AudioInput
from gummysnake.assets.media.stream_sources import capture_factories as _capture_factories
from gummysnake.assets.media.stream_sources import stream_types as _stream_types
from gummysnake.assets.media.stream_sources.capture_factories import (
    AudioVideoCapture,
    Capture,
)
from gummysnake.assets.media.stream_sources.capture_factories import (
    _frame_to_image as _frame_to_image,
)
from gummysnake.assets.media.stream_sources.capture_factories import (
    _load_cv2_module as _load_cv2_module,
)
from gummysnake.assets.media.stream_sources.stream_types import Video


def _sync_capture_hooks() -> None:
    _capture_factories._load_cv2_module = _load_cv2_module
    _capture_factories._frame_to_image = _frame_to_image
    _stream_types._frame_to_image = _frame_to_image


def create_video(path: str | Path) -> Video:
    """Open a video file for frame-by-frame reading."""

    _sync_capture_hooks()
    return _capture_factories.create_video(path)


async def create_video_async(path: str | Path) -> Video:
    """Open a video file using the async asset-loading API."""

    _sync_capture_hooks()
    return await _capture_factories.create_video_async(path)


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Open a camera, microphone, or combined capture stream."""

    _sync_capture_hooks()
    return _capture_factories.create_capture(kind, device=device, width=width, height=height)


async def create_capture_async(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Open a capture stream using the async asset-loading API."""

    _sync_capture_hooks()
    return await _capture_factories.create_capture_async(
        kind,
        device=device,
        width=width,
        height=height,
    )


__all__ = [
    "AudioVideoCapture",
    "Capture",
    "Video",
    "_frame_to_image",
    "_load_cv2_module",
    "create_capture",
    "create_capture_async",
    "create_video",
    "create_video_async",
]
