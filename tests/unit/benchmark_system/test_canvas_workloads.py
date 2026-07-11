from __future__ import annotations

import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from benchmarks.suites.canvas.workloads import (
    CanvasWorkloadError,
    ExecutionRouteError,
    build_workload,
    dispatch,
)


@dataclass
class _Context:
    width: int = 16
    height: int = 12
    frame_count: int = 1

    def pixel_density(self) -> float:
        return 1.0

    def load_pixel_bytes(self) -> bytes:
        return bytes(self.width * self.height * 4)

    def renderer_performance_counters(self) -> dict[str, object]:
        return {"cpu_fallbacks": 0}


def test_canvas_workload_builder_preserves_distinct_headless_and_native_routes() -> None:
    parameters = {"frames": 1, "width": 16, "height": 12, "density": 1.0, "dispatch_route": "fast"}

    headless = build_workload("primitives-paths-order", parameters, "headless")
    native = build_workload("primitives-paths-order", parameters, "native-interactive")

    assert headless.headless is True
    assert native.headless is False
    assert native.execution_class.value == "native-interactive"
    with pytest.raises(ExecutionRouteError, match="require execution_class"):
        build_workload("lifecycle-hidpi", {}, "trial")
    with pytest.raises(CanvasWorkloadError, match="dispatch_route"):
        build_workload("lifecycle-hidpi", {"dispatch_route": "renderer-adapter"}, "headless")


def test_canvas_dispatch_passes_the_declared_route_without_headless_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocations: list[dict[str, object]] = []

    def run(**kwargs: object) -> _Context:
        invocations.append(kwargs)
        return _Context()

    monkeypatch.setitem(sys.modules, "gummysnake", SimpleNamespace(run=run))
    parameters = {"frames": 1, "width": 16, "height": 12, "density": 1.0}

    headless = dispatch("lifecycle-hidpi", parameters, "headless")
    native = dispatch("lifecycle-hidpi", parameters, "native-interactive")

    assert headless.frame_count == 1
    assert native.physical_desktop_requested is True
    assert [call["headless"] for call in invocations] == [True, False]
