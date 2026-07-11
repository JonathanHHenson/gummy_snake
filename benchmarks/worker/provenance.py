"""Release build planning and privacy-preserving cross-platform machine probing."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..schema.records import ComparisonFingerprint


class ProvenanceError(RuntimeError):
    """Release provenance cannot be planned or normalized safely."""


_ARCH_ALIASES = {
    "amd64": "x86_64",
    "x64": "x86_64",
    "x86-64": "x86_64",
    "aarch64": "arm64",
    "arm64e": "arm64",
}


def normalize_architecture(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "")
    return _ARCH_ALIASES.get(normalized, normalized)


@dataclass(frozen=True, slots=True)
class ReleaseBuildPlan:
    repository: Path
    output_directory: Path
    command: tuple[str, ...]
    isolated_environment: Path
    source_import_forbidden: bool = True

    def __post_init__(self) -> None:
        if not self.command or self.command[0] != "uv":
            raise ProvenanceError("authoritative release plans must use uv")


def release_build_plan(repository: Path, output_directory: Path) -> ReleaseBuildPlan:
    """Plan, but do not execute, the isolated release-wheel build required by workers."""

    repository = repository.resolve()
    output_directory = output_directory.resolve()
    return ReleaseBuildPlan(
        repository=repository,
        output_directory=output_directory,
        command=("uv", "build", "--wheel", "--out-dir", str(output_directory)),
        isolated_environment=output_directory / "venv",
    )


def _command_output(command: tuple[str, ...]) -> str | None:
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value or None


def _virtualization() -> str:
    if sys.platform.startswith("linux"):
        value = _command_output(("systemd-detect-virt", "--vm"))
        return "none" if value in (None, "none") else value
    # Do not infer a VM from hostnames, MAC addresses, or other private identifiers.
    return "unknown"


def probe_machine(
    *,
    runtime_route: str,
    build_settings: Mapping[str, object],
    gpu: Mapping[str, object] | None = None,
    display_route: Mapping[str, object] | None = None,
    audio_route: Mapping[str, object] | None = None,
    storage_route: Mapping[str, object] | None = None,
) -> ComparisonFingerprint:
    """Create a stable comparison fingerprint without candidate or private identity."""

    stable: dict[str, object] = {
        "architecture": normalize_architecture(platform.machine()),
        "process_architecture": normalize_architecture(platform.architecture()[0]),
        "os": {
            "system": platform.system().lower(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "cpu": {"model": platform.processor() or "unknown", "topology": os.cpu_count() or 0},
        "memory_class": "unknown",
        "virtualization": _virtualization(),
        "runtime_route": runtime_route,
        "build_settings": dict(build_settings),
        "gpu": dict(gpu or {}),
        "display_route": dict(display_route or {}),
        "audio_route": dict(audio_route or {}),
        "storage_route": dict(storage_route or {}),
    }
    return ComparisonFingerprint(stable)
