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
    """Open a self-contained GIF through the Rust media runtime.

    Args:
        path: Path to a GIF file supported by the installed Rust canvas runtime.

    Returns:
        A ``Video`` object that can provide frames to image APIs.
    """

    return _create_video(path)


async def create_video_async(path: str | Path) -> Video:
    """Open a Rust-decoded GIF from an async sketch callback.

    Args:
        path: Path to a GIF file supported by the installed Rust canvas runtime.

    Returns:
        A ``Video`` object that can provide frames to image APIs.
    """

    return await _create_video_async(path)


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Create audio input or request an explicitly supported native capture source.

    Args:
        kind: Capture kind, such as ``"video"``, ``"audio"``, or ``"audio_video"``.
        device: Device index or backend-specific device name.
        width: Optional requested video width.
        height: Optional requested video height.

    Returns:
        A capture object matching the requested media kind.
    """

    return _create_capture(kind, device=device, width=width, height=height)


async def create_capture_async(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Create audio input or request native capture from an async callback.

    Args:
        kind: Capture kind, such as ``"video"``, ``"audio"``, or ``"audio_video"``.
        device: Device index or backend-specific device name.
        width: Optional requested video width.
        height: Optional requested video height.

    Returns:
        A capture object matching the requested media kind.
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
