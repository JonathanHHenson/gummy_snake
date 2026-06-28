"""Global-mode media capture and video wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets.audio import AudioInput
from gummysnake.assets.media import AudioVideoCapture, Capture, Video
from gummysnake.assets.media import create_capture as _create_capture
from gummysnake.assets.media import create_capture_async as _create_capture_async
from gummysnake.assets.media import create_video as _create_video
from gummysnake.assets.media import create_video_async as _create_video_async


def create_video(path: str | Path) -> Video:
    """Create and return a video value.
    
    Args:
        path: The path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Video`.
    """
    return _create_video(path)


async def create_video_async(path: str | Path) -> Video:
    """Create and return a video async value.
    
    Args:
        path: The path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Video`.
    """
    return await _create_video_async(path)


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Create and return a capture value.
    
    Args:
        kind: The kind value. Expected type: `str`. Defaults to `'video'`.
        device: The device value. Expected type: `int | str`. Defaults to `0`.
        width: The width value. Expected type: `int | None`. Defaults to `None`.
        height: The height value. Expected type: `int | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Capture | AudioInput | AudioVideoCapture`.
    """
    return _create_capture(kind, device=device, width=width, height=height)


async def create_capture_async(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Create and return a capture async value.
    
    Args:
        kind: The kind value. Expected type: `str`. Defaults to `'video'`.
        device: The device value. Expected type: `int | str`. Defaults to `0`.
        width: The width value. Expected type: `int | None`. Defaults to `None`.
        height: The height value. Expected type: `int | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Capture | AudioInput | AudioVideoCapture`.
    """
    return await _create_capture_async(kind, device=device, width=width, height=height)


__all__ = [
    "Video",
    "Capture",
    "AudioVideoCapture",
    "create_video",
    "create_video_async",
    "create_capture",
    "create_capture_async",
]
