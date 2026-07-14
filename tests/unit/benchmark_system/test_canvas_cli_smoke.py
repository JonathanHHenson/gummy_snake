from __future__ import annotations

import json
from pathlib import Path

from benchmarks.cli import main
from benchmarks.schema.catalog import load_catalog
from benchmarks.suites import registry
from benchmarks.suites.registry import SuiteExecution

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "benchmarks" / "canvas_v1.toml"


def test_smoke_runs_only_static_headless_canvas_cases(monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []

    def fake_dispatch(
        suite_id: str,
        workload_id: str,
        _parameters: object,
        execution_class: object,
    ) -> SuiteExecution:
        assert suite_id == "canvas"
        calls.append((workload_id, str(execution_class)))
        return SuiteExecution({}, {"frames": 1, "pixel_bytes": 4})

    monkeypatch.setattr(registry, "dispatch", fake_dispatch)

    assert main(["smoke", str(CATALOG)]) == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    catalog = load_catalog(CATALOG)
    expected = [
        (workload.id, workload.case_id)
        for workload in catalog.workloads
        if workload.execution_class.value == "headless"
    ]
    assert [(line["workload"], line["case"]) for line in lines] == expected
    assert len(lines) == 66
    assert all(line["execution_class"] == "headless" for line in lines)
    assert [workload_id for workload_id, _ in calls] == [line["workload"] for line in lines]


def test_smoke_does_not_accept_policy_bypasses(capsys) -> None:
    assert main(["--threshold=0.02", "smoke", str(CATALOG)]) == 2
    assert "benchmark policy override is not supported" in capsys.readouterr().err
