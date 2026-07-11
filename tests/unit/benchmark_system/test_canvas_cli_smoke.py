from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from benchmarks.cli import main
from benchmarks.suites import canvas

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "benchmarks" / "canvas_v1.toml"


def test_smoke_runs_only_static_headless_canvas_cases(monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []

    def fake_dispatch(workload_id: str, _parameters: object, execution_class: object) -> object:
        calls.append((workload_id, str(execution_class)))
        return SimpleNamespace(frame_count=1, pixels=b"rgba")

    monkeypatch.setattr(canvas, "dispatch", fake_dispatch)

    assert main(["smoke", str(CATALOG)]) == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line["workload"] for line in lines] == [
        "lifecycle-hidpi",
        "primitives-paths-order",
        "images-text-pixels-effects",
    ]
    assert all(line["execution_class"] == "headless" for line in lines)
    assert [workload_id for workload_id, _ in calls] == [line["workload"] for line in lines]


def test_smoke_does_not_accept_authority_bypasses(capsys) -> None:
    assert main(["--threshold=0.02", "smoke", str(CATALOG)]) == 2
    assert "authoritative override is not supported" in capsys.readouterr().err
