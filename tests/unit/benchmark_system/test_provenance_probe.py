from __future__ import annotations

import json

import pytest

from benchmarks.worker import provenance


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


def test_provenance_probe_rejects_private_supplied_route() -> None:
    with pytest.raises(provenance.ProvenanceError, match="private field gpu.serial"):
        provenance.probe_machine(
            runtime_route="test",
            build_settings={},
            gpu={"serial": "private"},
        )
