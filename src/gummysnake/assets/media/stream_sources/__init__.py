"""Implementation chunks for :mod:`gummysnake.assets.media.streams`."""

from __future__ import annotations

from gummysnake.assets.media.stream_sources.capture_factories import (
    AudioVideoCapture,
    Capture,
    create_capture,
    create_capture_async,
    create_video,
    create_video_async,
)
from gummysnake.assets.media.stream_sources.stream_types import Video

__all__ = [
    "AudioVideoCapture",
    "Capture",
    "Video",
    "create_capture",
    "create_capture_async",
    "create_video",
    "create_video_async",
]
