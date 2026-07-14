"""Release-wheel, isolated-worker recorder for registered benchmark suites."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from ..governance import BenchmarkMode
from ..runner_profiles import RunnerProfile, RunnerProfileError, load_runner_profile
from ..schema.canonical import file_hash
from ..schema.catalog import Catalog, CatalogError, Workload
from ..schema.records import BenchmarkRecord, MetricResult, Provenance
from ..suites.registry import REGISTERED_SUITE_IDS
from ..worker.protocol import FreshWorker, WorkerError, WorkerRequest, WorkerResult
from ..worker.provenance import (
    ReleaseBuildPlan,
    probe_machine,
    probe_run_conditions,
    release_build_plan,
    release_build_provenance,
)
from .modes import RunReport
from .snapshot import (
    SnapshotError,
    SourceSnapshot,
    materialize_source_snapshot,
    snapshot_declared_roots,
    validate_referenced_build_inputs,
    verify_materialized_source,
)
from .statistics import (
    PROFILES,
    Decision,
    SamplingProfile,
    compare_samples,
    median_of_process_medians,
)


class RunnerError(RuntimeError):
    """An isolated Canvas recording run could not be prepared or completed."""


# Every root is an explicit source/build/benchmark/config input. These names are
# intentionally fixed rather than inferred from package discovery.
DECLARED_INPUT_ROOTS = (
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
)

_SUITE_PROFILE_ALIASES: dict[str, SamplingProfile] = {
    "canvas-bounded-v1": SamplingProfile("canvas-bounded-v1", 0, 1, 2, 2, 2),
    "canvas-native-bounded-v1": SamplingProfile("canvas-native-bounded-v1", 0, 1, 2, 2, 2),
}


@dataclass(frozen=True, slots=True)
class IsolatedRunPlan:
    """The reproducible release build and worker layout for one source snapshot."""

    snapshot: SourceSnapshot
    source_directory: Path
    build: ReleaseBuildPlan
    workspace: Path
    worker_command: tuple[str, ...]


class _WorkerClient(Protocol):
    def run(self, request: WorkerRequest) -> WorkerResult: ...


class _FreshWorkerFactory(Protocol):
    def __call__(self, command: tuple[str, ...], cwd: Path) -> _WorkerClient: ...


def _default_worker(command: tuple[str, ...], cwd: Path) -> FreshWorker:
    return FreshWorker(command, cwd=cwd)


def _canonical_diagnostic_value(value: object) -> object:
    """Preserve public diagnostics while representing measured floats exactly in records."""

    if isinstance(value, float):
        if not math.isfinite(value):
            raise RunnerError("renderer diagnostics contain a non-finite floating-point value")
        return Decimal(str(value))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise RunnerError("renderer diagnostics must use string mapping keys")
        return {key: _canonical_diagnostic_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_canonical_diagnostic_value(item) for item in value)
    return value


def _canonical_diagnostics(value: Mapping[str, object]) -> Mapping[str, object]:
    return {key: _canonical_diagnostic_value(item) for key, item in value.items()}


def plan_isolated_run(repository: Path, output_directory: Path) -> IsolatedRunPlan:
    """Freeze every declared input into an external tree before planning the build."""

    repository = repository.resolve()
    output_directory = output_directory.resolve()
    snapshot = snapshot_declared_roots(repository, DECLARED_INPUT_ROOTS)
    validate_referenced_build_inputs(repository, snapshot)
    source_directory = materialize_source_snapshot(
        repository, snapshot, output_directory / "source-snapshot"
    )
    build = release_build_plan(source_directory, output_directory / "artifacts")
    workspace = output_directory / "worker-workspace"
    return IsolatedRunPlan(
        snapshot,
        source_directory,
        build,
        workspace,
        (str(build.interpreter), "-m", "benchmarks.worker.main"),
    )


class BenchmarkRecorderRunner:
    """Run one complete static suite catalog from wheel-installed fresh workers."""

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
        suite_ids = {workload.suite_id for workload in catalog.workloads}
        if len(suite_ids) != 1 or not suite_ids <= REGISTERED_SUITE_IDS:
            raise RunnerError("the isolated recorder requires one registered static suite")

    def plan(self) -> IsolatedRunPlan:
        return plan_isolated_run(self.repository, self.output_directory)

    def _run_command(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        process_environment = os.environ.copy()
        if environment:
            process_environment.update(environment)
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env=process_environment,
        )
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RunnerError(f"isolated command failed ({' '.join(command)}): {detail}")

    def _build_and_install(self, plan: IsolatedRunPlan) -> Path:
        if plan.build.repository.resolve() != plan.source_directory.resolve():
            raise RunnerError("release build source must be the materialized snapshot")
        verify_materialized_source(plan.snapshot, plan.source_directory)
        if plan.build.output_directory.exists():
            shutil.rmtree(plan.build.output_directory)
        plan.build.output_directory.mkdir(parents=True)
        build_environment = {
            **plan.build.environment,
            "GUMMY_BENCHMARK_SOURCE_COMMIT": plan.snapshot.head,
            "GUMMY_BENCHMARK_SOURCE_DIGEST": plan.snapshot.digest,
            "GUMMY_BENCHMARK_TREE_DIGEST": plan.snapshot.tree_digest,
            "GUMMY_BENCHMARK_BUILD_PROFILE": plan.build.profile,
            "GUMMY_BENCHMARK_BUILD_FEATURES": ",".join(plan.build.features),
        }
        self._run_command(
            plan.build.command,
            cwd=plan.source_directory,
            environment=build_environment,
        )
        verify_materialized_source(plan.snapshot, plan.source_directory)
        wheels = sorted(plan.build.output_directory.glob("gummy_snake-*.whl"))
        if len(wheels) != 1:
            raise RunnerError("release build must produce exactly one gummy-snake wheel")
        wheel = wheels[0]
        if plan.build.isolated_environment.exists():
            shutil.rmtree(plan.build.isolated_environment)
        self._run_command(
            ("uv", "venv", "--python", sys.executable, str(plan.build.isolated_environment)),
            cwd=plan.source_directory,
        )
        self._run_command(
            (
                "uv",
                "pip",
                "install",
                "--python",
                str(plan.build.interpreter),
                "--no-cache",
                str(wheel),
            ),
            cwd=plan.source_directory,
        )
        return wheel

    def _copy_worker_inputs(self, plan: IsolatedRunPlan) -> None:
        """Copy worker code only from the already-verified materialized snapshot."""

        workspace = plan.workspace
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)
        source = plan.source_directory / "benchmarks"
        destination = workspace / "benchmarks"
        destination.mkdir()
        for name in ("__init__.py",):
            shutil.copy2(source / name, destination / name)
        for name in ("framework", "governance", "schema", "suites", "worker"):
            shutil.copytree(
                source / name,
                destination / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        try:
            catalog_relative = self.catalog.path.resolve().relative_to(self.repository)
        except ValueError as error:
            raise RunnerError(
                "benchmark catalog must be inside the snapshotted repository"
            ) from error
        snapshotted_catalog = plan.source_directory / catalog_relative
        if not snapshotted_catalog.is_file():
            raise RunnerError("benchmark catalog is absent from the materialized source snapshot")
        shutil.copy2(snapshotted_catalog, destination / self.catalog.path.name)

    def _verify_installed_import(self, plan: IsolatedRunPlan) -> str:
        interpreter = plan.build.interpreter
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
    def _wheel_build_metadata(wheel: Path) -> Mapping[str, object]:
        try:
            with zipfile.ZipFile(wheel) as archive:
                wheel_files = [
                    name for name in archive.namelist() if name.endswith(".dist-info/WHEEL")
                ]
                if len(wheel_files) != 1:
                    raise RunnerError("release wheel must contain exactly one WHEEL metadata file")
                lines = archive.read(wheel_files[0]).decode("utf-8").splitlines()
        except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError) as error:
            raise RunnerError(f"cannot inspect release wheel build metadata: {error}") from error
        generator = [
            line.split(":", 1)[1].strip() for line in lines if line.startswith("Generator:")
        ]
        tags = sorted(line.split(":", 1)[1].strip() for line in lines if line.startswith("Tag:"))
        if len(generator) != 1 or not generator[0].lower().startswith("maturin ") or not tags:
            raise RunnerError("release wheel must report one Maturin generator and platform tag")
        return {"generator": generator[0], "tags": tags}

    @staticmethod
    def _wheel_native_artifact(wheel: Path) -> tuple[str, str]:
        try:
            with zipfile.ZipFile(wheel) as archive:
                members = [
                    name
                    for name in archive.namelist()
                    if name.startswith("gummysnake/rust/_canvas")
                    and name.endswith((".so", ".pyd", ".dylib"))
                ]
                if len(members) != 1:
                    raise RunnerError(
                        "release wheel must contain exactly one native Canvas extension artifact"
                    )
                payload = archive.read(members[0])
        except (OSError, zipfile.BadZipFile, KeyError) as error:
            raise RunnerError(f"cannot inspect release wheel runtime artifact: {error}") from error
        return members[0], "sha256:" + hashlib.sha256(payload).hexdigest()

    def _verify_runtime_provenance(
        self, plan: IsolatedRunPlan, wheel: Path, installed_location: str
    ) -> Mapping[str, object]:
        """Verify the loaded runtime against the built wheel before creating any worker."""

        wheel_build = self._wheel_build_metadata(wheel)
        wheel_member, wheel_extension_hash = self._wheel_native_artifact(wheel)
        with (plan.source_directory / "pyproject.toml").open("rb") as source:
            project = tomllib.load(source).get("project", {})
        expected_version = project.get("version") if isinstance(project, Mapping) else None
        if not isinstance(expected_version, str) or not expected_version:
            raise RunnerError("materialized pyproject has no package version")
        code = """
import hashlib, importlib.metadata, json
from pathlib import Path
import gummysnake
from gummysnake.rust import canvas, ecs
native = canvas.require_canvas_runtime()
native_path = Path(native.__file__).resolve()
reported = native.benchmark_provenance()
print(json.dumps({
    "package_location": str(Path(gummysnake.__file__).resolve()),
    "package_version": importlib.metadata.version("gummy-snake"),
    "native_location": str(native_path),
    "native_hash": "sha256:" + hashlib.sha256(native_path.read_bytes()).hexdigest(),
    "canvas_abi": canvas.canvas_abi_version(),
    "expected_canvas_abi": canvas.EXPECTED_CANVAS_ABI_VERSION,
    "ecs_abi": ecs.ecs_abi_version(),
    "expected_ecs_abi": ecs.EXPECTED_ECS_ABI_VERSION,
    "health": canvas.canvas_health_check(),
    "native_reported": reported,
}, sort_keys=True, separators=(",", ":")))
"""
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        environment["PYTHONSAFEPATH"] = "1"
        result = subprocess.run(
            (str(plan.build.interpreter), "-c", code),
            cwd=plan.workspace,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        if result.returncode:
            raise RunnerError(f"installed runtime provenance probe failed: {result.stderr.strip()}")
        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RunnerError("installed runtime provenance probe emitted invalid JSON") from error
        if not isinstance(raw, Mapping):
            raise RunnerError("installed runtime provenance probe must emit an object")
        package_location = Path(str(raw.get("package_location", ""))).resolve()
        native_location = Path(str(raw.get("native_location", ""))).resolve()
        environment_root = plan.build.isolated_environment.resolve()
        if str(package_location) != installed_location:
            raise RunnerError("runtime probe imported a different package than import preflight")
        if (
            not native_location.is_relative_to(environment_root)
            or "site-packages" not in native_location.parts
        ):
            raise RunnerError("native Canvas extension did not load from isolated site-packages")
        if raw.get("native_hash") != wheel_extension_hash:
            raise RunnerError("installed native Canvas artifact does not match the release wheel")
        if raw.get("package_version") != expected_version:
            raise RunnerError(
                "installed package version does not match materialized build metadata"
            )
        for name in ("canvas", "ecs"):
            if raw.get(f"{name}_abi") != raw.get(f"expected_{name}_abi"):
                raise RunnerError(f"installed {name} runtime ABI does not match its Python wrapper")
        if raw.get("health") != "rust-canvas":
            raise RunnerError("installed native Canvas runtime failed its health check")
        expected_native = {
            "source_commit": plan.snapshot.head,
            "source_digest": plan.snapshot.digest,
            "tree_digest": plan.snapshot.tree_digest,
            "profile": plan.build.profile,
            "features": list(plan.build.features),
        }
        reported = raw.get("native_reported")
        if not isinstance(reported, Mapping):
            raise RunnerError("native benchmark provenance must be an object")
        for key, expected in expected_native.items():
            if key not in reported or reported[key] != expected:
                raise RunnerError(f"native benchmark provenance mismatch for {key}")
        return {
            "gummysnake_module": package_location.relative_to(environment_root).as_posix(),
            "package_version": expected_version,
            "native_module": native_location.relative_to(environment_root).as_posix(),
            "native_wheel_member": wheel_member,
            "native_artifact_hash": wheel_extension_hash,
            "canvas_abi": raw["canvas_abi"],
            "ecs_abi": raw["ecs_abi"],
            "build_profile": plan.build.profile,
            "build_features": list(plan.build.features),
            "native_reported": dict(reported),
            "wheel_build": dict(wheel_build),
        }

    @staticmethod
    def _profile(workload: Workload) -> SamplingProfile:
        alias = _SUITE_PROFILE_ALIASES.get(workload.sampling_profile)
        if alias is not None:
            return alias
        try:
            return PROFILES[workload.sampling_profile]
        except KeyError as error:
            raise RunnerError(
                f"unsupported static sampling profile: {workload.sampling_profile}"
            ) from error

    @staticmethod
    def _work_per_block(workload: Workload) -> int:
        parameter_by_unit = {
            "frame": "frames",
            "draw-record": "draw_count",
            "feature-operation": "image_count",
        }
        parameter = parameter_by_unit.get(workload.primary_metric.work_unit)
        value = workload.parameters.get("work_units")
        if value is None:
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
            request = WorkerRequest(
                request_id=f"{workload.id}-{workload.case_id}-{process_index}",
                execution_class=workload.execution_class,
                workload_id=workload.id,
                suite_id=workload.suite_id,
                seed=process_index,
                hash_seed=270_005 + process_index,
                timeout_seconds=120,
                work_units=work,
                payload={"parameters": dict(workload.parameters), "warmup_runs": 1},
                timed_blocks=profile.blocks_per_process,
            )
            result = worker.run(request)
            result.require_complete(request)
            if len(result.elapsed_blocks_ns) != profile.blocks_per_process:
                raise RunnerError("fresh worker returned an incomplete timed block set")
            blocks.append(result.elapsed_blocks_ns)
            diagnostics.append(_canonical_diagnostics(result.diagnostics))
        return tuple(blocks), tuple(diagnostics)

    @staticmethod
    def _runner_profile(mode: BenchmarkMode) -> RunnerProfile | None:
        configured = os.environ.get("GUMMY_BENCHMARK_RUNNER_PROFILE")
        if not configured:
            if mode is BenchmarkMode.RECORD_HEAD:
                raise RunnerError(
                    "record-head requires GUMMY_BENCHMARK_RUNNER_PROFILE to name a runner profile"
                )
            return None
        try:
            return load_runner_profile(Path(configured))
        except RunnerProfileError as error:
            raise RunnerError(str(error)) from error

    def _record(
        self,
        plan: IsolatedRunPlan,
        wheel: Path,
        installed_location: str,
        runner_profile: RunnerProfile | None = None,
        runtime_provenance: Mapping[str, object] | None = None,
    ) -> BenchmarkRecord:
        build_facts = release_build_provenance(plan.build)
        suite_id = self.catalog.workloads[0].suite_id
        fingerprint = probe_machine(
            runtime_route=f"isolated-release-wheel-{suite_id}",
            build_settings={"tool": "uv", "wheel": "release", **build_facts},
        )
        if runner_profile is not None:
            try:
                runner_profile.validate(fingerprint.stable)
            except RunnerProfileError as error:
                raise RunnerError(str(error)) from error
        worker = self._worker_factory(plan.worker_command, plan.workspace)
        metrics: list[MetricResult] = []
        diagnostic_runs: dict[str, list[Mapping[str, object]]] = {}
        for workload in self.catalog.workloads:
            profile = self._profile(workload)
            blocks, diagnostics = self._sample_workload(worker, workload, profile)
            work = self._work_per_block(workload)
            estimate = median_of_process_medians(blocks, work)
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
        lockfile = plan.source_directory / "uv.lock"
        cargo_lockfile = plan.source_directory / "Cargo.lock"
        profile_condition = (
            {
                "runner_profile_path": str(runner_profile.path),
                "runner_profile_digest": runner_profile.digest,
            }
            if runner_profile is not None
            else {}
        )
        raw_artifact_build = (runtime_provenance or {}).get("wheel_build", {})
        artifact_build = dict(raw_artifact_build) if isinstance(raw_artifact_build, Mapping) else {}
        provenance = Provenance(
            plan.snapshot.head,
            plan.snapshot.digest,
            plan.snapshot.tree_digest,
            file_hash(wheel),
            file_hash(lockfile),
            {
                **build_facts,
                "command": list(plan.build.command),
                "declared_roots": list(plan.snapshot.declared_roots),
                "lockfiles": {
                    "uv.lock": file_hash(lockfile),
                    "Cargo.lock": file_hash(cargo_lockfile),
                },
                "artifact": artifact_build,
                **profile_condition,
            },
            {
                **dict(runtime_provenance or {"gummysnake_module": installed_location}),
                "worker_command": list(plan.worker_command),
            },
        )
        return BenchmarkRecord(
            fingerprint,
            provenance,
            suite_id,
            self.catalog.workloads[0].suite_version,
            self.catalog.digest,
            tuple(metrics),
            {
                "worker_diagnostics": diagnostic_runs,
                "all_catalog_workloads": len(self.catalog.workloads),
                "machine": probe_run_conditions(),
                **profile_condition,
            },
        )

    def run(self, mode: BenchmarkMode) -> RunReport:
        """Build once, then run every declared workload without execution-class filtering."""

        try:
            runner_profile = self._runner_profile(mode)
            plan = self.plan()
            wheel = self._build_and_install(plan)
            self._copy_worker_inputs(plan)
            installed_location = self._verify_installed_import(plan)
            runtime_provenance = self._verify_runtime_provenance(plan, wheel, installed_location)
            record = self._record(
                plan,
                wheel,
                installed_location,
                runner_profile,
                runtime_provenance,
            )
            return RunReport(record, complete=True)
        except (
            CatalogError,
            OSError,
            RunnerError,
            SnapshotError,
            WorkerError,
            ValueError,
        ) as error:
            return RunReport(None, complete=False, reason=str(error))


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
