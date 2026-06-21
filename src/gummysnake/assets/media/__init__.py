"""Backend-neutral video playback and camera capture helpers."""

from __future__ import annotations

from gummysnake.assets.media.streams import (
    Capture,
    Video,
    create_capture,
    create_capture_async,
    create_video,
    create_video_async,
)

__all__ = [
    "Video",
    "Capture",
    "create_video",
    "create_video_async",
    "create_capture",
    "create_capture_async",
]
