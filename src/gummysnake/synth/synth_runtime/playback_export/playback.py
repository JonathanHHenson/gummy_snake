from __future__ import annotations

import contextlib
import contextvars
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gummysnake.api.current import _ACTIVE_CONTEXT
from gummysnake.assets._audio_codec import MemorySoundSource
from gummysnake.assets.sound import Sound
from gummysnake.synth.synth_runtime.composition.logical_nodes import (
    ScheduledControl,
    ScheduledEvent,
    TrackPlan,
)
from gummysnake.synth.synth_runtime.physical.physical_plan import PhysicalPlan
from gummysnake.synth.synth_runtime.physical.rendering import (
    _expand_physical_plan,
    _render_physical_plan,
    _require_synth_runtime,
)
from gummysnake.synth.synth_runtime.physical.serialization import (
    _control_lookup,
    _render_event_sound,
)
from gummysnake.synth.synth_runtime.playback_export.samples_and_export import _wav_duration_seconds
from gummysnake.synth.synth_runtime.values.foundation import _SAMPLE_RATE, SynthPlanError


@dataclass(slots=True)
class _RenderedTrackCacheEntry:
    payload: bytes
    duration_seconds: float
    path: Path | None = None


@dataclass(slots=True)
class _RenderedFileSoundSource:
    duration: float


def _event_time_groups(
    events: Sequence[ScheduledEvent], *, tolerance: float = 1e-9
) -> tuple[tuple[ScheduledEvent, ...], ...]:
    """Group adjacent events that should start at the same realtime instant."""

    groups: list[list[ScheduledEvent]] = []
    for event in events:
        if not groups or abs(event.time_seconds - groups[-1][0].time_seconds) > tolerance:
            groups.append([event])
        else:
            groups[-1].append(event)
    return tuple(tuple(group) for group in groups)


class TrackPlayback:
    """Realtime playback handle returned by track playback methods."""

    def __init__(
        self,
        plan: PhysicalPlan | None,
        *,
        logical_plan: TrackPlan | None = None,
        sample_rate: int = _SAMPLE_RATE,
        player_factory: Any | None = None,
        look_ahead: float = 0.05,
        name: str = "gummysnake-track",
        rolling: bool = False,
        window_seconds: float = 4.0,
        rendered_cache: _RenderedTrackCacheEntry | None = None,
    ) -> None:
        self._plan = plan
        self._logical_plan = logical_plan
        self._rolling = bool(rolling)
        self._window_seconds = max(0.25, float(window_seconds))
        self._rendered_cache = rendered_cache
        self._sample_rate = int(sample_rate)
        self._player_factory = player_factory
        self._look_ahead = max(0.0, float(look_ahead))
        self._name = name
        self._stop_event = threading.Event()
        self._done_event = threading.Event()
        self._error: Exception | None = None
        self._active_sounds: list[tuple[Sound, float]] = []
        self._rust_playback: Any | None = None
        worker_context = contextvars.Context()
        worker_context.run(_ACTIVE_CONTEXT.set, None)
        self._thread = threading.Thread(
            target=worker_context.run,
            args=(self._run,),
            name=f"gummysnake-synth-{name}",
            daemon=False,
        )

    def start(self) -> TrackPlayback:
        """Start scheduling playback on a background thread."""

        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop scheduling and close any active event sounds."""

        self._stop_event.set()
        self._close_rust_playback()
        self._close_active_sounds()

    def join(self, timeout: float | None = None) -> bool:
        """Wait for playback to finish.

        Returns:
            ``True`` when playback finished before the timeout.
        """

        self._thread.join(timeout)
        return not self._thread.is_alive()

    def wait_until_stop(self, timeout: float | None = None) -> bool:
        """Block until playback stops or an optional timeout expires.

        This is a readability-focused alias for :meth:`join` intended for
        scripts and examples that start a track and then keep the process alive
        until the bounded playback finishes.
        """

        return self.join(timeout)

    def is_playing(self) -> bool:
        """Return whether the realtime scheduler is still active."""

        return not self._done_event.is_set()

    @property
    def error(self) -> Exception | None:
        """Playback error captured from the scheduler thread, if any."""

        return self._error

    def _run(self) -> None:
        try:
            if self._rolling:
                self._run_rolling()
            else:
                self._run_finite()
        except Exception as exc:  # pragma: no cover - backend/audio-device dependent
            self._error = exc
        finally:
            self._close_rust_playback()
            self._close_active_sounds()
            self._done_event.set()

    def _run_finite(self) -> None:
        if self._plan is None:
            raise SynthPlanError("Finite realtime playback requires a physical plan.")
        cached = self._rendered_cache
        if self._player_factory is None:
            self._run_finite_rust_playback(cached)
            return
        if cached is not None:
            payload = cached.payload
            seconds = cached.duration_seconds
        else:
            payload = _render_physical_plan(self._plan, sample_rate=self._sample_rate)
            seconds = _wav_duration_seconds(payload)
        if self._stop_event.is_set():
            return
        if seconds <= 0:
            return
        if cached is not None and cached.path is not None and cached.path.exists():
            sound = Sound(
                _RenderedFileSoundSource(seconds),
                path=cached.path,
                player_factory=self._player_factory,
            )
        else:
            sound = Sound(
                MemorySoundSource(payload, duration=seconds),
                path=Path(f"{self._name}.wav"),
                player_factory=self._player_factory,
            )
        start_time = time.monotonic()
        target_end_time = start_time + max(0.0, self._plan.duration_seconds)
        sound.play()
        self._active_sounds.append((sound, start_time + seconds + 0.25))
        self._wait_until_finite_end(target_end_time)

    def _run_finite_rust_playback(self, cached: _RenderedTrackCacheEntry | None) -> None:
        if self._plan is None:
            raise SynthPlanError("Finite realtime playback requires a physical plan.")
        _ = cached
        runtime = _require_synth_runtime()
        playback = runtime.synth_play_serialized_plan(self._plan.to_bytes(), int(self._sample_rate))
        self._rust_playback = playback
        if self._stop_event.is_set():
            self._close_rust_playback()
            return
        target_end_time = time.monotonic() + max(0.0, self._plan.duration_seconds)
        self._wait_until_finite_end(target_end_time)

    def _run_rolling(self) -> None:
        if self._logical_plan is None:
            raise SynthPlanError("Rolling realtime playback requires a logical plan.")
        start_time = time.monotonic()
        emitted: set[tuple[object, ...]] = set()
        horizon = 0.0
        while not self._stop_event.is_set():
            elapsed = max(0.0, time.monotonic() - start_time)
            horizon = max(horizon + self._window_seconds, elapsed + self._window_seconds)
            plan = _expand_physical_plan(self._logical_plan, horizon)
            controls_by_instance, fx_controls = _control_lookup(plan)
            events = [
                event
                for event in sorted(plan.events, key=lambda item: item.time_seconds)
                if event.instance not in emitted and event.time_seconds <= horizon
            ]
            if not events:
                self._close_finished_sounds(time.monotonic())
                self._stop_event.wait(0.05)
                continue
            for event_group in _event_time_groups(events):
                if self._stop_event.is_set():
                    break
                for event in event_group:
                    emitted.add(event.instance)
                self._schedule_event_group(
                    start_time, event_group, controls_by_instance, fx_controls
                )
            self._close_finished_sounds(time.monotonic())
        self._wait_for_active_sounds()

    def _schedule_event_group(
        self,
        start_time: float,
        events: Sequence[ScheduledEvent],
        controls_by_instance: Mapping[tuple[object, ...], Sequence[ScheduledControl]],
        fx_controls: Mapping[int, Sequence[ScheduledControl]],
    ) -> None:
        if not events:
            return
        event_time = events[0].time_seconds
        self._sleep_until(start_time + max(0.0, event_time - self._look_ahead))
        if self._stop_event.is_set():
            return
        sounds = self._render_event_group_sounds(events, controls_by_instance, fx_controls)
        if not sounds:
            return
        self._sleep_until(start_time + event_time)
        if self._stop_event.is_set():
            for _event, sound in sounds:
                sound.close()
            return
        self._play_event_sounds(start_time, event_time, sounds)

    def _render_event_group_sounds(
        self,
        events: Sequence[ScheduledEvent],
        controls_by_instance: Mapping[tuple[object, ...], Sequence[ScheduledControl]],
        fx_controls: Mapping[int, Sequence[ScheduledControl]],
    ) -> list[tuple[ScheduledEvent, Sound]]:
        sounds: list[tuple[ScheduledEvent, Sound]] = []
        for event in events:
            if self._stop_event.is_set():
                break
            sound = _render_event_sound(
                event,
                controls_by_instance.get(event.instance, ()),
                fx_controls,
                self._sample_rate,
                self._player_factory,
                self._name,
            )
            if sound is not None:
                sounds.append((event, sound))
        return sounds

    def _play_event_sounds(
        self,
        start_time: float,
        event_time: float,
        sounds: Sequence[tuple[ScheduledEvent, Sound]],
    ) -> None:
        for _event, sound in sounds:
            sound.play()
            end_time = event_time + (sound.duration or 0.0) + 0.25
            self._active_sounds.append((sound, start_time + end_time))
        self._close_finished_sounds(time.monotonic())

    def _wait_for_active_sounds(self) -> None:
        while self._active_sounds and not self._stop_event.is_set():
            self._close_finished_sounds(time.monotonic())
            if self._active_sounds:
                self._stop_event.wait(0.05)

    def _wait_until_finite_end(self, target_time: float) -> None:
        while not self._stop_event.is_set():
            self._raise_if_rust_playback_failed()
            now = time.monotonic()
            self._close_finished_sounds(now)
            remaining = target_time - now
            if remaining <= 0:
                return
            self._stop_event.wait(min(remaining, 0.05))

    def _raise_if_rust_playback_failed(self) -> None:
        playback = self._rust_playback
        if playback is None:
            return
        error_message = getattr(playback, "error", None)
        if callable(error_message):
            error_message = error_message()
        if error_message:
            raise RuntimeError(f"Rust synth playback failed: {error_message}")

    def _sleep_until(self, target_time: float) -> None:
        while not self._stop_event.is_set():
            remaining = target_time - time.monotonic()
            if remaining <= 0:
                return
            self._stop_event.wait(min(remaining, 0.05))

    def _close_finished_sounds(self, now: float) -> None:
        remaining: list[tuple[Sound, float]] = []
        for sound, end_time in self._active_sounds:
            if now >= end_time:
                sound.close()
            else:
                remaining.append((sound, end_time))
        self._active_sounds = remaining

    def _close_active_sounds(self) -> None:
        sounds = self._active_sounds
        self._active_sounds = []
        for sound, _end_time in sounds:
            with contextlib.suppress(Exception):
                sound.close()

    def _close_rust_playback(self) -> None:
        playback = self._rust_playback
        self._rust_playback = None
        if playback is None:
            return
        close = getattr(playback, "close", None)
        stop = getattr(playback, "stop", None)
        with contextlib.suppress(Exception):
            if callable(close):
                close()
            elif callable(stop):
                stop()
