"""Compatibility guarantees for the corrected wobble-rhythm example path."""

from __future__ import annotations

import importlib
import inspect
import runpy
import sys
from pathlib import Path


def test_wob_rhythm_keeps_the_historical_adapter_and_output_default(monkeypatch) -> None:
    synth_examples = Path("examples/12_synth").resolve()
    monkeypatch.syspath_prepend(str(synth_examples))
    canonical = importlib.import_module("wob_rhythm")
    historical = importlib.import_module("wob_rythm")

    assert historical.wob_rythm is canonical.wob_rhythm
    assert historical.main is canonical.main
    assert Path("examples/output/12_synth/wob_rhythm.wav") == canonical.OUTPUT
    assert Path("examples/output/12_synth/wob_rythm.wav") == historical.OUTPUT
    assert (
        inspect.signature(canonical.main).parameters["default_output"].default == canonical.OUTPUT
    )

    forwarded: dict[str, object] = {}

    def fake_main(*, default_output: Path, display_name: str) -> None:
        forwarded["default_output"] = default_output
        forwarded["display_name"] = display_name

    monkeypatch.setattr(canonical, "main", fake_main)
    monkeypatch.setattr(sys, "argv", [str(synth_examples / "wob_rythm.py")])
    runpy.run_path(str(synth_examples / "wob_rythm.py"), run_name="__main__")

    assert forwarded == {
        "default_output": Path("examples/output/12_synth/wob_rythm.wav"),
        "display_name": "wob_rythm",
    }
