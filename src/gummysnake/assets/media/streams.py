"""Public media stream factories.

The facade owns dependency selection and passes it explicitly to the focused
factory and stream modules, avoiding cross-module mutable hook state.
"""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets.audio import AudioInput
from gummysnake.assets.media.cv2 import load_cv2_module
from gummysnake.assets.media.frame import frame_to_image
from gummysnake.assets.media.stream_sources import capture_factories as _capture_factories
from gummysnake.assets.media.stream_sources.capture_factories import AudioVideoCapture, Capture
from gummysnake.assets.media.stream_sources.stream_types import Video


def create_video(path: str | Path) -> Video:
    """Open a video file for frame-by-frame reading."""

    return _capture_factories.create_video(
        path,
        cv2_loader=load_cv2_module,
        frame_converter=frame_to_image,
    )


async def create_video_async(path: str | Path) -> Video:
    """Open a video file using the async asset-loading API."""

    return await _capture_factories.create_video_async(
        path,
        cv2_loader=load_cv2_module,
        frame_converter=frame_to_image,
    )


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Open a camera, microphone, or combined capture stream."""

    return _capture_factories.create_capture(
        kind,
        device=device,
        width=width,
        height=height,
        cv2_loader=load_cv2_module,
        frame_converter=frame_to_image,
    )


async def create_capture_async(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Open a capture stream using the async asset-loading API."""

    return await _capture_factories.create_capture_async(
        kind,
        device=device,
        width=width,
        height=height,
        cv2_loader=load_cv2_module,
        frame_converter=frame_to_image,
    )


__all__ = [
    "AudioVideoCapture",
    "Capture",
    "Video",
    "create_capture",
    "create_capture_async",
    "create_video",
    "create_video_async",
]
