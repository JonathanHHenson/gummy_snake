from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "package_acceleration_wheel.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("package_acceleration_wheel", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_extension_wheel(path: Path, *, include_extension: bool = True) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        if include_extension:
            archive.writestr("gummysnake/rust/_accelerated.cpython-312.so", "native")
        archive.writestr("gummy_accel-0.1.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")
        archive.writestr("gummy_accel-0.1.0.dist-info/RECORD", "stale\n")


def test_package_acceleration_wheel_adds_typed_native_interface_and_updates_record(
    tmp_path: Path,
) -> None:
    module = load_module()
    wheel = tmp_path / "gummy_accel-0.1.0.whl"
    build_extension_wheel(wheel)

    module.package_acceleration_wheel(wheel, ROOT)

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert "gummysnake/py.typed" in names
        assert "gummysnake/rust/_accelerated.pyi" in names
        record = archive.read("gummy_accel-0.1.0.dist-info/RECORD").decode("utf-8")

    assert "gummysnake/py.typed,sha256=" in record
    assert "gummysnake/rust/_accelerated.pyi,sha256=" in record
    assert record.endswith("gummy_accel-0.1.0.dist-info/RECORD,,\n")


def test_package_acceleration_wheel_rejects_archive_without_native_extension(
    tmp_path: Path,
) -> None:
    module = load_module()
    wheel = tmp_path / "gummy_accel-0.1.0.whl"
    build_extension_wheel(wheel, include_extension=False)

    with pytest.raises(module.AccelerationWheelError, match="native gummysnake.rust._accelerated"):
        module.package_acceleration_wheel(wheel, ROOT)
