"""Release-wheel, isolated-worker Canvas benchmark recorder."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..governance import BenchmarkMode
from ..schema.canonical import file_hash
from ..schema.catalog import Catalog, CatalogError, Workload
from ..schema.records import BenchmarkRecord, MetricResult, Provenance
from ..worker.protocol import FreshWorker, WorkerError, WorkerRequest, WorkerResult
from ..worker.provenance import ReleaseBuildPlan, probe_machine, release_build_plan
from .modes import RunReport
from .snapshot import SourceSnapshot, snapshot_declared_roots
from .statistics import (
    Decision,
    SamplingProfile,
    compare_samples,
    median_of_process_medians,
    split_half_stable,
)


class RunnerError(RuntimeError):
    """An isolated Canvas recording run could not be prepared or completed."""


# Every root is an explicit source/build/benchmark/config input. These names are
# intentionally fixed rather than inferred from package discovery.
DECLARED_INPUT_ROOTS = (
    ".cargo",
    "benchmarks",
    "crates",
    "pyproject.toml",
    "src",
    "uv.lock",
)

_CANVAS_PROFILES: dict[str, SamplingProfile] = {
    "canvas-bounded-v1": SamplingProfile("canvas-bounded-v1", 2_000_000_000, 1, 9, 5, 27),
    "canvas-native-bounded-v1": SamplingProfile(
        "canvas-native-bounded-v1", 3_000_000_000, 1, 11, 5, 33
    ),
}


@dataclass(frozen=True, slots=True)
class IsolatedRunPlan:
    """The reproducible release build and worker layout for one source snapshot."""

    snapshot: SourceSnapshot
    build: ReleaseBuildPlan
    workspace: Path
    worker_command: tuple[str, ...]


class _WorkerClient(Protocol):
    def run(self, request: WorkerRequest) -> WorkerResult: ...


class _FreshWorkerFactory(Protocol):
    def __call__(self, command: tuple[str, ...], cwd: Path) -> _WorkerClient: ...


def _default_worker(command: tuple[str, ...], cwd: Path) -> FreshWorker:
    return FreshWorker(command, cwd=cwd)


def plan_isolated_run(repository: Path, output_directory: Path) -> IsolatedRunPlan:
    """Snapshot every declared input before any release build is run."""

    repository = repository.resolve()
    snapshot = snapshot_declared_roots(repository, DECLARED_INPUT_ROOTS)
    build = release_build_plan(repository, output_directory)
    workspace = build.output_directory / "worker-workspace"
    interpreter = build.isolated_environment / "bin" / "python"
    return IsolatedRunPlan(
        snapshot, build, workspace, (str(interpreter), "-m", "benchmarks.worker.main")
    )


class CanvasRecorderRunner:
    """Run the entire static Canvas catalog from a wheel-installed fresh worker."""

    def __init__(
        self,
        repository: Path,
        catalog: Catalog,
        output_directory: Path,
        *,
        worker_factory: _FreshWorkerFactory = _default_worker,
    ) -> None:
        self.repository = repository.resolve()
        self.catalog = catalog
        self.output_directory = output_directory.resolve()
        self._worker_factory = worker_factory
        if any(workload.suite_id != "canvas" for workload in catalog.workloads):
            raise RunnerError("the isolated recorder supports only the static Canvas suite")

    def plan(self) -> IsolatedRunPlan:
        return plan_isolated_run(self.repository, self.output_directory)

    def _run_command(self, command: tuple[str, ...], *, cwd: Path) -> None:
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RunnerError(f"isolated command failed ({' '.join(command)}): {detail}")

    def _build_and_install(self, plan: IsolatedRunPlan) -> Path:
        plan.build.output_directory.mkdir(parents=True, exist_ok=True)
        self._run_command(plan.build.command, cwd=self.repository)
        wheels = sorted(plan.build.output_directory.glob("gummy_snake-*.whl"))
        if len(wheels) != 1:
            raise RunnerError("release build must produce exactly one gummy-snake wheel")
        wheel = wheels[0]
        self._run_command(("uv", "venv", str(plan.build.isolated_environment)), cwd=self.repository)
        interpreter = plan.build.isolated_environment / "bin" / "python"
        self._run_command(
            ("uv", "pip", "install", "--python", str(interpreter), str(wheel)), cwd=self.repository
        )
        return wheel

    def _copy_worker_inputs(self, workspace: Path) -> None:
        """Copy only the benchmark modules/catalog used by an isolated worker."""

        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)
        source = self.repository / "benchmarks"
        destination = workspace / "benchmarks"
        destination.mkdir()
        for name in ("__init__.py",):
            shutil.copy2(source / name, destination / name)
        for name in ("governance", "schema", "suites", "worker"):
            shutil.copytree(
                source / name,
                destination / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        shutil.copy2(self.catalog.path, destination / self.catalog.path.name)

    def _verify_installed_import(self, plan: IsolatedRunPlan) -> str:
        interpreter = plan.build.isolated_environment / "bin" / "python"
        code = "import gummysnake; print(gummysnake.__file__)"
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        result = subprocess.run(
            (str(interpreter), "-c", code),
            cwd=plan.workspace,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        if result.returncode:
            raise RunnerError(f"installed wheel import failed: {result.stderr.strip()}")
        location = Path(result.stdout.strip()).resolve()
        virtual_environment = plan.build.isolated_environment.resolve()
        source_tree = (self.repository / "src").resolve()
        if (
            not location.is_relative_to(virtual_environment)
            or "site-packages" not in location.parts
            or location.is_relative_to(source_tree)
        ):
            raise RunnerError(
                "gummysnake must resolve from the isolated venv site-packages, not source"
            )
        return str(location)

    @staticmethod
    def _profile(workload: Workload) -> SamplingProfile:
        try:
            return _CANVAS_PROFILES[workload.sampling_profile]
        except KeyError as error:
            raise RunnerError(
                f"unsupported static Canvas sampling profile: {workload.sampling_profile}"
            ) from error

    @staticmethod
    def _work_per_block(workload: Workload) -> int:
        parameter_by_unit = {
            "frame": "frames",
            "draw-record": "draw_count",
            "feature-operation": "image_count",
        }
        parameter = parameter_by_unit.get(workload.primary_metric.work_unit)
        value = workload.parameters.get(parameter, 1) if parameter else 1
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RunnerError(f"workload {workload.id} has invalid declared work for its metric")
        return value

    def _sample_workload(
        self, worker: _WorkerClient, workload: Workload, profile: SamplingProfile
    ) -> tuple[tuple[tuple[int, ...], ...], tuple[Mapping[str, object], ...]]:
        blocks: list[tuple[int, ...]] = []
        diagnostics: list[Mapping[str, object]] = []
        work = self._work_per_block(workload)
        for process_index in range(profile.processes):
            process_blocks: list[int] = []
            for block_index in range(profile.blocks_per_process):
                request = WorkerRequest(
                    request_id=f"{workload.id}-{workload.case_id}-{process_index}-{block_index}",
                    execution_class=workload.execution_class,
                    workload_id=workload.id,
                    seed=process_index * profile.blocks_per_process + block_index,
                    hash_seed=270_005 + process_index * profile.blocks_per_process + block_index,
                    timeout_seconds=120,
                    work_units=work,
                    payload={"parameters": dict(workload.parameters), "warmup_runs": 1},
                )
                result = worker.run(request)
                if result.elapsed_ns is None:
                    raise RunnerError("fresh worker returned no elapsed duration")
                process_blocks.append(result.elapsed_ns)
                diagnostics.append(dict(result.diagnostics))
            blocks.append(tuple(process_blocks))
        return tuple(blocks), tuple(diagnostics)

    def _record(
        self,
        plan: IsolatedRunPlan,
        wheel: Path,
        installed_location: str,
    ) -> tuple[BenchmarkRecord, bool]:
        worker = self._worker_factory(plan.worker_command, plan.workspace)
        metrics: list[MetricResult] = []
        diagnostic_runs: dict[str, list[Mapping[str, object]]] = {}
        stable = True
        for workload in self.catalog.workloads:
            profile = self._profile(workload)
            blocks, diagnostics = self._sample_workload(worker, workload, profile)
            work = self._work_per_block(workload)
            estimate = median_of_process_medians(blocks, work)
            stability = split_half_stable(workload.primary_metric, blocks, work)
            stable = stable and stability.decision is Decision.PASS
            metric = workload.primary_metric
            metrics.append(
                MetricResult(
                    workload.key,
                    blocks,
                    work,
                    estimate,
                    metric.unit,
                    metric.direction.value,
                    metric.transform.value,
                    estimate if metric.transform.value == "ratio" else None,
                )
            )
            diagnostic_runs[f"{workload.id}:{workload.case_id}"] = list(diagnostics)
        fingerprint = probe_machine(
            runtime_route="isolated-release-wheel-canvas",
            build_settings={"tool": "uv", "wheel": "release", "source_import_forbidden": True},
        )
        lockfile = self.repository / "uv.lock"
        provenance = Provenance(
            plan.snapshot.head,
            plan.snapshot.digest,
            plan.snapshot.digest,
            file_hash(wheel),
            file_hash(lockfile),
            {
                "command": list(plan.build.command),
                "declared_roots": list(plan.snapshot.declared_roots),
            },
            {"gummysnake_module": installed_location, "worker_command": list(plan.worker_command)},
        )
        return (
            BenchmarkRecord(
                fingerprint,
                provenance,
                "canvas",
                self.catalog.workloads[0].suite_version,
                self.catalog.digest,
                tuple(metrics),
                {
                    "worker_diagnostics": diagnostic_runs,
                    "all_catalog_workloads": len(self.catalog.workloads),
                },
            ),
            stable,
        )

    def run(self, mode: BenchmarkMode) -> RunReport:
        """Build once, then run every declared workload without execution-class filtering."""

        try:
            plan = self.plan()
            wheel = self._build_and_install(plan)
            self._copy_worker_inputs(plan.workspace)
            installed_location = self._verify_installed_import(plan)
            record, stable = self._record(plan, wheel, installed_location)
            return RunReport(record, complete=True, stable=stable)
        except (CatalogError, OSError, RunnerError, WorkerError, ValueError) as error:
            return RunReport(None, complete=False, stable=False, reason=str(error))


def compare_record_to_baseline(
    catalog: Catalog, baseline: object, candidate: BenchmarkRecord
) -> Decision:
    """Compare every static metric; one regression/inconclusive result blocks a record."""

    if not isinstance(baseline, Mapping):
        raise RunnerError("baseline record must be a decoded object")
    raw_metrics = baseline.get("metrics")
    if not isinstance(raw_metrics, list):
        raise RunnerError("baseline record has no metrics")
    by_key = {
        tuple(item.get("benchmark_key", ())): item
        for item in raw_metrics
        if isinstance(item, Mapping)
    }
    decisions: list[Decision] = []
    for workload, current in zip(
        self_workloads := catalog.workloads, candidate.metrics, strict=True
    ):
        raw = by_key.get(workload.key)
        if not isinstance(raw, Mapping):
            raise RunnerError(f"baseline misses static workload {workload.id}:{workload.case_id}")
        blocks = raw.get("raw_blocks_ns")
        work = raw.get("work_per_block")
        if not isinstance(blocks, list) or isinstance(work, bool) or not isinstance(work, int):
            raise RunnerError("baseline metric samples are malformed")
        baseline_blocks = tuple(
            tuple(value for value in block) for block in blocks if isinstance(block, list)
        )
        if len(baseline_blocks) != len(blocks):
            raise RunnerError("baseline metric samples are malformed")
        result = compare_samples(
            workload.primary_metric,
            baseline_blocks,
            current.raw_blocks_ns,
            work,
            family_size=len(self_workloads),
        )
        decisions.append(result.decision)
    if Decision.ABSOLUTE_FAILURE in decisions or Decision.REGRESSION in decisions:
        return Decision.REGRESSION
    if Decision.INCONCLUSIVE in decisions:
        return Decision.INCONCLUSIVE
    return Decision.PASS
