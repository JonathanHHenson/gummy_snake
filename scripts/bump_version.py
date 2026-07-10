#!/usr/bin/env python3
"""Bump Gummy Snake package versions in one place.

Updates the root Python package version, Rust crate versions, and the editable
package version recorded in uv.lock. Use an exact semantic version or one of
``major``, ``minor``, or ``patch`` to bump relative to the root project version.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PYPROJECT = Path("pyproject.toml")
CARGO_WORKSPACE = Path("Cargo.toml")
CARGO_MANIFEST = Path("Cargo.toml")
UV_LOCK = Path("uv.lock")
VERSION_PARTS = {"major", "minor", "patch"}
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
VERSION_LINE_RE = re.compile(r'(?m)^(version\s*=\s*")([^"\n]+)(")')
UV_PACKAGE_RE = re.compile(
    r'(?ms)^(\[\[package\]\]\s*\nname\s*=\s*"gummy-snake"\s*\nversion\s*=\s*")([^"\n]+)(")'
)


@dataclass(frozen=True)
class VersionFile:
    path: Path
    current: str
    updated: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bump Gummy Snake versions across pyproject.toml, Rust crates, and uv.lock. "
            "TARGET may be an exact X.Y.Z version or one of: major, minor, patch."
        )
    )
    parser.add_argument("target", nargs="?", help="Exact X.Y.Z version or major/minor/patch.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify that managed version files are already in sync.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()

    managed = read_versions(root)
    current_versions = {item.current for item in managed}

    if args.check:
        if len(current_versions) == 1:
            version = next(iter(current_versions))
            print(f"Managed versions are in sync at {version}.")
            return 0
        print("Managed versions are not in sync:", file=sys.stderr)
        for item in managed:
            print(f"  {item.path}: {item.current}", file=sys.stderr)
        return 1

    if args.target is None:
        print("error: TARGET is required unless --check is used", file=sys.stderr)
        return 2

    root_version = version_for_file(managed, PYPROJECT)
    next_version = resolve_target(args.target, root_version)

    planned = [VersionFile(item.path, item.current, next_version) for item in managed]
    changed = [item for item in planned if item.current != item.updated]

    if not changed:
        print(f"All managed versions are already {next_version}.")
        return 0

    for item in changed:
        print(f"{item.path}: {item.current} -> {item.updated}")

    if args.dry_run:
        return 0

    write_versions(root, next_version)
    print("Version bump complete.")
    return 0


def read_versions(root: Path) -> list[VersionFile]:
    versions = [_read_toml_version(root, path) for path in managed_toml_files(root)]
    lock_path = root / UV_LOCK
    if lock_path.exists():
        versions.append(_read_uv_lock_version(root))
    return versions


def managed_toml_files(root: Path) -> tuple[Path, ...]:
    """Return the Python project manifest and Cargo workspace member manifests."""
    return (PYPROJECT, *workspace_member_manifests(root))


def workspace_member_manifests(root: Path) -> tuple[Path, ...]:
    """Read Rust crate manifests from explicit root Cargo workspace members."""
    workspace_path = root / CARGO_WORKSPACE
    try:
        workspace_data = tomllib.loads(workspace_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError(f"Could not read Cargo workspace manifest: {CARGO_WORKSPACE}") from error

    workspace = workspace_data.get("workspace")
    if not isinstance(workspace, dict):
        raise RuntimeError(f"Could not find [workspace] in {CARGO_WORKSPACE}")
    members = workspace.get("members")
    if not isinstance(members, list) or not all(isinstance(member, str) for member in members):
        raise RuntimeError(f"Could not find workspace members in {CARGO_WORKSPACE}")

    manifests: list[Path] = []
    for member in members:
        member_path = Path(member)
        if member_path.is_absolute():
            raise RuntimeError(f"Workspace member must be relative to the project root: {member}")
        manifest = member_path / CARGO_MANIFEST
        if manifest not in manifests:
            manifests.append(manifest)
    return tuple(manifests)


def version_for_file(files: Iterable[VersionFile], path: Path) -> str:
    for item in files:
        if item.path == path:
            return item.current
    raise RuntimeError(f"Managed version file is missing: {path}")


def resolve_target(target: str, current: str) -> str:
    normalized = target.strip().lower()
    if normalized in VERSION_PARTS:
        major, minor, patch = parse_version(current)
        if normalized == "major":
            return f"{major + 1}.0.0"
        if normalized == "minor":
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}"
    validate_version(target)
    return target


def parse_version(version: str) -> tuple[int, int, int]:
    validate_version(version)
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def validate_version(version: str) -> None:
    if not VERSION_RE.fullmatch(version):
        raise SystemExit(f"error: expected semantic version X.Y.Z, got {version!r}")


def write_versions(root: Path, version: str) -> None:
    for path in managed_toml_files(root):
        _write_toml_version(root, path, version)
    lock_path = root / UV_LOCK
    if lock_path.exists():
        _write_uv_lock_version(root, version)


def _read_toml_version(root: Path, relative_path: Path) -> VersionFile:
    path = root / relative_path
    text = path.read_text(encoding="utf-8")
    match = VERSION_LINE_RE.search(text)
    if match is None:
        raise RuntimeError(f"Could not find version line in {relative_path}")
    return VersionFile(relative_path, match.group(2), match.group(2))


def _write_toml_version(root: Path, relative_path: Path, version: str) -> None:
    path = root / relative_path
    text = path.read_text(encoding="utf-8")
    updated, count = VERSION_LINE_RE.subn(rf"\g<1>{version}\g<3>", text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not update version line in {relative_path}")
    path.write_text(updated, encoding="utf-8")


def _read_uv_lock_version(root: Path) -> VersionFile:
    path = root / UV_LOCK
    text = path.read_text(encoding="utf-8")
    match = UV_PACKAGE_RE.search(text)
    if match is None:
        raise RuntimeError("Could not find gummy-snake package version in uv.lock")
    return VersionFile(UV_LOCK, match.group(2), match.group(2))


def _write_uv_lock_version(root: Path, version: str) -> None:
    path = root / UV_LOCK
    text = path.read_text(encoding="utf-8")
    updated, count = UV_PACKAGE_RE.subn(rf"\g<1>{version}\g<3>", text, count=1)
    if count != 1:
        raise RuntimeError("Could not update gummy-snake package version in uv.lock")
    path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
