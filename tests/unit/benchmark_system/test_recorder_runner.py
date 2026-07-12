from __future__ import annotations

import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.framework.modes import RunReport
from benchmarks.framework.runner import CanvasRecorderRunner, plan_isolated_run
from benchmarks.governance import BenchmarkMode
from benchmarks.schema.catalog import load_catalog
from benchmarks.schema.records import ComparisonFingerprint
from benchmarks.worker.protocol import PHASES, WorkerError, WorkerRequest, WorkerResult

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "benchmarks" / "canvas_v1.toml"


class FakeWorker:
    def __init__(self) -> None:
        self.requests: list[WorkerRequest] = []

    def run(self, request: WorkerRequest) -> WorkerResult:
        self.requests.append(request)
        return WorkerResult(
            request.request_id,
            True,
            {phase: "ok" for phase in PHASES},
            100,
            request.work_units,
            {"renderer": {"gpu_primitive_batches": 1, "gpu_encode_time_ms": 1.5}},
        )


def test_isolated_plan_snapshots_declared_inputs_and_builds_only_release_wheel(
    tmp_path: Path,
) -> None:
    plan = plan_isolated_run(ROOT, tmp_path / "build")

    assert {"src", "crates", "benchmarks", "pyproject.toml", "uv.lock", ".cargo"} == set(
        plan.snapshot.declared_roots
    )
    assert plan.build.command[:3] == ("uv", "build", "--wheel")
    assert plan.worker_command[-2:] == ("-m", "benchmarks.worker.main")
    assert plan.workspace.name == "worker-workspace"


def test_runner_build_install_and_import_verification_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = load_catalog(CATALOG)
    runner = CanvasRecorderRunner(ROOT, catalog, tmp_path / "build")
    plan = runner.plan()
    commands: list[tuple[str, ...]] = []

    def command(command: tuple[str, ...], *, cwd: Path) -> None:
        commands.append(command)
        if command[:3] == ("uv", "build", "--wheel"):
            plan.build.output_directory.mkdir(parents=True, exist_ok=True)
            (plan.build.output_directory / "gummy_snake-0.8.0.whl").write_bytes(b"wheel")

    monkeypatch.setattr(runner, "_run_command", command)
    wheel = runner._build_and_install(plan)
    runner._copy_worker_inputs(plan.workspace)
    installed = (
        plan.build.isolated_environment
        / "lib"
        / "python3.12"
        / "site-packages"
        / "gummysnake"
        / "__init__.py"
    )
    installed.parent.mkdir(parents=True)
    installed.write_text("")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, str(installed) + "\n", ""),
    )

    assert runner._verify_installed_import(plan) == str(installed.resolve())
    assert wheel.name == "gummy_snake-0.8.0.whl"
    assert commands[0][:3] == ("uv", "build", "--wheel")
    assert commands[1][:2] == ("uv", "venv")
    assert commands[2][:3] == ("uv", "pip", "install")
    assert not (plan.workspace / "src").exists()
    assert (plan.workspace / "benchmarks" / "worker" / "main.py").is_file()


@pytest.mark.parametrize(
    ("case_id", "draw_count"),
    [
        ("headless-uniform-primitives-1k", 1_000),
        ("headless-mixed-primitives-5k", 5_000),
        ("headless-paths-1k-by-32", 1_000),
        ("headless-nested-clips-depth-4-by-32", 1_000),
        ("headless-sprite-uniqueness-mutation", 17),
        ("headless-text-reuse-script", 36),
        ("headless-pixel-read-write-locality", 64),
        ("headless-ordered-effects", 1),
    ],
)
def test_recorder_uses_each_declared_draw_record_count(
    tmp_path: Path, case_id: str, draw_count: int
) -> None:
    catalog = load_catalog(CATALOG)
    runner = CanvasRecorderRunner(ROOT, catalog, tmp_path / "build")
    workload = next(workload for workload in catalog.workloads if workload.case_id == case_id)

    assert runner._work_per_block(workload) == draw_count


def test_recorder_requires_every_catalog_workload_and_invalidates_on_worker_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = load_catalog(CATALOG)
    fake = FakeWorker()

    def fake_worker_factory(command: tuple[str, ...], cwd: Path) -> FakeWorker:
        del command, cwd
        return fake

    runner = CanvasRecorderRunner(
        ROOT, catalog, tmp_path / "build", worker_factory=fake_worker_factory
    )
    plan = runner.plan()
    wheel = tmp_path / "wheel.whl"
    wheel.write_bytes(b"wheel")
    monkeypatch.setattr(
        "benchmarks.framework.runner.probe_machine",
        lambda **_kwargs: ComparisonFingerprint(
            {"architecture": "x86_64", "runtime_route": "canvas"}
        ),
    )

    record = runner._record(plan, wheel, "/venv/site-packages/gummysnake/__init__.py")

    assert len(record.metrics) == len(catalog.workloads)
    assert {request.execution_class.value for request in fake.requests} == {
        "headless",
        "native-interactive",
    }
    expected = sum(
        runner._profile(workload).processes * runner._profile(workload).blocks_per_process
        for workload in catalog.workloads
    )
    assert len(fake.requests) == expected
    diagnostics = record.run_conditions["worker_diagnostics"]
    assert isinstance(diagnostics, dict)
    first = diagnostics["lifecycle-hidpi:headless-continuous-clear-loop"]
    assert isinstance(first, list)
    assert first[0]["renderer"]["gpu_encode_time_ms"] == Decimal("1.5")

    class FailingWorker:
        def run(self, request: WorkerRequest) -> WorkerResult:
            raise WorkerError(f"failed {request.workload_id}")

    def failing_worker_factory(command: tuple[str, ...], cwd: Path) -> FailingWorker:
        del command, cwd
        return FailingWorker()

    failed = CanvasRecorderRunner(
        ROOT, catalog, tmp_path / "failure", worker_factory=failing_worker_factory
    )
    monkeypatch.setattr(failed, "plan", lambda: plan)
    monkeypatch.setattr(failed, "_build_and_install", lambda _plan: wheel)
    monkeypatch.setattr(failed, "_copy_worker_inputs", lambda _workspace: None)
    monkeypatch.setattr(
        failed,
        "_verify_installed_import",
        lambda _plan: "/venv/site-packages/gummysnake/__init__.py",
    )
    report: RunReport = failed.run(BenchmarkMode.WORKTREE)
    assert report.complete is False
    assert report.record is None
