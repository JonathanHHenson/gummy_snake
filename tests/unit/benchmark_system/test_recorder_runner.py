from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.framework.modes import RunReport
from benchmarks.framework.runner import BenchmarkRecorderRunner, RunnerError, plan_isolated_run
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
        blocks = (100,) * request.timed_blocks
        return WorkerResult(
            request.request_id,
            True,
            {phase: "ok" for phase in PHASES},
            sum(blocks),
            request.work_units * request.timed_blocks,
            {"renderer": {"gpu_primitive_batches": 1, "gpu_encode_time_ms": 1.5}},
            blocks,
        )


def test_isolated_plan_snapshots_declared_inputs_and_builds_only_release_wheel(
    tmp_path: Path,
) -> None:
    plan = plan_isolated_run(ROOT, tmp_path / "build")

    assert {
        ".cargo",
        ".python-version",
        "Cargo.lock",
        "Cargo.toml",
        "README.md",
        "assets",
        "benchmarks",
        "crates",
        "license.txt",
        "pyproject.toml",
        "src",
        "uv.lock",
    } == set(plan.snapshot.declared_roots)
    assert plan.source_directory != ROOT
    assert (plan.source_directory / "src" / "gummysnake" / "__init__.py").is_file()
    assert plan.build.repository == plan.source_directory
    assert plan.build.command[:3] == ("uv", "build", "--wheel")
    assert plan.worker_command[-2:] == ("-m", "benchmarks.worker.main")
    assert plan.workspace.name == "worker-workspace"


def test_runner_build_install_and_import_verification_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = load_catalog(CATALOG)
    runner = BenchmarkRecorderRunner(ROOT, catalog, tmp_path / "build")
    plan = runner.plan()
    commands: list[tuple[str, ...]] = []
    command_cwds: list[Path] = []
    command_environments: list[Mapping[str, str] | None] = []

    def command(
        command: tuple[str, ...],
        *,
        cwd: Path,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        commands.append(command)
        command_cwds.append(cwd)
        command_environments.append(environment)
        if command[:3] == ("uv", "build", "--wheel"):
            plan.build.output_directory.mkdir(parents=True, exist_ok=True)
            (plan.build.output_directory / "gummy_snake-0.8.0.whl").write_bytes(b"wheel")

    monkeypatch.setattr(runner, "_run_command", command)
    wheel = runner._build_and_install(plan)
    runner._copy_worker_inputs(plan)
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
    assert command_cwds[0] == plan.source_directory
    build_environment = command_environments[0]
    assert build_environment is not None
    assert build_environment["GUMMY_BENCHMARK_SOURCE_COMMIT"] == plan.snapshot.head
    assert build_environment["GUMMY_BENCHMARK_SOURCE_DIGEST"] == plan.snapshot.digest
    assert build_environment["GUMMY_BENCHMARK_TREE_DIGEST"] == plan.snapshot.tree_digest
    assert build_environment["GUMMY_BENCHMARK_BUILD_PROFILE"] == "release"
    assert build_environment["GUMMY_BENCHMARK_BUILD_FEATURES"] == "extension-module"
    assert commands[1][:2] == ("uv", "venv")
    assert commands[2][:3] == ("uv", "pip", "install")
    assert not (plan.workspace / "src").exists()
    assert (plan.workspace / "benchmarks" / "worker" / "main.py").is_file()


def test_runtime_preflight_verifies_wheel_artifact_abi_features_and_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = BenchmarkRecorderRunner(ROOT, load_catalog(CATALOG), tmp_path / "build")
    plan = runner.plan()
    wheel = plan.build.output_directory / "gummy_snake-0.8.0.whl"
    wheel.parent.mkdir(parents=True, exist_ok=True)
    native = (
        plan.build.isolated_environment
        / "lib"
        / "site-packages"
        / "gummysnake"
        / "rust"
        / "_canvas.so"
    )
    native.parent.mkdir(parents=True)
    native.write_bytes(b"native-extension")
    package = native.parents[1] / "__init__.py"
    package.write_text("")
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("gummysnake/rust/_canvas.so", b"native-extension")
        archive.writestr(
            "gummy_snake-0.8.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: maturin 1.9.4\n"
            "Root-Is-Purelib: false\nTag: cp312-cp312-macosx_11_0_arm64\n",
        )
    payload = {
        "package_location": str(package.resolve()),
        "package_version": "0.8.0",
        "native_location": str(native.resolve()),
        "native_hash": "sha256:3fffc581f0c914537e4f166c980a6b43d9e7dbba6fd731c43767eb35a80f2f7e",
        "canvas_abi": 19,
        "expected_canvas_abi": 19,
        "ecs_abi": 4,
        "expected_ecs_abi": 4,
        "health": "rust-canvas",
        "native_reported": {
            "source_commit": plan.snapshot.head,
            "source_digest": plan.snapshot.digest,
            "tree_digest": plan.snapshot.tree_digest,
            "profile": "release",
            "features": ["extension-module"],
        },
    }
    payload["native_hash"] = "sha256:" + hashlib.sha256(b"native-extension").hexdigest()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, json.dumps(payload) + "\n", ""
        ),
    )

    provenance = runner._verify_runtime_provenance(plan, wheel, str(package.resolve()))

    assert provenance["native_artifact_hash"] == payload["native_hash"]
    assert provenance["build_features"] == ["extension-module"]
    assert provenance["wheel_build"] == {
        "generator": "maturin 1.9.4",
        "tags": ["cp312-cp312-macosx_11_0_arm64"],
    }
    payload["native_reported"] = None
    with pytest.raises(RunnerError, match="native benchmark provenance"):
        runner._verify_runtime_provenance(plan, wheel, str(package.resolve()))

    payload["native_reported"] = {
        "source_commit": plan.snapshot.head,
        "source_digest": plan.snapshot.digest,
        "tree_digest": plan.snapshot.tree_digest,
        "profile": "release",
        "features": ["extension-module"],
    }
    payload["canvas_abi"] = 18
    with pytest.raises(RunnerError, match="canvas runtime ABI"):
        runner._verify_runtime_provenance(plan, wheel, str(package.resolve()))


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
    runner = BenchmarkRecorderRunner(ROOT, catalog, tmp_path / "build")
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

    runner = BenchmarkRecorderRunner(
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
    expected = sum(runner._profile(workload).processes for workload in catalog.workloads)
    assert len(fake.requests) == expected
    diagnostics = record.run_conditions["worker_diagnostics"]
    assert isinstance(diagnostics, Mapping)
    first = diagnostics["lifecycle-hidpi:headless-continuous-clear-loop"]
    assert isinstance(first, Sequence)
    assert first[0]["renderer"]["gpu_encode_time_ms"] == Decimal("1.5")

    class FailingWorker:
        def run(self, request: WorkerRequest) -> WorkerResult:
            raise WorkerError(f"failed {request.workload_id}")

    def failing_worker_factory(command: tuple[str, ...], cwd: Path) -> FailingWorker:
        del command, cwd
        return FailingWorker()

    failed = BenchmarkRecorderRunner(
        ROOT, catalog, tmp_path / "failure", worker_factory=failing_worker_factory
    )
    monkeypatch.setattr(failed, "plan", lambda: plan)
    monkeypatch.setattr(failed, "_build_and_install", lambda _plan: wheel)
    monkeypatch.setattr(failed, "_copy_worker_inputs", lambda _plan: None)
    monkeypatch.setattr(
        failed,
        "_verify_installed_import",
        lambda _plan: "/venv/site-packages/gummysnake/__init__.py",
    )
    monkeypatch.setattr(
        failed,
        "_verify_runtime_provenance",
        lambda *_args: {"canvas_abi": 19, "ecs_abi": 4},
    )
    report: RunReport = failed.run(BenchmarkMode.WORKTREE)
    assert report.complete is False
    assert report.record is None
