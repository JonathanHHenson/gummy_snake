from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import pytest

from benchmarks.worker import provenance


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("AMD64", "x86_64"),
        ("x86_64h", "x86_64"),
        ("i686", "x86_32"),
        ("aarch64", "arm64"),
        ("ARMv8L", "arm64"),
        ("ppc64le", "powerpc64le"),
    ],
)
def test_architecture_aliases_are_cross_platform(raw: str, normalized: str) -> None:
    assert provenance.normalize_architecture(raw) == normalized


def test_provenance_probe_normalizes_macos_m4_max_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provenance.sys, "platform", "darwin")
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.setattr(provenance.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(provenance.platform, "python_implementation", lambda: "CPython")
    monkeypatch.setattr(provenance.platform, "python_version", lambda: "3.12.11")
    responses = {
        ("sysctl", "-n", "hw.machine"): "arm64",
        ("sysctl", "-n", "hw.model"): "Mac16,5",
        ("sysctl", "-n", "machdep.cpu.brand_string"): "Apple M4 Max",
        ("sysctl", "-n", "hw.logicalcpu"): "16",
        ("sysctl", "-n", "hw.physicalcpu"): "16",
        ("sysctl", "-n", "hw.memsize"): "137438953472",
        ("sysctl", "-n", "kern.hv_vmm_present"): "0",
        ("sw_vers", "-productVersion"): "26.5.1",
        ("sw_vers", "-buildVersion"): "25F80",
        ("rustc", "--version"): "rustc 1.88.0 (6b00bc388 2025-06-23)",
        ("cargo", "--version"): "cargo 1.88.0 (873a06493 2025-05-10)",
        ("uv", "--version"): "uv 0.8.8 (abcdef)",
        ("uv", "cache", "dir"): "/Users/example/Library/Caches/uv",
        ("stat", "-f", "%T", "."): "apfs",
        (
            "system_profiler",
            "SPDisplaysDataType",
            "-json",
        ): json.dumps(
            {
                "SPDisplaysDataType": [
                    {
                        "_name": "Apple M4 Max",
                        "sppci_cores": "40",
                        "spdisplays_mtlgpufamilysupport": "spdisplays_metal4",
                        "spdisplays_ndrvs": [
                            {
                                "_name": "Color LCD",
                                "spdisplays_main": "spdisplays_yes",
                                "spdisplays_builtin": "spdisplays_yes",
                                "spdisplays_display_type": "spdisplays_built-in-liquid-retina-xdr",
                                "spdisplays_pixelresolution": "3456 x 2234",
                                "spdisplays_scale": 2,
                            }
                        ],
                    }
                ]
            }
        ),
    }
    monkeypatch.setattr(provenance, "_command_output", lambda command: responses.get(command))

    fingerprint = provenance.probe_machine(
        runtime_route="isolated-release-wheel-canvas",
        build_settings={"tool": "uv"},
    )

    assert fingerprint.stable["architecture"] == "arm64"
    assert fingerprint.stable["hardware_architecture"] == "arm64"
    assert fingerprint.stable["process_architecture"] == "arm64"
    assert fingerprint.stable["hardware_model"] == "Mac16,5"
    assert fingerprint.stable["os"] == {
        "product": "macos",
        "release": "26.5.1",
        "build": "25F80",
    }
    assert fingerprint.stable["cpu"] == {
        "model": "Apple M4 Max",
        "topology": {"logical_cores": 16, "physical_cores": 16},
    }
    assert fingerprint.stable["memory"] == {
        "total_bytes": 137438953472,
        "gib_class": "128 GiB",
    }
    assert fingerprint.stable["toolchain"] == {
        "python": "3.12.11",
        "rustc": "1.88.0",
        "cargo": "1.88.0",
        "uv": "0.8.8",
    }
    assert fingerprint.stable["gpu"] == {
        "model": "Apple M4 Max",
        "core_count": 40,
        "api": "metal",
        "api_version": "4",
    }
    assert fingerprint.stable["display_route"] == {
        "route": "built-in",
        "model": "Liquid Retina XDR Display",
        "resolution": {"width": 3456, "height": 2234},
        "scale": 2,
    }
    assert fingerprint.stable["storage_route"] == {
        "filesystem": "apfs",
        "cache_route": "uv-default",
    }
    assert fingerprint.stable["virtualization"] == "none"


def test_machine_facts_detect_rosetta_hardware_and_process_architectures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provenance.sys, "platform", "darwin")
    monkeypatch.setattr(provenance.platform, "machine", lambda: "x86_64")
    responses = {
        ("sysctl", "-n", "hw.machine"): "x86_64",
        ("sysctl", "-in", "sysctl.proc_translated"): "1",
        ("sysctl", "-n", "hw.optional.arm64"): "1",
        ("sysctl", "-n", "hw.memsize"): "17179869184",
    }
    monkeypatch.setattr(provenance, "_command_output", lambda command: responses.get(command))

    facts = provenance._machine_facts()

    assert facts["hardware_architecture"] == "arm64"
    assert facts["process_architecture"] == "x86_64"
    assert facts["process_translation"] == "rosetta2"


def test_linux_probe_normalizes_cpu_gpu_storage_display_audio_and_virtualization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provenance.sys, "platform", "linux")
    monkeypatch.setattr(provenance.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(provenance.platform, "system", lambda: "Linux")
    monkeypatch.setattr(provenance.platform, "release", lambda: "6.12.0")
    monkeypatch.setattr(
        provenance.platform,
        "freedesktop_os_release",
        lambda: {"ID": "fedora", "VERSION_ID": "42"},
    )
    monkeypatch.setattr(provenance, "_memory_bytes", lambda: 32 * 1024**3)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    responses = {
        ("lscpu", "--json"): json.dumps(
            {
                "lscpu": [
                    {"field": "Model name:", "data": "Example CPU  9000"},
                    {"field": "CPU(s):", "data": "16"},
                    {"field": "Core(s) per socket:", "data": "8"},
                    {"field": "Socket(s):", "data": "1"},
                ]
            }
        ),
        ("lspci", "-mm"): '01:00.0 "VGA compatible controller" "Vendor" "Example GPU"',
        ("lspci", "-k"): (
            "01:00.0 VGA compatible controller: Example GPU\n\tKernel driver in use: example-gpu\n"
        ),
        ("vulkaninfo", "--summary"): "Vulkan Instance Version: 1.3.280",
        ("stat", "-f", "-c", "%T", "."): "btrfs",
        ("findmnt", "-no", "SOURCE", "--target", "."): "/dev/nvme0n1p2",
        ("lsblk", "--json", "--nodeps", "-o", "TYPE,ROTA,MODEL,TRAN"): json.dumps(
            {"blockdevices": [{"type": "disk", "rota": False, "model": "FastDisk", "tran": "nvme"}]}
        ),
        ("pactl", "info"): "Server Name: PulseAudio (on PipeWire 1.2.0)",
        ("systemd-detect-virt",): "kvm",
    }
    monkeypatch.setattr(provenance, "_command_output", lambda command: responses.get(command))

    fingerprint = provenance.probe_machine(
        runtime_route="wheel", build_settings={"profile": "release"}
    )

    assert fingerprint.stable["architecture"] == "x86_64"
    assert fingerprint.stable["cpu"] == {
        "model": "Example CPU 9000",
        "topology": {"logical_cores": 16, "physical_cores": 8},
    }
    assert fingerprint.stable["gpu"] == {
        "model": "Vendor Example GPU",
        "driver": "example-gpu",
        "api": "vulkan",
        "api_version": "1.3.280",
    }
    assert fingerprint.stable["display_route"] == {"session": "wayland"}
    assert fingerprint.stable["audio_route"] == {"server": "pipewire"}
    assert fingerprint.stable["storage_route"] == {
        "filesystem": "btrfs",
        "mount_route": "block-device",
        "model": "FastDisk",
        "transport": "nvme",
        "hardware_class": "solid-state",
    }
    assert fingerprint.stable["virtualization"] == "kvm"


def test_windows_probe_whitelists_hardware_fields_without_device_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provenance.sys, "platform", "win32")
    monkeypatch.setattr(provenance.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(provenance.platform, "system", lambda: "Windows")
    monkeypatch.setattr(provenance.platform, "win32_ver", lambda: ("11", "10.0.26100", "", ""))
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "ARM64")

    def output(command: tuple[str, ...]) -> str | None:
        text = command[-1]
        if "Win32_Processor" in text:
            return json.dumps(
                {"Name": "Example CPU", "NumberOfCores": 8, "NumberOfLogicalProcessors": 16}
            )
        if "TotalPhysicalMemory" in text:
            return str(64 * 1024**3)
        if "Win32_VideoController" in text:
            return json.dumps(
                {
                    "Name": "Example GPU",
                    "DriverVersion": "32.1",
                    "CurrentHorizontalResolution": 2560,
                    "CurrentVerticalResolution": 1440,
                }
            )
        if "Get-PhysicalDisk" in text:
            return json.dumps(
                {"FriendlyName": "Example SSD", "MediaType": "SSD", "BusType": "NVMe"}
            )
        if "Get-Volume" in text:
            return "NTFS"
        if "Win32_SoundDevice" in text:
            return json.dumps({"Name": "Example Audio", "Manufacturer": "Example"})
        if "Win32_ComputerSystem" in text:
            return json.dumps({"Manufacturer": "Example", "Model": "Workstation"})
        return None

    monkeypatch.setattr(provenance, "_command_output", output)
    fingerprint = provenance.probe_machine(
        runtime_route="wheel", build_settings={"profile": "release"}
    )

    assert fingerprint.stable["hardware_architecture"] == "arm64"
    assert fingerprint.stable["process_architecture"] == "x86_64"
    assert fingerprint.stable["gpu"] == {
        "model": "Example GPU",
        "driver": "32.1",
        "api": "direct3d",
    }
    display = cast(Mapping[str, object], fingerprint.stable["display_route"])
    storage = cast(Mapping[str, object], fingerprint.stable["storage_route"])
    assert display["resolution"] == {
        "width": 2560,
        "height": 1440,
    }
    assert storage["hardware_class"] == "ssd"
    assert fingerprint.stable["audio_route"] == {
        "model": "Example Audio",
        "manufacturer": "Example",
    }


def test_provenance_probe_rejects_private_supplied_route() -> None:
    with pytest.raises(provenance.ProvenanceError, match="private field gpu.serial"):
        provenance.probe_machine(
            runtime_route="test",
            build_settings={},
            gpu={"serial": "private"},
        )
    with pytest.raises(provenance.ProvenanceError, match="private field gpu.driver_path"):
        provenance.probe_machine(
            runtime_route="test",
            build_settings={},
            gpu={"driver_path": "/private/device/path"},
        )
