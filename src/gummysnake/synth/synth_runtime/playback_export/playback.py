from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, cast

from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError
from gummysnake.synth.synth_runtime.physical.physical_plan import PhysicalPlan
from gummysnake.synth.synth_runtime.physical.rendering import _require_synth_runtime
from gummysnake.synth.synth_runtime.values.foundation import _SAMPLE_RATE


@dataclass(slots=True)
class _RenderedTrackCacheEntry:
    payload: bytes | None
    duration_seconds: float
    path: Path | None = None


class TrackPlayback:
    """Native realtime playback handle returned by ``Track.play()``.

    Python compiles one bounded physical program before startup. The Rust-owned
    session then renders finite or rolling repetitions into the process-local SDL
    mixer without Python horizon expansion, event WAVs, temporary files, or
    platform-player subprocesses.
    """

    def __init__(
        self,
        plan: PhysicalPlan,
        *,
        sample_rate: int = _SAMPLE_RATE,
        player_factory: Any | None = None,
        look_ahead: float = 0.05,
        name: str = "gummysnake-track",
        rolling: bool = False,
        rendered_cache: _RenderedTrackCacheEntry | None = None,
        **_legacy_options: object,
    ) -> None:
        if player_factory is not None:
            raise ArgumentValidationError(
                "Custom track player factories are no longer supported; realtime playback "
                "requires the native Gummy Snake SDL3 audio manager."
            )
        self._plan = plan
        self._sample_rate = int(sample_rate)
        self._name = name
        self._rolling = bool(rolling)
        self._look_ahead = max(0.0, float(look_ahead))
        self._rendered_cache = rendered_cache
        self._rust_playback: Any | None = None
        self._error: Exception | None = None
        self._closed = False
        self._last_diagnostics: dict[str, object] | None = None

    def start(self) -> TrackPlayback:
        """Compile the native program and synchronously open shared audio."""

        try:
            runtime = _require_synth_runtime()
            program = runtime.CanvasSynthProgram.from_serialized(
                self._plan.to_bytes(), self._sample_rate
            )
            self._rust_playback = runtime.synth_play_compiled_program(program, self._rolling)
        except Exception as exc:
            self._error = BackendCapabilityError(
                "Native synth playback is unavailable. The installed Gummy Snake canvas "
                "runtime must include SDL3 audio support and an accessible playback device."
            )
            raise self._error from exc
        return self

    def pause(self) -> None:
        """Pause the native synth session at a mixer frame boundary."""

        playback = self._rust_playback
        if playback is not None:
            playback.pause()

    def resume(self) -> None:
        """Resume a paused native synth session."""

        playback = self._rust_playback
        if playback is not None:
            playback.play()

    def stop(self) -> None:
        """Stop and close the native synth session."""

        playback = self._rust_playback
        self._rust_playback = None
        self._closed = True
        if playback is None:
            return
        try:
            playback.stop()
        finally:
            playback.close()

    def join(self, timeout: float | None = None) -> bool:
        """Wait until playback ends while keeping Python signals responsive."""

        playback = self._rust_playback
        if playback is None:
            return True
        try:
            deadline = None if timeout is None else monotonic() + max(0.0, float(timeout))
            while True:
                wait_seconds = 0.05
                if deadline is not None:
                    remaining = deadline - monotonic()
                    if remaining <= 0.0:
                        return False
                    wait_seconds = min(wait_seconds, remaining)
                if playback.wait_until_stop(wait_seconds):
                    finished = True
                    break
            self._capture_native_error()
            if finished and not self._rolling:
                diagnostics = getattr(playback, "diagnostics", None)
                if callable(diagnostics):
                    self._last_diagnostics = dict(cast(dict[str, object], diagnostics()))
                playback.close()
                self._rust_playback = None
                self._closed = True
            return finished
        except KeyboardInterrupt:
            self.stop()
            raise
        except Exception as exc:
            self._error = RuntimeError(f"Rust synth playback failed: {exc}")
            return True

    def wait_until_stop(self, timeout: float | None = None) -> bool:
        """Readable alias for :meth:`join`."""

        return self.join(timeout)

    def is_playing(self) -> bool:
        """Return whether the native session is currently advancing."""

        playback = self._rust_playback
        if playback is None:
            return False
        try:
            playing = bool(playback.is_playing())
            self._capture_native_error()
            return playing
        except Exception as exc:
            self._error = RuntimeError(f"Rust synth playback failed: {exc}")
            return False

    @property
    def error(self) -> Exception | None:
        """Playback error reported by the native session, if any."""

        self._capture_native_error()
        return self._error

    def playback_diagnostics(self) -> dict[str, object]:
        """Return native block/session diagnostics for this playback."""

        playback = self._rust_playback
        if playback is None:
            if self._last_diagnostics is not None:
                return dict(self._last_diagnostics)
            return {
                "duration_seconds": self._plan.duration_seconds,
                "position_seconds": 0.0,
                "playing": False,
                "paused": False,
                "looping": self._rolling,
                "blocks": 0,
                "rendered_frames": 0,
                "ended_generation": 0,
                "error": None if self._error is None else str(self._error),
            }
        diagnostics = getattr(playback, "diagnostics", None)
        if not callable(diagnostics):
            return {"playing": self.is_playing(), "looping": self._rolling}
        return dict(cast(dict[str, object], diagnostics()))

    def _capture_native_error(self) -> None:
        playback = self._rust_playback
        if playback is None:
            return
        error = getattr(playback, "error", None)
        if callable(error):
            error = error()
        if error:
            self._error = RuntimeError(f"Rust synth playback failed: {error}")

    def __del__(self) -> None:
        if getattr(self, "_rust_playback", None) is not None:
            with contextlib.suppress(Exception):
                self.stop()


__all__ = ["TrackPlayback"]
