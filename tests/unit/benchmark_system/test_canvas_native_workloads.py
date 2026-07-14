from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.schema.catalog import load_catalog
from benchmarks.suites.canvas.interactive import InteractiveWorkloadError, dispatch

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "benchmarks" / "canvas_v1.toml"


def test_canvas_catalog_keeps_only_bounded_native_window_workloads() -> None:
    catalog = load_catalog(CATALOG)
    native = [
        workload
        for workload in catalog.workloads
        if workload.execution_class.value == "native-interactive"
    ]

    assert len(native) == 26
    assert all(workload.id != "native-input-window" for workload in catalog.workloads)
    assert all("physical-input-automation" not in workload.capabilities for workload in native)
    assert all("physical-touch-device" not in workload.capabilities for workload in native)
    assert all("suites/canvas/workloads.py" in workload.source_files for workload in native)
    for workload in native:
        frames = workload.parameters.get("frames")
        counters = workload.parameters.get("required_counters")
        assert isinstance(frames, int) and frames >= 1
        assert isinstance(counters, list) and "frames_presented" in counters


def test_retired_native_input_route_fails_with_simple_direction() -> None:
    with pytest.raises(InteractiveWorkloadError, match="bounded native-interactive"):
        dispatch({}, "native-interactive")
