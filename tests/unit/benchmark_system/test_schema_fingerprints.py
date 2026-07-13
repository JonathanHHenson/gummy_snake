from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from typing import cast

import pytest

from benchmarks.schema.records import ComparisonFingerprint, RecordError, normalize_architecture


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("ARM64", "arm64"),
        ("aarch64", "arm64"),
        ("arm64e", "arm64"),
        ("AMD64", "x86_64"),
        ("x64", "x86_64"),
        ("x86-64", "x86_64"),
        ("i686", "x86"),
    ],
)
def test_architecture_aliases_are_cross_platform_canonical(alias: str, canonical: str) -> None:
    assert normalize_architecture(alias) == canonical


def _platform_fingerprint(
    *,
    os_product: str,
    hardware: str,
    process: str,
    gpu_driver: str = "1.0",
) -> ComparisonFingerprint:
    return ComparisonFingerprint(
        {
            "architecture": hardware,
            "hardware_architecture": hardware,
            "process_architecture": process,
            "os": {"product": os_product, "release": "test", "build": "test-build"},
            "cpu": {"model": "simulated", "topology": {"logical_cores": 8}},
            "memory": {"gib_class": "16 GiB"},
            "virtualization": "none",
            "python": {"implementation": "CPython", "version": "3.12.0"},
            "toolchain": {"rustc": "1.88.0"},
            "build_settings": {"profile": "release", "features": ["gpu"]},
            "runtime_route": "isolated-release-wheel-canvas",
            "gpu": {"model": "simulated-gpu", "backend": "metal", "driver": gpu_driver},
            "storage_route": {
                "device_class": "ssd",
                "filesystem": "apfs",
                "mount_route": "physical",
                "cache_route": "uv-default",
            },
            "display_route": {"route": "built-in", "scale": 2},
            "audio_route": {},
        }
    )


def test_macos_arm_and_alias_spelling_produce_the_same_fingerprint() -> None:
    native = _platform_fingerprint(os_product="macos", hardware="arm64", process="arm64")
    aliases = _platform_fingerprint(os_product="Darwin", hardware="aarch64", process="ARM64")

    assert aliases.stable["hardware_architecture"] == "arm64"
    assert aliases.stable["os"] == {
        "product": "macos",
        "release": "test",
        "build": "test-build",
    }
    assert native.id == aliases.id


def test_rosetta_remains_distinct_from_native_macos_execution() -> None:
    native = _platform_fingerprint(os_product="macos", hardware="arm64", process="arm64")
    rosetta_data = deepcopy(native.to_dict()["stable"])
    assert isinstance(rosetta_data, dict)
    rosetta_data["process_architecture"] = "AMD64"
    rosetta_data["translation"] = "Rosetta 2"
    rosetta = ComparisonFingerprint(rosetta_data)

    assert rosetta.stable["hardware_architecture"] == "arm64"
    assert rosetta.stable["process_architecture"] == "x86_64"
    assert rosetta.stable["translation"] == "rosetta-2"
    assert rosetta.id != native.id


@pytest.mark.parametrize(
    ("os_product", "architecture"),
    [("Linux", "AMD64"), ("Windows_NT", "x64"), ("macOS", "x86-64")],
)
def test_simulated_x86_platforms_normalize_without_collapsing_os_identity(
    os_product: str, architecture: str
) -> None:
    fingerprint = _platform_fingerprint(
        os_product=os_product, hardware=architecture, process=architecture
    )

    assert fingerprint.stable["hardware_architecture"] == "x86_64"
    assert fingerprint.stable["process_architecture"] == "x86_64"
    expected_os = {"linux": "linux", "windows_nt": "windows", "macos": "macos"}[os_product.lower()]
    os_facts = fingerprint.stable["os"]
    assert isinstance(os_facts, Mapping)
    assert os_facts["product"] == expected_os


def test_gpu_driver_and_runtime_route_are_stable_comparison_dimensions() -> None:
    first = _platform_fingerprint(
        os_product="linux", hardware="x86_64", process="x86_64", gpu_driver="550.1"
    )
    second = _platform_fingerprint(
        os_product="linux", hardware="x86_64", process="x86_64", gpu_driver="551.0"
    )
    stable = first.to_dict()["stable"]
    assert isinstance(stable, dict)
    changed_route = dict(stable)
    changed_route["runtime_route"] = "native-interactive-canvas"

    assert first.id != second.id
    assert first.id != ComparisonFingerprint(changed_route).id


@pytest.mark.parametrize(
    "private_fragment",
    [
        {"hostname": "private"},
        {"gpu": {"board_serial_number": "private"}},
        {"storage_route": {"volume_uuid": "private"}},
        {"subject_commit": "candidate-specific"},
        {"build": {"wheel_hash": "candidate-specific"}},
        {"free_memory": 123},
        {"cpu": {"current_frequency": 4_000_000_000}},
        {"load_average": "0.5"},
    ],
)
def test_fingerprint_rejects_private_candidate_and_volatile_values(
    private_fragment: dict[str, object],
) -> None:
    with pytest.raises(RecordError, match="must exclude"):
        ComparisonFingerprint(private_fragment)


def test_fingerprint_mapping_is_immutable_and_id_is_verified() -> None:
    fingerprint = ComparisonFingerprint({"architecture": "AMD64", "runtime_route": "headless"})
    payload = fingerprint.to_dict()

    assert ComparisonFingerprint.from_mapping(payload) == fingerprint
    stable = cast(MutableMapping[str, object], fingerprint.stable)
    with pytest.raises(TypeError):
        stable["architecture"] = "arm64"
    payload["id"] = "0" * 64
    with pytest.raises(RecordError, match="id does not match"):
        ComparisonFingerprint.from_mapping(payload)
