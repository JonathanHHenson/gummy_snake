from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from gummysnake.assets.audio import AudioBuffer, AudioInput, create_audio_in
from gummysnake.assets.image import Image
from gummysnake.assets.media.cv2 import (
    capture_is_open as _capture_is_open,
)
from gummysnake.assets.media.cv2 import (
    load_cv2_module as _load_cv2_module,
)
from gummysnake.assets.media.cv2 import (
    release_capture as _release_capture,
)
from gummysnake.assets.media.cv2 import (
    set_capture_dimensions as _set_capture_dimensions,
)
from gummysnake.assets.media.frame import frame_to_image as _frame_to_image
from gummysnake.assets.media.stream_sources.stream_types import (
    _AUDIO_KINDS,
    _AUDIO_VIDEO_KINDS,
    _VIDEO_KINDS,
    Video,
    _FrameStreamBase,
)
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


class Capture(_FrameStreamBase):
    """Camera capture stream with explicit lifecycle and frame reads."""

    def __init__(self, capture: Any, *, device: int | str, cv2_module: Any) -> None:
        """Create a camera capture stream from an OpenCV capture object."""
        super().__init__(
            capture,
            cv2_module=cv2_module,
            playing=True,
            closed_error_message="This capture has already been closed.",
        )
        self._device = device

    @property
    def device(self) -> int | str:
        """Camera device identifier used to open this capture."""

        return self._device

    def read(self) -> Image | None:
        """Read a frame from the camera.

        Returns:
            A copy of the newest frame as an ``Image``, or ``None`` if no frame is available.
        """

        self._ensure_open()
        if not self._playing and self._last_frame is not None:
            return self._last_frame.copy()
        read = getattr(self._capture, "read", None)
        if not callable(read):
            raise BackendCapabilityError("Camera frame reading is unavailable on this system.")
        ok, frame = cast(tuple[bool, Any], read())
        if not ok or frame is None:
            return None
        image = _frame_to_image(frame)
        self._last_frame = image
        return image.copy()


class AudioVideoCapture:
    """Combined camera and audio-input capture stream.

    Video frames are provided by the same native camera path as ``Capture``;
    audio samples are supplied by the headless-safe ``AudioInput`` object so
    analysis and audio-reactive sketches can share one capture handle.
    """

    def __init__(self, video: Capture, audio: AudioInput) -> None:
        """Create a combined capture object from video and audio streams."""
        self.video = video
        self.audio = audio

    @property
    def width(self) -> int:
        """Video capture width in pixels."""

        return self.video.width

    @property
    def height(self) -> int:
        """Video capture height in pixels."""

        return self.video.height

    @property
    def device(self) -> int | str:
        """Camera device identifier used by the video stream."""

        return self.video.device

    @property
    def is_playing(self) -> bool:
        """Return whether both video and audio capture are active."""

        return self.video.is_playing and self.audio.is_started

    def play(self) -> None:
        """Start video and audio capture."""

        self.video.play()
        self.audio.start()

    def pause(self) -> None:
        """Pause video and audio capture."""

        self.video.pause()
        self.audio.stop()

    def stop(self) -> None:
        """Stop video and audio capture."""

        self.pause()

    def read(self) -> Image | None:
        """Read a video frame from the combined capture.

        Returns:
            A copy of the newest frame as an ``Image``, or ``None`` if no frame is available.
        """

        return self.video.read()

    def current_frame(self) -> Image | None:
        """Return the most recently read video frame, if one exists."""

        return self.video.current_frame()

    def read_audio(self, count: int | None = None) -> AudioBuffer:
        """Read audio samples from the microphone input.

        Args:
            count: Optional maximum number of samples to read.

        Returns:
            Audio samples from the underlying ``AudioInput``.
        """

        return self.audio.read(count)

    def push_audio_samples(self, samples: list[float] | tuple[float, ...]) -> None:
        """Append synthetic audio samples for tests or headless sketches.

        Args:
            samples: Sample amplitudes to add to the audio input buffer.
        """

        self.audio.push_samples(samples)

    def close(self) -> None:
        """Close the video capture and stop the audio input."""

        self.video.close()
        self.audio.stop()


def create_video(path: str | Path) -> Video:
    """Open a video file for frame-by-frame reading.

    Args:
        path: File path to an existing video.

    Returns:
        A Video stream ready to play, seek, and read frames.
    """
    video_path = Path(path).expanduser()
    if not video_path.exists():
        raise ArgumentValidationError(f"Video file does not exist: {video_path!s}.")
    cv2 = _load_cv2_module()
    capture = cv2.VideoCapture(str(video_path))
    if not _capture_is_open(capture):
        _release_capture(capture)
        raise BackendCapabilityError(f"Could not open video file: {video_path!s}.")
    return Video(capture, path=video_path, cv2_module=cv2)


async def create_video_async(path: str | Path) -> Video:
    """Open a video file using the async asset-loading API.

    Args:
        path: File path to an existing video.

    Returns:
        A Video stream ready to play, seek, and read frames.
    """
    return create_video(path)


def create_capture(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Open a camera, microphone, or combined capture stream.

    Args:
        kind: Capture type: "video"/"camera", "audio"/"microphone", or "av".
        device: Camera device index or name.
        width: Optional requested camera frame width.
        height: Optional requested camera frame height.

    Returns:
        A Capture, AudioInput, or AudioVideoCapture for the requested input.
    """
    normalized_kind = kind.lower()
    if normalized_kind in _AUDIO_KINDS:
        audio = create_audio_in()
        audio.start()
        return audio
    if normalized_kind in _AUDIO_VIDEO_KINDS:
        video = create_capture("video", device=device, width=width, height=height)
        audio = create_audio_in()
        audio.start()
        return AudioVideoCapture(cast(Capture, video), audio)
    if normalized_kind not in _VIDEO_KINDS:
        raise ArgumentValidationError(
            "create_capture() currently supports only kind='video' or kind='camera'."
        )

    cv2 = _load_cv2_module()
    capture = cv2.VideoCapture(device)
    if not _capture_is_open(capture):
        _release_capture(capture)
        raise BackendCapabilityError(
            "Could not open the requested camera device. This can happen in headless "
            "environments, when no camera is available, or when the OS denies access."
        )
    _set_capture_dimensions(capture, cv2, width=width, height=height)
    return Capture(capture, device=device, cv2_module=cv2)


async def create_capture_async(
    kind: str = "video",
    *,
    device: int | str = 0,
    width: int | None = None,
    height: int | None = None,
) -> Capture | AudioInput | AudioVideoCapture:
    """Open a capture stream using the async asset-loading API.

    Args:
        kind: Capture type: "video"/"camera", "audio"/"microphone", or "av".
        device: Camera device index or name.
        width: Optional requested camera frame width.
        height: Optional requested camera frame height.

    Returns:
        A Capture, AudioInput, or AudioVideoCapture for the requested input.
    """
    return create_capture(kind, device=device, width=width, height=height)


__all__ = [
    "Video",
    "Capture",
    "AudioVideoCapture",
    "create_video",
    "create_video_async",
    "create_capture",
    "create_capture_async",
]
