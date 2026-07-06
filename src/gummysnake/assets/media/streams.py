"""Backend-neutral video playback and camera capture helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from gummysnake.assets.audio import AudioInput, create_audio_in
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
from gummysnake.exceptions import (
    ArgumentValidationError,
    BackendCapabilityError,
)

_VIDEO_KINDS = {"video", "camera"}
_AUDIO_KINDS = {"audio", "microphone", "mic"}
_AUDIO_VIDEO_KINDS = {"av", "audio_video", "video+audio", "audio+video"}


class _FrameStreamBase:
    """Shared lifecycle and cached-frame behavior for OpenCV-backed streams."""

    def __init__(
        self,
        capture: Any,
        *,
        cv2_module: Any,
        playing: bool,
        closed_error_message: str,
    ) -> None:
        self._capture = capture
        self._cv2 = cv2_module
        self._playing = playing
        self._closed = False
        self._closed_error_message = closed_error_message
        self._last_frame: Image | None = None

    @property
    def width(self) -> int:
        return int(self._get_prop("CAP_PROP_FRAME_WIDTH") or 0)

    @property
    def height(self) -> int:
        return int(self._get_prop("CAP_PROP_FRAME_HEIGHT") or 0)

    @property
    def is_playing(self) -> bool:
        return self._playing

    def play(self) -> None:
        self._ensure_open()
        self._playing = True

    def pause(self) -> None:
        self._ensure_open()
        self._playing = False

    def current_frame(self) -> Image | None:
        if self._last_frame is None:
            return None
        return self._last_frame.copy()

    def close(self) -> None:
        if self._closed:
            return
        _release_capture(self._capture)
        self._closed = True
        self._playing = False

    def _get_prop(self, name: str) -> float | int | None:
        get_prop = getattr(self._capture, "get", None)
        prop = getattr(self._cv2, name, None)
        if not callable(get_prop) or prop is None:
            return None
        value = get_prop(prop)
        if value is None:
            return None
        if isinstance(value, int | float):
            return value
        return None

    def _ensure_open(self) -> None:
        if self._closed:
            raise BackendCapabilityError(self._closed_error_message)


class Video(_FrameStreamBase):
    """File-backed video stream with explicit frame-reading semantics."""

    def __init__(self, capture: Any, *, path: Path, cv2_module: Any) -> None:
        """Create a file-backed video stream from an OpenCV capture object."""
        super().__init__(
            capture,
            cv2_module=cv2_module,
            playing=False,
            closed_error_message="This video has already been closed.",
        )
        self._path = path
        self._loop = False
        self._speed = 1.0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def fps(self) -> float | None:
        fps = float(self._get_prop("CAP_PROP_FPS") or 0.0)
        return fps if fps > 0 else None

    @property
    def frame_count(self) -> int | None:
        count = int(self._get_prop("CAP_PROP_FRAME_COUNT") or 0)
        return count if count > 0 else None

    @property
    def duration(self) -> float | None:
        fps = self.fps
        frame_count = self.frame_count
        if fps is None or frame_count is None:
            return None
        return frame_count / fps

    def stop(self) -> None:
        self._ensure_open()
        self._playing = False
        self.seek(0.0)

    def looping(self, value: bool | None = None) -> bool:
        if value is not None:
            self._loop = bool(value)
        return self._loop

    def loop(self) -> None:
        self.looping(True)
        self.play()

    def no_loop(self) -> None:
        self.looping(False)

    def speed(self, value: float | None = None) -> float:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("Video.speed() must be positive.")
            self._speed = float(value)
        return self._speed

    def time(self) -> float | None:
        milliseconds = self._get_prop("CAP_PROP_POS_MSEC")
        if milliseconds is None:
            return None
        return float(milliseconds) / 1000.0

    def seek(self, seconds: float) -> None:
        self._ensure_open()
        if seconds < 0:
            raise ArgumentValidationError("Video.seek() cannot be negative.")
        set_prop = getattr(self._capture, "set", None)
        position_prop = getattr(self._cv2, "CAP_PROP_POS_MSEC", None)
        if not callable(set_prop) or position_prop is None:
            raise BackendCapabilityError("Video seeking is unavailable on this system.")
        set_prop(position_prop, float(seconds) * 1000.0)
        self._last_frame = None

    def read(self) -> Image | None:
        self._ensure_open()
        if not self._playing and self._last_frame is not None:
            return self._last_frame.copy()
        frame = self._read_next_frame()
        if frame is None:
            return None
        self._last_frame = frame
        return frame.copy()

    def _read_next_frame(self) -> Image | None:
        read = getattr(self._capture, "read", None)
        if not callable(read):
            raise BackendCapabilityError("Video frame reading is unavailable on this system.")
        ok, frame = cast(tuple[bool, Any], read())
        if not ok or frame is None:
            if self._loop:
                self.seek(0.0)
                ok, frame = cast(tuple[bool, Any], read())
            if not ok or frame is None:
                self._playing = False
                return None
        return _frame_to_image(frame)


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
        return self._device

    def read(self) -> Image | None:
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
        return self.video.width

    @property
    def height(self) -> int:
        return self.video.height

    @property
    def device(self) -> int | str:
        return self.video.device

    @property
    def is_playing(self) -> bool:
        return self.video.is_playing and self.audio.is_started

    def play(self) -> None:
        self.video.play()
        self.audio.start()

    def pause(self) -> None:
        self.video.pause()
        self.audio.stop()

    def stop(self) -> None:
        self.pause()

    def read(self) -> Image | None:
        return self.video.read()

    def current_frame(self) -> Image | None:
        return self.video.current_frame()

    def read_audio(self, count: int | None = None):
        return self.audio.read(count)

    def push_audio_samples(self, samples: list[float] | tuple[float, ...]) -> None:
        self.audio.push_samples(samples)

    def close(self) -> None:
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
