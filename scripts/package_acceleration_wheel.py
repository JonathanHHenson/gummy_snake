#!/usr/bin/env python3
"""Add PEP 561 marker and native acceleration stub to a built gummy_accel wheel.

``gummy_accel`` is a separately built optional extension. Maturin builds its
minimal extension wheel from its Cargo manifest, while the canonical Python
sources and ``_accelerated.pyi`` live in the main package tree. This script
makes that supplemental wheel carry the same typed native interface without
copying or rebuilding runtime code.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

PACKAGE_PATHS = {
    PurePosixPath("gummysnake/py.typed"): Path("src/gummysnake/py.typed"),
    PurePosixPath("gummysnake/rust/_accelerated.pyi"): Path("src/gummysnake/rust/_accelerated.pyi"),
}
RECORD_SUFFIX = ".dist-info/RECORD"


class AccelerationWheelError(RuntimeError):
    """Raised when a wheel cannot be prepared as a typed acceleration wheel."""


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the wheel path and optional project root."""

    parser = argparse.ArgumentParser(
        description="Add gummysnake native type-interface files to an acceleration wheel."
    )
    parser.add_argument("wheel", type=Path, help="Built gummy_accel wheel to update in place.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root containing the canonical native stub (default: repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Prepare a wheel in place and report actionable errors."""

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        package_acceleration_wheel(args.wheel, args.root)
    except (AccelerationWheelError, OSError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Prepared typed acceleration wheel: {args.wheel}")
    return 0


def package_acceleration_wheel(wheel_path: Path, project_root: Path) -> None:
    """Rewrite *wheel_path* with the marker/stub and an accurate ``RECORD``."""

    wheel = wheel_path.resolve()
    root = project_root.resolve()
    if not wheel.is_file():
        raise AccelerationWheelError(f"Wheel does not exist: {wheel}")
    additions = _canonical_package_files(root)

    with zipfile.ZipFile(wheel) as archive:
        contents = {
            PurePosixPath(info.filename): archive.read(info.filename)
            for info in archive.infolist()
            if not info.is_dir() and not info.filename.endswith(RECORD_SUFFIX)
        }
    if not any(
        path.name.startswith("_accelerated.") and path.suffix in {".so", ".pyd", ".dylib"}
        for path in contents
    ):
        raise AccelerationWheelError(
            "Wheel is missing the native gummysnake.rust._accelerated extension"
        )

    contents.update(additions)
    record_path = _record_path(contents)
    contents[record_path] = _record_contents(contents, record_path)

    with tempfile.NamedTemporaryFile(
        prefix=f"{wheel.stem}-", suffix=".whl", dir=wheel.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, content in sorted(contents.items(), key=lambda item: item[0].as_posix()):
                archive.writestr(path.as_posix(), content)
        temporary_path.replace(wheel)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _canonical_package_files(project_root: Path) -> dict[PurePosixPath, bytes]:
    files: dict[PurePosixPath, bytes] = {}
    for wheel_path, source_path in PACKAGE_PATHS.items():
        source = project_root / source_path
        if not source.is_file():
            raise AccelerationWheelError(f"Missing canonical package file: {source_path}")
        files[wheel_path] = source.read_bytes()
    return files


def _record_path(contents: dict[PurePosixPath, bytes]) -> PurePosixPath:
    record_paths = [path for path in contents if path.as_posix().endswith(".dist-info/WHEEL")]
    if len(record_paths) != 1:
        raise AccelerationWheelError("Could not identify one .dist-info/WHEEL member")
    return record_paths[0].parent / "RECORD"


def _record_contents(contents: dict[PurePosixPath, bytes], record_path: PurePosixPath) -> bytes:
    rows = []
    for path, content in sorted(contents.items(), key=lambda item: item[0].as_posix()):
        digest = (
            base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
        )
        rows.append(f"{path.as_posix()},sha256={digest},{len(content)}")
    rows.append(f"{record_path.as_posix()},,")
    return ("\n".join(rows) + "\n").encode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
