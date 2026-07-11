"""Regression coverage for the canvas-owned PyO3 synth adapter."""

from __future__ import annotations

import pytest

from gummysnake.rust.canvas import canvas_abi_version, require_canvas_runtime


def _sine_event() -> dict[str, object]:
    return {
        "node_id": 1,
        "order": 0,
        "kind": "play",
        "time_seconds": 0.0,
        "value": 60,
        "opts": {"release": 0.01, "amp": 0.1},
        "synth_name": "_sine",
        "synth_opts": {},
        "fx_chain": [],
        "controls": [],
    }


def test_canvas_owned_synth_functions_preserve_names_outputs_and_value_errors() -> None:
    runtime = require_canvas_runtime()

    event_wav = runtime.synth_render_event_wav(_sine_event(), 8_000)
    plan_wav = runtime.synth_render_plan_wav([_sine_event()], 0.02, 8_000)

    assert event_wav.startswith(b"RIFF")
    assert plan_wav.startswith(b"RIFF")
    assert canvas_abi_version() == 18

    with pytest.raises(ValueError) as serialized_error:
        runtime.synth_render_serialized_plan_wav(b"", 8_000)
    assert str(serialized_error.value) == "ValueError: serialized synth physical plan is too short."

    with pytest.raises(ValueError) as duration_error:
        runtime.synth_render_plan_wav([], -0.01, 8_000)
    assert str(duration_error.value) == "synth plan render duration cannot be negative."
