"""End-to-end regressions for the public synth examples."""

from __future__ import annotations

import runpy
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from gummysnake import synth as sy

_EXAMPLES = Path("examples/12_synth")
_SAMPLE_RATE = 8_000


def _example_track(file_name: str, track_name: str) -> Any:
    namespace = runpy.run_path(str(_EXAMPLES / file_name))
    factory = cast(Callable[[], Any], namespace[track_name])
    return factory()


def _assert_one_second_wav(path: Path) -> None:
    with wave.open(str(path), "rb") as wav:
        assert wav.getnchannels() == 2
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == _SAMPLE_RATE
        assert wav.getnframes() == _SAMPLE_RATE


@pytest.mark.parametrize(
    ("file_name", "track_name"),
    [
        ("acid_walk.py", "acid_walk"),
        ("control_fx_and_scales.py", "control_fx"),
    ],
)
def test_tb303_examples_save_one_second_with_builtin_cutoff_envelope_options(
    file_name: str,
    track_name: str,
    tmp_path: Path,
) -> None:
    track = _example_track(file_name, track_name)
    output = tmp_path / file_name.replace(".py", ".wav")

    saved = track.save(output, duration=sy.duration(secs=1), sample_rate=_SAMPLE_RATE)

    assert saved == output
    _assert_one_second_wav(output)


def test_tron_bikes_renders_one_second_to_sound() -> None:
    track = _example_track("tron_bikes.py", "tron_bikes")

    sound = track.to_sound(
        "tron_bikes.wav",
        duration=sy.duration(secs=1),
        sample_rate=_SAMPLE_RATE,
    )

    assert sound.duration == pytest.approx(1.0)
    assert sound.to_bytes().startswith(b"RIFF")
