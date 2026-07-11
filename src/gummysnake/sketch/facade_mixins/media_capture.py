"""Capture and video forwards for object-mode sketches."""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets.audio import AudioInput
from gummysnake.assets.media import AudioVideoCapture, Capture, Video
from gummysnake.assets.media import create_capture as _create_capture
from gummysnake.assets.media import create_capture_async as _create_capture_async
from gummysnake.assets.media import create_video as _create_video
from gummysnake.assets.media import create_video_async as _create_video_async
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeCaptureMixin(SketchFacadeBaseMixin):
    """Create camera, microphone, and video assets from object-mode sketches."""

    __facade_doc_topic__ = "Create or open capture and video assets for this sketch."

    def create_video(self, path: str | Path) -> Video:
        return _create_video(path)

    async def create_video_async(self, path: str | Path) -> Video:
        return await _create_video_async(path)

    def create_capture(
        self,
        kind: str = "video",
        *,
        device: int | str = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> Capture | AudioInput | AudioVideoCapture:
        return _create_capture(kind, device=device, width=width, height=height)

    async def create_capture_async(
        self,
        kind: str = "video",
        *,
        device: int | str = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> Capture | AudioInput | AudioVideoCapture:
        return await _create_capture_async(kind, device=device, width=width, height=height)
