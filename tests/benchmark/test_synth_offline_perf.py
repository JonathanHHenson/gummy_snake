from __future__ import annotations

import statistics
import time
import wave
from io import BytesIO

import pytest

from tests.helpers.synth_tracks_fixtures import _slicer_fx_track

REPEATS = 3
SAMPLE_RATE = 44_100
DURATION_SECONDS = 0.25


@pytest.mark.benchmark
def test_offline_synth_serialized_plan_is_deterministic_and_reports_metrics() -> None:
    """Exercise the Rust serialized-plan renderer without native playback timing."""
    plan = _slicer_fx_track().physical_plan(duration=DURATION_SECONDS)
    payload = plan.to_bytes()
    timings_ms: list[float] = []
    renders: list[bytes] = []

    for _ in range(REPEATS):
        start = time.perf_counter_ns()
        renders.append(_slicer_fx_track().render(duration=DURATION_SECONDS))
        timings_ms.append((time.perf_counter_ns() - start) / 1_000_000)

    with wave.open(BytesIO(renders[0]), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        pcm = wav.readframes(frames)

    non_silent_samples = sum(byte != 0 for byte in pcm)
    repeat_byte_equal = all(render == renders[0] for render in renders[1:])
    print(
        "offline_synth "
        f"sample_rate_hz={sample_rate} duration_seconds={DURATION_SECONDS} "
        f"serialized_plan_bytes={len(payload)} wav_bytes={len(renders[0])} "
        f"pcm_frames={frames} channels={channels} sample_width_bytes={sample_width} "
        f"non_silent_bytes={non_silent_samples} repeat_byte_equal={repeat_byte_equal} "
        f"median_render_ms={statistics.median(timings_ms):.3f}"
    )
    assert channels == 2
    assert sample_width == 2
    assert sample_rate == SAMPLE_RATE
    assert frames == int(DURATION_SECONDS * SAMPLE_RATE)
    assert non_silent_samples > 0
    assert repeat_byte_equal
