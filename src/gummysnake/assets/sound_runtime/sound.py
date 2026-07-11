"""Public sound asset model, independent of native player implementation details."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from gummysnake.assets.sound_runtime.canvas_sound import CanvasSound
from gummysnake.assets.sound_runtime.native_playback import NativeAudioPlayer, PlaybackResource
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


class Sound:
    """Loaded sound asset with simple playback controls.

    Loading keeps bytes and metadata in a Rust-owned ``CanvasSound``. Playback
    uses an explicitly supplied player factory, which defaults to the native
    platform-player adapter; no audio device is required merely to inspect an
    asset.
    """

    def __init__(
        self,
        source: object,
        *,
        path: Path,
        rust_sound: CanvasSound | None = None,
        player_factory: Any | None = None,
    ) -> None:
        """Create a playable sound wrapper around an asset or generated source."""

        self._source = source
        self._rust_sound = rust_sound
        self._path = path
        self._player_factory = player_factory or NativeAudioPlayer
        self._player: Any | None = None
        self._playback_resource: PlaybackResource | None = None
        self._volume = 1.0
        self._rate = 1.0
        self._pan = 0.0
        self._loop = False
        self._position = 0.0
        self._is_playing = False
        self._ended_callbacks: list[Callable[[Sound], object]] = []

    @property
    def path(self) -> Path:
        """Path used to create this sound."""

        return self._path

    @property
    def duration(self) -> float | None:
        """Sound duration in seconds, if known."""

        if self._rust_sound is not None:
            return self._rust_sound.duration
        duration = getattr(self._source, "duration", None)
        return None if duration is None else float(duration)

    @property
    def byte_len(self) -> int | None:
        """Number of encoded audio bytes, if bytes are available."""

        if self._rust_sound is None:
            return None
        return self._rust_sound.byte_len

    def to_bytes(self) -> bytes:
        """Return the encoded sound bytes."""

        if self._rust_sound is not None:
            return self._rust_sound.to_bytes()
        to_bytes = getattr(self._source, "to_bytes", None)
        if callable(to_bytes):
            return bytes(cast(Callable[[], bytes | bytearray | memoryview], to_bytes)())
        raise BackendCapabilityError("Sound bytes are unavailable for this sound source.")

    def play(self) -> None:
        """Start playback from the current sound source."""

        self.stop()
        player = self._create_player()
        self._queue_source(player)
        self._apply_controls(player)
        try:
            play = player.play
            play()
        except BackendCapabilityError:
            self._dispose_player(player)
            raise
        except Exception as exc:  # pragma: no cover - backend-specific failure path
            self._dispose_player(player)
            raise BackendCapabilityError(
                f"Audio playback is unavailable on this system. Could not play {self._path!s}."
            ) from exc
        self._player = player
        self._is_playing = True

    def loop(self) -> None:
        """Enable looping and start playback."""

        self.looping(True)
        self.play()

    def no_loop(self) -> None:
        """Disable looping for future playback."""

        self.looping(False)

    def looping(self, value: bool | None = None) -> bool:
        """Get or set whether the sound repeats when it reaches the end."""

        if value is not None:
            self._loop = bool(value)
            if self._player is not None and hasattr(self._player, "loop"):
                self._player.loop = self._loop
        return self._loop

    def pause(self) -> None:
        """Pause playback if a player is active."""

        if self._player is None:
            return
        pause = getattr(self._player, "pause", None)
        if callable(pause):
            pause()
        self._is_playing = False

    def stop(self) -> None:
        """Stop playback, seek back to the start, and release the player."""

        player = self._player
        if player is None:
            return
        pause = getattr(player, "pause", None)
        if callable(pause):
            pause()
        seek = getattr(player, "seek", None)
        if callable(seek):
            seek(0.0)
        self._position = 0.0
        self._is_playing = False
        self._dispose_player(player)
        self._player = None

    def close(self) -> None:
        """Stop playback and release any temporary playback resources."""

        self.stop()

    def volume(self, value: float | None = None) -> float:
        """Get or set a non-negative playback volume."""

        if value is not None:
            if value < 0:
                raise ArgumentValidationError("Sound.volume() cannot be negative.")
            self._volume = float(value)
            if self._player is not None:
                self._player.volume = self._volume
        return self._volume

    def rate(self, value: float | None = None) -> float:
        """Get or set a positive playback-speed multiplier."""

        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("Sound.rate() must be positive.")
            self._rate = float(value)
            if self._player is not None:
                self._player.pitch = self._rate
        return self._rate

    def pan(self, value: float | None = None) -> float:
        """Get or set stereo pan from ``-1.0`` (left) to ``1.0`` (right)."""

        if value is not None:
            if not -1.0 <= value <= 1.0:
                raise ArgumentValidationError("Sound.pan() must be between -1 and 1.")
            self._pan = float(value)
            if self._player is not None:
                self._player.position = self._pan, 0.0, 0.0
        return self._pan

    def seek(self, seconds: float) -> None:
        """Move playback to a non-negative time position in seconds."""

        if seconds < 0:
            raise ArgumentValidationError("Sound.seek() cannot be negative.")
        self._position = float(seconds)
        if self._player is not None:
            seek = getattr(self._player, "seek", None)
            if callable(seek):
                seek(self._position)

    def time(self) -> float:
        """Return the current playback position in seconds."""

        if self._player is not None:
            time = getattr(self._player, "time", None)
            if callable(time):
                return float(cast(float, time()))
            get_time = getattr(self._player, "get_time", None)
            if callable(get_time):
                return float(cast(float, get_time()))
        return self._position

    def is_playing(self) -> bool:
        """Return whether this sound is currently playing."""

        return self._is_playing

    def is_paused(self) -> bool:
        """Return whether this sound has an active player that is paused."""

        return self._player is not None and not self._is_playing

    def on_ended(self, callback: Callable[[Sound], object]) -> Callable[[Sound], object]:
        """Register and return a callback invoked when playback ends."""

        if not callable(callback):
            raise ArgumentValidationError("Sound.on_ended() requires a callable.")
        self._ended_callbacks.append(callback)
        return callback

    def _notify_ended(self) -> None:
        self._is_playing = False
        for callback in tuple(self._ended_callbacks):
            callback(self)

    def _create_player(self) -> Any:
        resource = PlaybackResource(
            self._path, self._source, rust_backed=self._rust_sound is not None
        )
        self._playback_resource = resource
        try:
            return self._player_factory(resource.path)
        except Exception as exc:  # pragma: no cover - backend-specific failure path
            self._release_playback_resource()
            raise BackendCapabilityError(
                "Audio playback is unavailable on this system. Could not create a sound player."
            ) from exc

    def _queue_source(self, player: Any) -> None:
        queue = getattr(player, "queue", None)
        if callable(queue):
            queue(self._source)

    def _apply_controls(self, player: Any) -> None:
        if hasattr(player, "volume"):
            player.volume = self._volume
        if hasattr(player, "pitch"):
            player.pitch = self._rate
        if hasattr(player, "position"):
            player.position = self._pan, 0.0, 0.0
        if hasattr(player, "loop"):
            player.loop = self._loop

    def _dispose_player(self, player: Any) -> None:
        delete = getattr(player, "delete", None)
        if callable(delete):
            delete()
        self._release_playback_resource()

    def _release_playback_resource(self) -> None:
        resource = self._playback_resource
        self._playback_resource = None
        if resource is not None:
            resource.close()


__all__ = ["Sound"]
