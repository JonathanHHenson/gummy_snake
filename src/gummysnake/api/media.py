"""Global-mode media capture and video wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets.media import Capture, Video
from gummysnake.assets.media import create_capture as _create_capture
from gummysnake.assets.media import create_capture_async as _create_capture_async
from gummysnake.assets.media import create_video as _create_video
from gummysnake.assets.media import create_video_async as _create_video_async


def create_video(path: str | Path) -> Video:
    return _create_video(path)


async def create_video_async(path: str | Path) -> Video:
    return await _create_video_async(path)


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture:
    return _create_capture(kind, device=device, width=width, height=height)


async def create_capture_async(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture:
    return await _create_capture_async(kind, device=device, width=width, height=height)


__all__ = [
    "create_video",
    "create_video_async",
    "create_capture",
    "create_capture_async",
]
