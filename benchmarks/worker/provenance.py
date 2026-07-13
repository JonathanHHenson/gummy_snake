"""Release build planning and privacy-preserving cross-platform machine probing."""

from __future__ import annotations

import json
import os
import platform
import plistlib
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..schema.records import ComparisonFingerprint


class ProvenanceError(RuntimeError):
    """Release provenance cannot be planned or normalized safely."""


_ARCH_ALIASES = {
    "amd64": "x86_64",
    "x64": "x86_64",
    "x86-64": "x86_64",
    "x86_64h": "x86_64",
    "i386": "x86_32",
    "i486": "x86_32",
    "i586": "x86_32",
    "i686": "x86_32",
    "x86": "x86_32",
    "aarch64": "arm64",
    "arm64e": "arm64",
    "armv8": "arm64",
    "armv8l": "arm64",
    "ppc64le": "powerpc64le",
    "riscv64gc": "riscv64",
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
        "user",
        "username",
        "home",
        "path",
        "mountpoint",
        "address",
        "ip",
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
    profile: str = "release"
    features: tuple[str, ...] = ("extension-module",)
    target: str | None = None
    deployment_target: str | None = None
    environment: Mapping[str, str] = field(default_factory=dict)
    source_import_forbidden: bool = True

    def __post_init__(self) -> None:
        if not self.command or self.command[0] != "uv":
            raise ProvenanceError("authoritative release plans must use uv")
        if self.profile != "release" or not self.features:
            raise ProvenanceError(
                "authoritative builds require a release profile and explicit features"
            )

    @property
    def interpreter(self) -> Path:
        if os.name == "nt":
            return self.isolated_environment / "Scripts" / "python.exe"
        return self.isolated_environment / "bin" / "python"


def _rust_host_target() -> str | None:
    output = _command_output(("rustc", "-vV"))
    if output is None:
        return None
    for line in output.splitlines():
        if line.startswith("host: "):
            return line.removeprefix("host: ").strip() or None
    return None


def release_build_plan(repository: Path, output_directory: Path) -> ReleaseBuildPlan:
    """Plan an isolated release wheel whose source is the materialized repository tree."""

    repository = repository.resolve()
    output_directory = output_directory.resolve()
    try:
        with (repository / "pyproject.toml").open("rb") as source:
            pyproject = tomllib.load(source)
        tool = pyproject.get("tool")
        maturin = tool.get("maturin") if isinstance(tool, Mapping) else None
        configured_features = maturin.get("features") if isinstance(maturin, Mapping) else None
        if (
            not isinstance(configured_features, list)
            or not configured_features
            or not all(isinstance(feature, str) and feature for feature in configured_features)
        ):
            raise ProvenanceError("materialized Maturin build must declare non-empty features")
        features = tuple(str(feature) for feature in configured_features)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ProvenanceError(
            f"cannot read materialized release build configuration: {error}"
        ) from error
    deployment_target = os.environ.get("MACOSX_DEPLOYMENT_TARGET")
    if deployment_target is None and sys.platform == "darwin":
        try:
            with (repository / ".cargo" / "config.toml").open("rb") as source:
                cargo_config = tomllib.load(source)
            cargo_environment = cargo_config.get("env")
            configured_target = (
                cargo_environment.get("MACOSX_DEPLOYMENT_TARGET")
                if isinstance(cargo_environment, Mapping)
                else None
            )
            if isinstance(configured_target, Mapping):
                value = configured_target.get("value")
                deployment_target = value if isinstance(value, str) else None
            elif isinstance(configured_target, str):
                deployment_target = configured_target
        except (OSError, tomllib.TOMLDecodeError):
            deployment_target = None
    environment = {
        "CARGO_TARGET_DIR": str(output_directory.parent / "cargo-target"),
        "PYO3_PYTHON": sys.executable,
    }
    if deployment_target:
        environment["MACOSX_DEPLOYMENT_TARGET"] = deployment_target
    return ReleaseBuildPlan(
        repository=repository,
        output_directory=output_directory,
        command=("uv", "build", "--wheel", "--out-dir", str(output_directory)),
        isolated_environment=output_directory.parent / "venv",
        features=features,
        target=_rust_host_target(),
        deployment_target=deployment_target,
        environment=environment,
    )


def release_build_provenance(plan: ReleaseBuildPlan) -> dict[str, object]:
    """Record stable compiler inputs for the release artifact without source identity."""

    compiler: dict[str, object] = {}
    _add_if_present(compiler, "rustc", _command_version(("rustc", "--version")))
    _add_if_present(compiler, "cargo", _command_version(("cargo", "--version")))
    _add_if_present(compiler, "maturin", _command_version(("maturin", "--version")))
    _add_if_present(compiler, "uv", _command_version(("uv", "--version")))
    values: dict[str, object] = {
        "profile": plan.profile,
        "features": list(plan.features),
        "compiler": compiler,
        "source_import_forbidden": plan.source_import_forbidden,
    }
    _add_if_present(values, "target", plan.target)
    _add_if_present(values, "deployment_target", plan.deployment_target)
    return values


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
        value = _command_output(("systemd-detect-virt",))
        if value is not None:
            return "none" if value == "none" else value.lower()
    if sys.platform == "darwin":
        value = _integer_command(("sysctl", "-n", "kern.hv_vmm_present"))
        if value is not None:
            return "vm" if value else "none"
    if sys.platform == "win32":
        output = _command_output(
            (
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem | Select-Object -First 1 "
                "Manufacturer,Model | ConvertTo-Json -Compress)",
            )
        )
        if output is None:
            return None
        parsed = _json_mapping(output)
        manufacturer = str(parsed.get("Manufacturer", "")).lower()
        model = str(parsed.get("Model", "")).lower()
        markers = ("virtual", "vmware", "parallels", "kvm", "hyper-v", "virtualbox")
        return (
            "vm" if any(marker in manufacturer or marker in model for marker in markers) else "none"
        )
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
    product = platform.system().lower()
    values: dict[str, object] = {"product": product}
    if sys.platform.startswith("linux"):
        try:
            release = platform.freedesktop_os_release()
        except OSError:
            release = {}
        _add_if_present(values, "distribution", release.get("ID"))
        _add_if_present(values, "distribution_version", release.get("VERSION_ID"))
        _add_if_present(values, "release", platform.release() or None)
    elif sys.platform == "win32":
        windows_release, version, service_pack, _ptype = platform.win32_ver()
        _add_if_present(values, "release", windows_release or None)
        _add_if_present(values, "version", version or None)
        _add_if_present(values, "service_pack", service_pack or None)
    else:
        _add_if_present(values, "release", platform.release() or None)
        _add_if_present(values, "version", platform.version() or None)
    return values


def _json_mapping(output: str | None) -> Mapping[str, object]:
    if output is None:
        return {}
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, Mapping) else {}


def _json_items(output: str | None, key: str | None = None) -> tuple[Mapping[str, object], ...]:
    if output is None:
        return ()
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return ()
    if key is not None and isinstance(value, Mapping):
        value = value.get(key)
    if isinstance(value, Mapping):
        return (value,)
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


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
    devices = _json_items(
        _command_output(("system_profiler", "SPNVMeDataType", "-json")), "SPNVMeDataType"
    )
    if devices:
        device = devices[0]
        _add_if_present(storage, "model", device.get("_name"))
        storage["hardware_class"] = "solid-state"
        storage["transport"] = "nvme"
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
    devices = _json_items(
        _command_output(("lsblk", "--json", "--nodeps", "-o", "TYPE,ROTA,MODEL,TRAN")),
        "blockdevices",
    )
    disks = [item for item in devices if item.get("type") == "disk"]
    if disks:
        device = disks[0]
        _add_if_present(storage, "model", device.get("model"))
        _add_if_present(storage, "transport", device.get("tran"))
        rotational = device.get("rota")
        if rotational in (False, 0, "0"):
            storage["hardware_class"] = "solid-state"
        elif rotational in (True, 1, "1"):
            storage["hardware_class"] = "rotational"
    cache_directory = _command_output(("uv", "cache", "dir"))
    if cache_directory is not None:
        storage["cache_route"] = "configured" if "UV_CACHE_DIR" in os.environ else "uv-default"
    return storage


def _windows_storage() -> dict[str, object]:
    storage: dict[str, object] = {}
    output = _command_output(
        (
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-PhysicalDisk | Select-Object -First 1 FriendlyName,MediaType,BusType "
            "| ConvertTo-Json -Compress)",
        )
    )
    device = _json_mapping(output)
    _add_if_present(storage, "model", device.get("FriendlyName"))
    media_type = device.get("MediaType")
    if isinstance(media_type, str) and media_type:
        storage["hardware_class"] = media_type.lower().replace(" ", "-")
    bus_type = device.get("BusType")
    if isinstance(bus_type, str) and bus_type:
        storage["transport"] = bus_type.lower()
    filesystem = _command_output(
        (
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Volume | Where-Object DriveLetter -eq (Get-Location).Drive.Name "
            "| Select-Object -ExpandProperty FileSystem)",
        )
    )
    _add_if_present(storage, "filesystem", filesystem.lower() if filesystem else None)
    if filesystem:
        storage["mount_route"] = "local-volume"
    if _command_output(("uv", "cache", "dir")) is not None:
        storage["cache_route"] = "configured" if "UV_CACHE_DIR" in os.environ else "uv-default"
    return storage


def _storage() -> dict[str, object]:
    if sys.platform == "darwin":
        return _macos_storage()
    if sys.platform.startswith("linux"):
        return _linux_storage()
    if sys.platform == "win32":
        return _windows_storage()
    return {}


def _linux_cpu() -> dict[str, object]:
    cpu: dict[str, object] = {}
    output = _command_output(("lscpu", "--json"))
    rows = _json_items(output, "lscpu")
    values = {
        str(row.get("field", "")).rstrip(":"): row.get("data")
        for row in rows
        if isinstance(row.get("field"), str)
    }
    model = values.get("Model name")
    if isinstance(model, str) and model.strip():
        cpu["model"] = " ".join(model.split())
    topology: dict[str, object] = {}
    logical = values.get("CPU(s)")
    cores = values.get("Core(s) per socket")
    sockets = values.get("Socket(s)")
    if isinstance(logical, str) and logical.isdigit():
        topology["logical_cores"] = int(logical)
    if all(isinstance(value, str) and value.isdigit() for value in (cores, sockets)):
        topology["physical_cores"] = int(str(cores)) * int(str(sockets))
    if topology:
        cpu["topology"] = topology
    return cpu


def _windows_machine() -> tuple[dict[str, object], int | None]:
    output = _command_output(
        (
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_Processor | Select-Object -First 1 "
            "Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress)",
        )
    )
    processor = _json_mapping(output)
    cpu: dict[str, object] = {}
    _add_if_present(cpu, "model", processor.get("Name"))
    topology: dict[str, object] = {}
    for source, target in (
        ("NumberOfCores", "physical_cores"),
        ("NumberOfLogicalProcessors", "logical_cores"),
    ):
        value = processor.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            topology[target] = value
    if topology:
        cpu["topology"] = topology
    memory_output = _command_output(
        (
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_ComputerSystem | "
            "Select-Object -ExpandProperty TotalPhysicalMemory)",
        )
    )
    try:
        total_memory = int(memory_output) if memory_output is not None else None
    except ValueError:
        total_memory = None
    return cpu, total_memory


def _machine_facts() -> dict[str, object]:
    process_architecture = normalize_architecture(platform.machine())
    hardware_architecture = process_architecture
    cpu: dict[str, object] = {}
    memory: dict[str, object] = {}
    hardware_model: str | None = None
    translation: str | None = None
    if sys.platform == "darwin":
        hardware = _command_output(("sysctl", "-n", "hw.machine"))
        if hardware:
            hardware_architecture = normalize_architecture(hardware)
        translated = _integer_command(("sysctl", "-in", "sysctl.proc_translated"))
        arm_capable = _integer_command(("sysctl", "-n", "hw.optional.arm64"))
        if translated == 1:
            translation = "rosetta2"
            if arm_capable == 1:
                hardware_architecture = "arm64"
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
    elif sys.platform.startswith("linux"):
        cpu = _linux_cpu()
        if not cpu and os.cpu_count() is not None:
            cpu["topology"] = {"logical_cores": os.cpu_count()}
        total_memory = _memory_bytes()
    elif sys.platform == "win32":
        native = os.environ.get("PROCESSOR_ARCHITEW6432")
        if native:
            hardware_architecture = normalize_architecture(native)
        cpu, total_memory = _windows_machine()
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
    if hardware_model is not None:
        facts["hardware_model"] = hardware_model
    if translation is not None:
        facts["process_translation"] = translation
    return facts


def _linux_display_and_gpu() -> tuple[dict[str, object], dict[str, object]]:
    display: dict[str, object] = {}
    gpu: dict[str, object] = {}
    session = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if session in {"wayland", "x11"}:
        display["session"] = session
    output = _command_output(("lspci", "-mm"))
    if output:
        for line in output.splitlines():
            if any(
                marker in line.lower() for marker in ("vga compatible", "3d controller", "display")
            ):
                quoted = re.findall(r'"([^"]+)"', line)
                if quoted:
                    gpu["model"] = " ".join(quoted[-2:]) if len(quoted) > 1 else quoted[0]
                break
    details = _command_output(("lspci", "-k"))
    if details:
        gpu_section = False
        for line in details.splitlines():
            lowered = line.lower()
            if line and not line[0].isspace():
                gpu_section = any(
                    marker in lowered for marker in ("vga compatible", "3d controller", "display")
                )
            elif gpu_section and "kernel driver in use:" in lowered:
                gpu["driver"] = line.split(":", 1)[1].strip()
                break
    vulkan = _command_output(("vulkaninfo", "--summary"))
    if vulkan:
        match = re.search(r"Vulkan Instance Version:\s*([0-9.]+)", vulkan)
        if match:
            gpu["api"] = "vulkan"
            gpu["api_version"] = match.group(1)
    resolution = _command_output(("xrandr", "--current")) if session == "x11" else None
    if resolution:
        match = re.search(r"current\s+(\d+)\s+x\s+(\d+)", resolution)
        if match:
            display["resolution"] = {"width": int(match.group(1)), "height": int(match.group(2))}
    return display, gpu


def _windows_display_and_gpu() -> tuple[dict[str, object], dict[str, object]]:
    display: dict[str, object] = {}
    session = os.environ.get("SESSIONNAME", "").lower()
    if session == "console":
        display["session"] = "desktop"
    elif session.startswith("rdp"):
        display["session"] = "remote-desktop"
    gpu: dict[str, object] = {}
    output = _command_output(
        (
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_VideoController | Select-Object -First 1 "
            "Name,DriverVersion,CurrentHorizontalResolution,CurrentVerticalResolution "
            "| ConvertTo-Json -Compress)",
        )
    )
    controller = _json_mapping(output)
    _add_if_present(gpu, "model", controller.get("Name"))
    _add_if_present(gpu, "driver", controller.get("DriverVersion"))
    if gpu:
        gpu["api"] = "direct3d"
    width = controller.get("CurrentHorizontalResolution")
    height = controller.get("CurrentVerticalResolution")
    if all(isinstance(value, int) and not isinstance(value, bool) for value in (width, height)):
        display["resolution"] = {"width": width, "height": height}
    return display, gpu


def _macos_audio() -> dict[str, object]:
    devices = _json_items(
        _command_output(("system_profiler", "SPAudioDataType", "-json")), "SPAudioDataType"
    )
    for group in devices:
        raw_devices = group.get("_items")
        if not isinstance(raw_devices, list):
            continue
        for device in raw_devices:
            if not isinstance(device, Mapping):
                continue
            default = device.get("coreaudio_default_audio_output_device")
            if default not in ("spaudio_yes", "yes", True):
                continue
            route: dict[str, object] = {}
            _add_if_present(route, "model", device.get("_name"))
            transport = device.get("coreaudio_transport")
            if isinstance(transport, str):
                route["transport"] = transport.lower()
            return route
    return {}


def _linux_audio() -> dict[str, object]:
    route: dict[str, object] = {}
    output = _command_output(("pactl", "info"))
    if output:
        for line in output.splitlines():
            if line.lower().startswith("server name:"):
                server = line.split(":", 1)[1].strip().lower()
                route["server"] = "pipewire" if "pipewire" in server else "pulseaudio"
                break
    return route


def _windows_audio() -> dict[str, object]:
    route: dict[str, object] = {}
    output = _command_output(
        (
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_SoundDevice | Where-Object Status -eq 'OK' "
            "| Select-Object -First 1 Name,Manufacturer | ConvertTo-Json -Compress)",
        )
    )
    device = _json_mapping(output)
    _add_if_present(route, "model", device.get("Name"))
    _add_if_present(route, "manufacturer", device.get("Manufacturer"))
    return route


def _audio() -> dict[str, object]:
    if sys.platform == "darwin":
        return _macos_audio()
    if sys.platform.startswith("linux"):
        return _linux_audio()
    if sys.platform == "win32":
        return _windows_audio()
    return {}


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


def probe_run_conditions() -> dict[str, object]:
    """Collect bounded execution-route conditions without identity or live telemetry."""

    conditions: dict[str, object] = {
        "ci": any(os.environ.get(name) for name in ("CI", "GITHUB_ACTIONS", "BUILD_BUILDID")),
    }
    virtualization = _virtualization()
    if virtualization is not None:
        conditions["virtualization"] = virtualization
    if sys.platform == "darwin":
        power = _command_output(("pmset", "-g", "batt"))
        if power:
            conditions["power_source"] = "ac" if "AC Power" in power else "battery"
    elif sys.platform.startswith("linux"):
        power = _command_output(("cat", "/sys/class/power_supply/AC/online"))
        if power in {"0", "1"}:
            conditions["power_source"] = "ac" if power == "1" else "battery"
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session in {"wayland", "x11", "tty"}:
            conditions["display_session"] = session
    elif sys.platform == "win32":
        power = _command_output(
            (
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Battery | Select-Object -First 1 "
                "-ExpandProperty BatteryStatus)",
            )
        )
        if power is not None:
            conditions["power_source"] = "battery-present"
        session = os.environ.get("SESSIONNAME", "").lower()
        if session == "console":
            conditions["display_session"] = "desktop"
        elif session.startswith("rdp"):
            conditions["display_session"] = "remote-desktop"
    _reject_private_fields(conditions)
    return conditions


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
    elif sys.platform.startswith("linux"):
        detected_display, detected_gpu = _linux_display_and_gpu()
    elif sys.platform == "win32":
        detected_display, detected_gpu = _windows_display_and_gpu()
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
        "audio_route": _merge(_audio(), audio_route),
        "storage_route": _merge(_storage(), storage_route),
    }
    virtualization = _virtualization()
    if virtualization is not None:
        stable["virtualization"] = virtualization
    _reject_private_fields(stable)
    return ComparisonFingerprint(stable)
