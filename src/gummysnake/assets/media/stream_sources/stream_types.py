"""Backend-neutral video playback and camera capture helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from gummysnake.assets.image import Image
from gummysnake.assets.media.cv2 import release_capture as _release_capture
from gummysnake.assets.media.frame import frame_to_image as _frame_to_image
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError

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
        """Current stream width in pixels."""

        return int(self._get_prop("CAP_PROP_FRAME_WIDTH") or 0)

    @property
    def height(self) -> int:
        """Current stream height in pixels."""

        return int(self._get_prop("CAP_PROP_FRAME_HEIGHT") or 0)

    @property
    def is_playing(self) -> bool:
        """Return whether this stream is actively advancing frames."""

        return self._playing

    def play(self) -> None:
        """Start or resume frame advancement."""

        self._ensure_open()
        self._playing = True

    def pause(self) -> None:
        """Pause frame advancement without closing the stream."""

        self._ensure_open()
        self._playing = False

    def current_frame(self) -> Image | None:
        """Return a copy of the most recently read frame, if available."""

        if self._last_frame is None:
            return None
        return self._last_frame.copy()

    def close(self) -> None:
        """Release the underlying capture object and stop playback."""

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
        """Path to the opened video file."""

        return self._path

    @property
    def fps(self) -> float | None:
        """Video frames per second, if the backend reports it."""

        fps = float(self._get_prop("CAP_PROP_FPS") or 0.0)
        return fps if fps > 0 else None

    @property
    def frame_count(self) -> int | None:
        """Total number of frames, if the backend reports it."""

        count = int(self._get_prop("CAP_PROP_FRAME_COUNT") or 0)
        return count if count > 0 else None

    @property
    def duration(self) -> float | None:
        """Video duration in seconds, if frame count and FPS are known."""

        fps = self.fps
        frame_count = self.frame_count
        if fps is None or frame_count is None:
            return None
        return frame_count / fps

    def stop(self) -> None:
        """Pause playback and seek back to the beginning."""

        self._ensure_open()
        self._playing = False
        self.seek(0.0)

    def looping(self, value: bool | None = None) -> bool:
        """Get or set whether the video restarts at the end.

        Args:
            value: Optional new looping flag.

        Returns:
            The current looping flag.
        """

        if value is not None:
            self._loop = bool(value)
        return self._loop

    def loop(self) -> None:
        """Enable looping and start playback."""

        self.looping(True)
        self.play()

    def no_loop(self) -> None:
        """Disable looping for future playback."""

        self.looping(False)

    def speed(self, value: float | None = None) -> float:
        """Get or set the video playback speed multiplier.

        Args:
            value: Optional positive speed multiplier, where ``1.0`` is normal speed.

        Returns:
            The current speed multiplier.
        """

        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("Video.speed() must be positive.")
            self._speed = float(value)
        return self._speed

    def time(self) -> float | None:
        """Current video time in seconds, if the backend reports it."""

        milliseconds = self._get_prop("CAP_PROP_POS_MSEC")
        if milliseconds is None:
            return None
        return float(milliseconds) / 1000.0

    def seek(self, seconds: float) -> None:
        """Move the video read position.

        Args:
            seconds: Non-negative target time in seconds.
        """

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
        """Read the current or next video frame.

        Returns:
            A copy of the current frame as an ``Image``, or ``None`` at end of stream.
        """

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


__all__ = [
    "Video",
    "_AUDIO_KINDS",
    "_AUDIO_VIDEO_KINDS",
    "_FrameStreamBase",
    "_VIDEO_KINDS",
]
