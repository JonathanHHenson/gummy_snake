from __future__ import annotations

from pathlib import Path
from typing import NoReturn, cast

import pytest

from benchmarks.framework.runner import CanvasRecorderRunner, IsolatedRunPlan, RunnerError
from benchmarks.governance import BenchmarkMode
from benchmarks.runner_profiles import RunnerProfileError, load_runner_profile
from benchmarks.schema.catalog import load_catalog
from benchmarks.schema.records import ComparisonFingerprint

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "benchmarks" / "canvas_v1.toml"


def test_runner_profile_parses_and_recursively_validates_expected_environment(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "runner.toml"
    profile_path.write_text(
        """schema_version = 1

[expected]
architecture = "arm64"

[expected.cpu]
model = "Apple M4 Max"

[expected.cpu.topology]
logical_cores = 16
"""
    )

    profile = load_runner_profile(profile_path)

    profile.validate(
        {
            "architecture": "arm64",
            "cpu": {"model": "Apple M4 Max", "topology": {"logical_cores": 16}},
        }
    )
    with pytest.raises(RunnerProfileError, match=r"mismatch at expected.cpu.model"):
        profile.validate(
            {
                "architecture": "arm64",
                "cpu": {"model": "Apple M4", "topology": {"logical_cores": 16}},
            }
        )
    with pytest.raises(
        RunnerProfileError, match=r"requires unavailable field expected.cpu.topology"
    ):
        profile.validate({"architecture": "arm64", "cpu": {"model": "Apple M4 Max"}})


def test_runner_profile_tracked_macos_environment_is_valid() -> None:
    profile = load_runner_profile(
        ROOT / "benchmarks" / "runner_profiles" / "macos_m4_max_128gb.toml"
    )

    assert profile.schema_version == 1
    assert profile.expected["architecture"] == "arm64"
    assert profile.expected["hardware_model"] == "Mac16,5"
    assert profile.expected["memory"] == {
        "total_bytes": 137438953472,
        "gib_class": "128 GiB",
    }


def test_runner_profile_rejects_private_identity_fields(tmp_path: Path) -> None:
    profile_path = tmp_path / "private.toml"
    profile_path.write_text(
        """schema_version = 1

[expected]
hostname = "private-machine"
"""
    )

    with pytest.raises(RunnerProfileError, match="private field expected.hostname"):
        load_runner_profile(profile_path)


def test_runner_profile_record_head_requires_a_configured_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GUMMY_BENCHMARK_RUNNER_PROFILE", raising=False)
    runner = CanvasRecorderRunner(ROOT, load_catalog(CATALOG), tmp_path / "build")
    build_started = False

    def unexpected_build(_plan: IsolatedRunPlan) -> Path:
        nonlocal build_started
        build_started = True
        raise AssertionError("profile check must happen before the build")

    monkeypatch.setattr(runner, "_build_and_install", unexpected_build)

    report = runner.run(BenchmarkMode.RECORD_HEAD)

    assert report.complete is False
    assert "record-head requires GUMMY_BENCHMARK_RUNNER_PROFILE" in report.reason
    assert build_started is False


def test_runner_profile_validation_precedes_worker_sampling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_path = tmp_path / "runner.toml"
    profile_path.write_text(
        """schema_version = 1

[expected]
architecture = "arm64"
"""
    )
    profile = load_runner_profile(profile_path)
    worker_created = False

    def unexpected_worker(*_args: object, **_kwargs: object) -> NoReturn:
        nonlocal worker_created
        worker_created = True
        raise AssertionError("profile validation must precede worker creation")

    runner = CanvasRecorderRunner(
        ROOT,
        load_catalog(CATALOG),
        tmp_path / "build",
        worker_factory=unexpected_worker,
    )
    monkeypatch.setattr(
        "benchmarks.framework.runner.probe_machine",
        lambda **_kwargs: ComparisonFingerprint({"architecture": "x86_64"}),
    )

    with pytest.raises(RunnerError, match=r"mismatch at expected.architecture"):
        runner._record(cast(IsolatedRunPlan, object()), tmp_path / "wheel.whl", "", profile)
    assert worker_created is False
