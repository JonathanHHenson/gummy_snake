"""Release build planning and privacy-preserving cross-platform machine probing."""

from __future__ import annotations

import json
import os
import platform
import plistlib
import re
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
_PRIVATE_FIELD_TOKENS = frozenset(
    {
        "hostname",
        "host",
        "serial",
        "uuid",
        "mac",
        "macaddress",
        "mac_address",
        "machine_id",
        "machineid",
        "volume_id",
        "volumeid",
        "volume_uuid",
        "volumeuuid",
        "device_id",
        "deviceid",
    }
)
_VERSION = re.compile(r"\d+(?:\.\d+)+")
_DIMENSIONS = re.compile(r"(?P<width>\d+)\s*x\s*(?P<height>\d+)", re.IGNORECASE)
_DISPLAY_TYPE_PREFIX = "spdisplays_built-in-"
_DISPLAY_ACRONYMS = frozenset({"hdr", "lcd", "led", "oled", "xdr"})


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
    return value if result.returncode == 0 and value else None


def _command_version(command: tuple[str, ...]) -> str | None:
    output = _command_output(command)
    if output is None:
        return None
    match = _VERSION.search(output)
    return match.group(0) if match else None


def _integer_command(command: tuple[str, ...]) -> int | None:
    output = _command_output(command)
    if output is None:
        return None
    try:
        return int(output)
    except ValueError:
        return None


def _gib_class(total_bytes: int) -> str:
    return f"{total_bytes // (1024**3)} GiB"


def _add_if_present(target: dict[str, object], key: str, value: object | None) -> None:
    if value is not None:
        target[key] = value


def _privacy_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    parts = tuple(part for part in normalized.split("_") if part)
    return normalized in _PRIVATE_FIELD_TOKENS or any(
        part in _PRIVATE_FIELD_TOKENS for part in parts
    )


def _reject_private_fields(value: Mapping[str, object], path: str = "") -> None:
    for key, item in value.items():
        field = f"{path}{key}"
        if _privacy_key(key):
            raise ProvenanceError(f"comparison fingerprint must exclude private field {field}")
        if isinstance(item, Mapping):
            _reject_private_fields(item, f"{field}.")


def _toolchains() -> dict[str, object]:
    tools: dict[str, object] = {"python": platform.python_version()}
    for name, command in (
        ("rustc", ("rustc", "--version")),
        ("cargo", ("cargo", "--version")),
        ("uv", ("uv", "--version")),
    ):
        _add_if_present(tools, name, _command_version(command))
    return tools


def _virtualization() -> str | None:
    if sys.platform.startswith("linux"):
        value = _command_output(("systemd-detect-virt", "--vm"))
        if value is not None:
            return "none" if value == "none" else value
    if sys.platform == "darwin":
        value = _integer_command(("sysctl", "-n", "kern.hv_vmm_present"))
        if value is not None:
            return "vm" if value else "none"
    return None


def _macos_os() -> dict[str, object]:
    os_values: dict[str, object] = {"product": "macos"}
    for key, command in (
        ("release", ("sw_vers", "-productVersion")),
        ("build", ("sw_vers", "-buildVersion")),
    ):
        _add_if_present(os_values, key, _command_output(command))
    return os_values


def _generic_os() -> dict[str, object]:
    values: dict[str, object] = {"product": platform.system().lower()}
    _add_if_present(values, "release", platform.release() or None)
    _add_if_present(values, "build", platform.version() or None)
    return values


def _macos_display_model(display: Mapping[str, object]) -> str | None:
    display_type = display.get("spdisplays_display_type")
    if isinstance(display_type, str) and display_type.startswith(_DISPLAY_TYPE_PREFIX):
        words = display_type.removeprefix(_DISPLAY_TYPE_PREFIX).split("-")
        model = " ".join(
            word.upper() if word in _DISPLAY_ACRONYMS else word.title() for word in words
        )
        return f"{model} Display"
    fallback_model = display.get("_name") or display.get("_spdisplays_display-product-name")
    return fallback_model if isinstance(fallback_model, str) and fallback_model else None


def _macos_display_and_gpu() -> tuple[dict[str, object], dict[str, object]]:
    output = _command_output(("system_profiler", "SPDisplaysDataType", "-json"))
    if output is None:
        return {}, {}
    try:
        raw = json.loads(output)
    except json.JSONDecodeError:
        return {}, {}
    devices = raw.get("SPDisplaysDataType")
    if not isinstance(devices, list):
        return {}, {}
    gpu: dict[str, object] = {}
    display_route: dict[str, object] = {}
    for device in devices:
        if not isinstance(device, Mapping):
            continue
        if not gpu:
            model = device.get("_name")
            if isinstance(model, str) and model:
                gpu["model"] = model
            cores = device.get("sppci_cores") or device.get("spdisplays_gpucores")
            if isinstance(cores, int):
                gpu["core_count"] = cores
            elif isinstance(cores, str) and cores.isdigit():
                gpu["core_count"] = int(cores)
            metal = (
                device.get("spdisplays_metal")
                or device.get("sppci_metal")
                or device.get("spdisplays_mtlgpufamilysupport")
            )
            if isinstance(metal, str):
                match = re.search(r"metal\s*(?P<version>\d+(?:\.\d+)*)?", metal, re.IGNORECASE)
                if match:
                    gpu["api"] = "metal"
                    _add_if_present(gpu, "api_version", match.group("version"))
        displays = device.get("spdisplays_ndrvs")
        if not isinstance(displays, list):
            continue
        for display in displays:
            if not isinstance(display, Mapping) or display.get("spdisplays_main") not in (
                "spdisplays_yes",
                "yes",
                True,
            ):
                continue
            connection = display.get("spdisplays_connection_type")
            is_builtin = display.get("spdisplays_builtin") in ("spdisplays_yes", "yes", True)
            if connection in ("spdisplays_internal", "internal", "built-in", "spdisplays_builtin"):
                is_builtin = True
            display_route["route"] = "built-in" if is_builtin else "external"
            model = _macos_display_model(display)
            if model is not None:
                display_route["model"] = model.removeprefix("Built-in ")
            resolution = (
                display.get("spdisplays_pixelresolution")
                or display.get("_spdisplays_resolution")
                or display.get("spdisplays_resolution")
            )
            if isinstance(resolution, str):
                dimensions = _DIMENSIONS.search(resolution)
                if dimensions:
                    display_route["resolution"] = {
                        "width": int(dimensions.group("width")),
                        "height": int(dimensions.group("height")),
                    }
            scale = display.get("spdisplays_scale")
            if isinstance(scale, int) and not isinstance(scale, bool):
                display_route["scale"] = scale
            return display_route, gpu
    return display_route, gpu


def _macos_mount_route() -> str | None:
    output = _command_output(("diskutil", "info", "-plist", "."))
    if output is None:
        return None
    try:
        info = plistlib.loads(output.encode())
    except (plistlib.InvalidFileException, ValueError):
        return None
    route = info.get("VirtualOrPhysical") if isinstance(info, dict) else None
    if isinstance(route, str) and route.lower() in {"physical", "virtual"}:
        return route.lower()
    return None


def _macos_storage() -> dict[str, object]:
    storage: dict[str, object] = {}
    _add_if_present(storage, "filesystem", _command_output(("stat", "-f", "%T", ".")))
    _add_if_present(storage, "mount_route", _macos_mount_route())
    cache_directory = _command_output(("uv", "cache", "dir"))
    if cache_directory is not None:
        storage["cache_route"] = "configured" if "UV_CACHE_DIR" in os.environ else "uv-default"
    return storage


def _linux_mount_route() -> str | None:
    source = _command_output(("findmnt", "-no", "SOURCE", "--target", "."))
    if source is None:
        return None
    if source == "overlay":
        return "container-overlay"
    if source.startswith("/dev/"):
        return "block-device"
    if source.startswith("//") or "://" in source:
        return "network"
    return None


def _linux_storage() -> dict[str, object]:
    storage: dict[str, object] = {}
    _add_if_present(storage, "filesystem", _command_output(("stat", "-f", "-c", "%T", ".")))
    _add_if_present(storage, "mount_route", _linux_mount_route())
    cache_directory = _command_output(("uv", "cache", "dir"))
    if cache_directory is not None:
        storage["cache_route"] = "configured" if "UV_CACHE_DIR" in os.environ else "uv-default"
    return storage


def _storage() -> dict[str, object]:
    if sys.platform == "darwin":
        return _macos_storage()
    if sys.platform.startswith("linux"):
        return _linux_storage()
    return {}


def _machine_facts() -> dict[str, object]:
    process_architecture = normalize_architecture(platform.machine())
    hardware_architecture = process_architecture
    cpu: dict[str, object] = {}
    memory: dict[str, object] = {}
    hardware_model: str | None = None
    if sys.platform == "darwin":
        hardware = _command_output(("sysctl", "-n", "hw.machine"))
        if hardware:
            hardware_architecture = normalize_architecture(hardware)
        hardware_model = _command_output(("sysctl", "-n", "hw.model"))
        _add_if_present(cpu, "model", _command_output(("sysctl", "-n", "machdep.cpu.brand_string")))
        topology: dict[str, object] = {}
        _add_if_present(
            topology, "logical_cores", _integer_command(("sysctl", "-n", "hw.logicalcpu"))
        )
        _add_if_present(
            topology, "physical_cores", _integer_command(("sysctl", "-n", "hw.physicalcpu"))
        )
        if topology:
            cpu["topology"] = topology
        total_memory = _integer_command(("sysctl", "-n", "hw.memsize"))
    else:
        count = os.cpu_count()
        if count is not None:
            cpu["topology"] = {"logical_cores": count}
        total_memory = _memory_bytes()
    if total_memory is not None:
        memory = {"total_bytes": total_memory, "gib_class": _gib_class(total_memory)}
    facts: dict[str, object] = {
        "architecture": hardware_architecture,
        "hardware_architecture": hardware_architecture,
        "process_architecture": process_architecture,
        "cpu": cpu,
        "memory": memory,
    }
    if sys.platform == "darwin" and hardware_model is not None:
        facts["hardware_model"] = hardware_model
    return facts


def _memory_bytes() -> int | None:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None
    if (
        isinstance(page_size, int)
        and isinstance(page_count, int)
        and page_size > 0
        and page_count > 0
    ):
        return page_size * page_count
    return None


def _merge(
    detected: Mapping[str, object], supplied: Mapping[str, object] | None
) -> dict[str, object]:
    merged = dict(detected)
    if supplied:
        merged.update(supplied)
    return merged


def probe_machine(
    *,
    runtime_route: str,
    build_settings: Mapping[str, object],
    gpu: Mapping[str, object] | None = None,
    display_route: Mapping[str, object] | None = None,
    audio_route: Mapping[str, object] | None = None,
    storage_route: Mapping[str, object] | None = None,
) -> ComparisonFingerprint:
    """Create a stable fingerprint using only measured, non-private host facts.

    Unavailable facts are omitted. A runner profile can therefore fail explicitly on a
    required missing field instead of comparing a fabricated placeholder value.
    """

    facts = _machine_facts()
    detected_display: dict[str, object] = {}
    detected_gpu: dict[str, object] = {}
    if sys.platform == "darwin":
        detected_display, detected_gpu = _macos_display_and_gpu()
    stable: dict[str, object] = {
        **facts,
        "os": _macos_os() if sys.platform == "darwin" else _generic_os(),
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "toolchain": _toolchains(),
        "runtime_route": runtime_route,
        "build_settings": dict(build_settings),
        "gpu": _merge(detected_gpu, gpu),
        "display_route": _merge(detected_display, display_route),
        "audio_route": dict(audio_route or {}),
        "storage_route": _merge(_storage(), storage_route),
    }
    virtualization = _virtualization()
    if virtualization is not None:
        stable["virtualization"] = virtualization
    _reject_private_fields(stable)
    return ComparisonFingerprint(stable)
