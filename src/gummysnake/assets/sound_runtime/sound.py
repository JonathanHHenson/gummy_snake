"""Public Sound facade over Rust-owned audio assets and native SDL voices."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

from gummysnake.assets.sound_runtime.canvas_sound import CanvasSound
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


class _Playback(Protocol):
    error: str | None

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...

    def looping(self, value: bool | None = None) -> bool: ...

    def set_volume(self, value: float) -> None: ...

    def set_rate(self, value: float) -> None: ...

    def set_pan(self, value: float) -> None: ...

    def seek(self, seconds: float) -> None: ...

    def time(self) -> float: ...

    def is_playing(self) -> bool: ...

    def is_paused(self) -> bool: ...

    def take_ended(self) -> bool: ...

    def diagnostics(self) -> dict[str, object]: ...


class Sound:
    """Rust-owned sound asset with independent native playback controls.

    Encoded bytes and decoded PCM stay in one ``CanvasSound`` asset. Every
    ``play()`` creates an independent voice on the process-local SDL3 mixer;
    playback never creates a temporary file or launches a platform process.
    """

    def __init__(
        self,
        source: object,
        *,
        path: Path,
        rust_sound: CanvasSound | None = None,
    ) -> None:
        """Create a sound facade backed by the native SDL audio route."""

        self._path = path
        self._rust_sound = rust_sound or self._asset_from_source(source, path)
        self._source = self._rust_sound
        self._playback: _Playback | None = None
        self._volume = 1.0
        self._rate = 1.0
        self._pan = 0.0
        self._loop = False
        self._position = 0.0
        self._ended_callbacks: list[Callable[[Sound], object]] = []

    @staticmethod
    def _asset_from_source(source: object, path: Path) -> CanvasSound:
        if isinstance(source, CanvasSound):
            return source
        to_bytes = getattr(source, "to_bytes", None)
        if not callable(to_bytes):
            raise BackendCapabilityError(
                "Sound requires a Rust CanvasSound asset or mono/stereo 16-bit PCM WAV bytes."
            )
        payload = bytes(cast(Callable[[], bytes | bytearray | memoryview], to_bytes)())
        return CanvasSound.from_bytes(path, payload)

    @property
    def path(self) -> Path:
        """Path or display name used to create this sound."""

        return self._path

    @property
    def duration(self) -> float:
        """Sound duration in seconds."""

        return self._rust_sound.duration

    @property
    def byte_len(self) -> int:
        """Number of encoded audio bytes retained by Rust."""

        return self._rust_sound.byte_len

    def to_bytes(self) -> bytes:
        """Return a copy of the encoded sound bytes."""

        return self._rust_sound.to_bytes()

    def play(self) -> None:
        """Start a new independent voice with the current controls."""

        previous = self._playback
        self._playback = None
        if previous is not None:
            try:
                previous.stop()
            finally:
                previous.close()
        try:
            self._playback = self._rust_sound.play(
                volume=self._volume,
                rate=self._rate,
                pan=self._pan,
                looping=self._loop,
                position=self._position,
            )
        except BackendCapabilityError:
            raise
        except Exception as exc:
            raise BackendCapabilityError(
                "Native audio playback is unavailable. The installed Gummy Snake canvas runtime "
                "must include SDL3 audio support and an accessible playback device."
            ) from exc

    def loop(self) -> None:
        """Enable looping and start playback."""

        self._loop = True
        self.play()

    def no_loop(self) -> None:
        """Disable looping for the current and future voice."""

        self.looping(False)

    def looping(self, value: bool | None = None) -> bool:
        """Get or set whether playback repeats at the asset boundary."""

        if value is not None:
            self._loop = bool(value)
            if self._playback is not None:
                self._call_native(self._playback.looping, self._loop)
        return self._loop

    def pause(self) -> None:
        """Pause the active voice without changing its sample position."""

        if self._playback is not None:
            self._call_native(self._playback.pause)

    def stop(self) -> None:
        """Stop and release the active voice, then reset to the start."""

        playback = self._playback
        self._playback = None
        self._position = 0.0
        if playback is None:
            return
        try:
            playback.stop()
        finally:
            playback.close()

    def close(self) -> None:
        """Stop playback and release the native voice handle."""

        self.stop()

    def volume(self, value: float | None = None) -> float:
        """Get or set a finite non-negative playback volume."""

        if value is not None:
            value = float(value)
            if not value >= 0.0 or value == float("inf"):
                raise ArgumentValidationError(
                    "Sound.volume() requires a finite non-negative value."
                )
            self._volume = value
            if self._playback is not None:
                self._call_native(self._playback.set_volume, value)
        return self._volume

    def rate(self, value: float | None = None) -> float:
        """Get or set a finite positive playback-speed multiplier."""

        if value is not None:
            value = float(value)
            if not value > 0.0 or value == float("inf"):
                raise ArgumentValidationError("Sound.rate() requires a finite positive value.")
            self._rate = value
            if self._playback is not None:
                self._call_native(self._playback.set_rate, value)
        return self._rate

    def pan(self, value: float | None = None) -> float:
        """Get or set stereo pan from ``-1.0`` to ``1.0``."""

        if value is not None:
            value = float(value)
            if not -1.0 <= value <= 1.0:
                raise ArgumentValidationError("Sound.pan() must be between -1 and 1.")
            self._pan = value
            if self._playback is not None:
                self._call_native(self._playback.set_pan, value)
        return self._pan

    def seek(self, seconds: float) -> None:
        """Move playback to a valid non-negative source time."""

        seconds = float(seconds)
        if not 0.0 <= seconds <= self.duration:
            raise ArgumentValidationError(
                f"Sound.seek() must be between 0 and the sound duration ({self.duration:g})."
            )
        self._position = seconds
        if self._playback is not None:
            self._call_native(self._playback.seek, seconds)

    def time(self) -> float:
        """Return the native voice position in seconds."""

        self._poll_ended()
        if self._playback is not None:
            self._position = float(self._call_native(self._playback.time))
        return self._position

    def is_playing(self) -> bool:
        """Return whether the native voice is advancing."""

        self._poll_ended()
        return bool(self._playback is not None and self._call_native(self._playback.is_playing))

    def is_paused(self) -> bool:
        """Return whether the native voice exists and is paused."""

        self._poll_ended()
        return bool(self._playback is not None and self._call_native(self._playback.is_paused))

    def on_ended(self, callback: Callable[[Sound], object]) -> Callable[[Sound], object]:
        """Register an owner-thread callback for natural non-looping completion.

        Native audio threads only enqueue completion state. Callbacks are drained
        on the Python owner thread when playback state is observed through
        ``time()``, ``is_playing()``, ``is_paused()``, or ``playback_diagnostics()``.
        """

        if not callable(callback):
            raise ArgumentValidationError("Sound.on_ended() requires a callable.")
        self._ended_callbacks.append(callback)
        return callback

    def playback_diagnostics(self) -> dict[str, object]:
        """Return block/session state for this voice, or an inactive snapshot."""

        self._poll_ended()
        if self._playback is None:
            return {
                "duration_seconds": self.duration,
                "position_seconds": self._position,
                "playing": False,
                "paused": False,
                "looping": self._loop,
                "blocks": 0,
                "rendered_frames": 0,
                "ended_generation": 0,
                "error": None,
            }
        return dict(self._call_native(self._playback.diagnostics))

    def _poll_ended(self) -> None:
        playback = self._playback
        if playback is None or not self._call_native(playback.take_ended):
            return
        self._position = self.duration
        for callback in tuple(self._ended_callbacks):
            callback(self)

    @staticmethod
    def _call_native(callback: Callable[..., Any], *args: object) -> Any:
        try:
            return callback(*args)
        except Exception as exc:
            raise BackendCapabilityError(f"Native audio playback failed: {exc}") from exc


__all__ = ["Sound"]
