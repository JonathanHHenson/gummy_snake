#!/usr/bin/env python3
"""Verify that a source distribution contains native build inputs and packaged assets.

The verifier compares an sdist against a checkout.  It follows local Cargo
``path`` dependencies from ``crates/gummy_canvas/Cargo.toml`` and checks every
file below each required crate's ``src`` directory, its ``Cargo.toml``, and any
present ``build.rs``.  It also expands the Maturin ``include`` globs in the
checkout's ``pyproject.toml``.  Missing paths are reported relative to the
project root, so the output is actionable regardless of the sdist's top-level
directory name.
"""

from __future__ import annotations

import argparse
import sys
import tarfile
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath

CANVAS_MANIFEST = Path("crates/gummy_canvas/Cargo.toml")
PYPROJECT = Path("pyproject.toml")
DEPENDENCY_SECTIONS = ("dependencies", "build-dependencies")


class DistributionConfigurationError(RuntimeError):
    """Raised when the checkout cannot provide an unambiguous verification plan."""


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments for sdist verification."""

    parser = argparse.ArgumentParser(
        description="Verify native Cargo sources and Maturin assets in an sdist tar.gz."
    )
    parser.add_argument("sdist", type=Path, help="Path to the source-distribution tar.gz file.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project checkout used to determine required files (default: repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run verification and return a process-compatible status code."""

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        missing = verify_distribution(args.sdist, args.root)
    except (DistributionConfigurationError, OSError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if missing:
        print("Source distribution is missing required paths:", file=sys.stderr)
        for path in missing:
            print(f"  {path.as_posix()}", file=sys.stderr)
        return 1

    print("Source distribution contains all required Cargo sources and Maturin assets.")
    return 0


def verify_distribution(sdist_path: Path, project_root: Path | None = None) -> tuple[Path, ...]:
    """Return exact project-relative paths required by *sdist_path* but absent from it.

    ``project_root`` is the checkout whose Cargo manifests and Maturin include
    entries define the expected contents.  It defaults to this repository's root
    so the function is also convenient for release automation.
    """

    root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    required = required_distribution_paths(root)
    archive_files, archive_root = sdist_file_paths(sdist_path)

    missing = [
        path for path in required if _archive_member_path(archive_root, path) not in archive_files
    ]
    return tuple(missing)


def required_distribution_paths(project_root: Path) -> tuple[Path, ...]:
    """Return all project-relative files that must be packaged in an sdist."""

    root = project_root.resolve()
    pyproject = root / PYPROJECT
    canvas_manifest = root / CANVAS_MANIFEST
    if not pyproject.is_file():
        raise DistributionConfigurationError(f"Missing project manifest: {PYPROJECT}")
    if not canvas_manifest.is_file():
        raise DistributionConfigurationError(f"Missing canvas Cargo manifest: {CANVAS_MANIFEST}")

    required: set[Path] = {PYPROJECT}
    for crate_directory in local_cargo_crates(canvas_manifest, root):
        required.add(_relative_to_root(crate_directory / "Cargo.toml", root))
        required.update(_crate_source_paths(crate_directory, root))
    required.update(maturin_include_paths(pyproject, root))
    return tuple(sorted(required, key=lambda path: path.as_posix()))


def local_cargo_crates(canvas_manifest: Path, project_root: Path) -> tuple[Path, ...]:
    """Return canvas and every recursive local Cargo path dependency directory."""

    root = project_root.resolve()
    pending = [canvas_manifest.resolve()]
    visited: set[Path] = set()
    crates: list[Path] = []

    while pending:
        manifest = pending.pop()
        crate_directory = manifest.parent
        if crate_directory in visited:
            continue
        if not manifest.is_file():
            relative = _relative_to_root(manifest, root)
            raise DistributionConfigurationError(f"Missing Cargo manifest: {relative}")

        visited.add(crate_directory)
        _relative_to_root(crate_directory, root)
        crates.append(crate_directory)
        for dependency_path in cargo_path_dependencies(manifest):
            dependency_manifest = (crate_directory / dependency_path / "Cargo.toml").resolve()
            _relative_to_root(dependency_manifest, root)
            pending.append(dependency_manifest)

    return tuple(sorted(crates, key=lambda path: _relative_to_root(path, root).as_posix()))


def cargo_path_dependencies(manifest_path: Path) -> tuple[Path, ...]:
    """Read local Cargo dependency paths from normal and build dependency tables."""

    manifest = _read_toml(manifest_path)
    paths: set[Path] = set()
    for dependencies in _dependency_tables(manifest):
        for specification in dependencies.values():
            if not isinstance(specification, Mapping):
                continue
            path = specification.get("path")
            if isinstance(path, str):
                dependency_path = Path(path)
                if dependency_path.is_absolute():
                    raise DistributionConfigurationError(
                        f"Cargo path dependencies must be relative: {manifest_path}: {path}"
                    )
                paths.add(dependency_path)
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def maturin_include_paths(pyproject_path: Path, project_root: Path) -> tuple[Path, ...]:
    """Expand the current ``tool.maturin.include`` patterns to packaged files."""

    document = _read_toml(pyproject_path)
    tool = document.get("tool")
    maturin = tool.get("maturin") if isinstance(tool, Mapping) else None
    includes = maturin.get("include") if isinstance(maturin, Mapping) else None
    if includes is None:
        return ()
    if not isinstance(includes, list) or not all(isinstance(pattern, str) for pattern in includes):
        raise DistributionConfigurationError("tool.maturin.include must be a list of path patterns")

    root = project_root.resolve()
    included: set[Path] = set()
    for pattern in includes:
        candidate_pattern = Path(pattern)
        if candidate_pattern.is_absolute() or ".." in candidate_pattern.parts:
            raise DistributionConfigurationError(
                f"Maturin include pattern must stay within the project root: {pattern}"
            )
        matches = tuple(path for path in root.glob(pattern) if path.is_file())
        if not matches:
            raise DistributionConfigurationError(
                f"Maturin include pattern did not match a file: {pattern}"
            )
        included.update(_relative_to_root(path, root) for path in matches)
    return tuple(sorted(included, key=lambda path: path.as_posix()))


def sdist_file_paths(sdist_path: Path) -> tuple[set[PurePosixPath], PurePosixPath]:
    """Return regular file paths and the detected top-level directory of an sdist."""

    with tarfile.open(sdist_path, "r:gz") as archive:
        files = {
            _normalise_archive_path(member.name)
            for member in archive.getmembers()
            if member.isfile()
        }

    pyproject_parents = {path.parent for path in files if path.name == PYPROJECT.name}
    if len(pyproject_parents) != 1:
        raise DistributionConfigurationError(
            "Could not identify one source-distribution root containing pyproject.toml"
        )
    return files, pyproject_parents.pop()


def _dependency_tables(document: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
    for section in DEPENDENCY_SECTIONS:
        dependencies = document.get(section)
        if isinstance(dependencies, Mapping):
            yield dependencies

    targets = document.get("target")
    if not isinstance(targets, Mapping):
        return
    for target in targets.values():
        if not isinstance(target, Mapping):
            continue
        for section in DEPENDENCY_SECTIONS:
            dependencies = target.get(section)
            if isinstance(dependencies, Mapping):
                yield dependencies


def _crate_source_paths(crate_directory: Path, project_root: Path) -> tuple[Path, ...]:
    source_directory = crate_directory / "src"
    source_paths = (
        (
            _relative_to_root(path, project_root)
            for path in source_directory.rglob("*")
            if path.is_file()
        )
        if source_directory.is_dir()
        else ()
    )
    build_script = crate_directory / "build.rs"
    if build_script.is_file():
        source_paths = (*source_paths, _relative_to_root(build_script, project_root))
    return tuple(sorted(set(source_paths), key=lambda path: path.as_posix()))


def _read_toml(path: Path) -> Mapping[str, object]:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DistributionConfigurationError(f"Could not read TOML manifest: {path}") from error
    if not isinstance(document, Mapping):
        raise DistributionConfigurationError(f"TOML manifest must contain a table: {path}")
    return document


def _relative_to_root(path: Path, project_root: Path) -> Path:
    try:
        return path.resolve().relative_to(project_root.resolve())
    except ValueError as error:
        raise DistributionConfigurationError(
            f"Required path is outside the project root: {path}"
        ) from error


def _normalise_archive_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise DistributionConfigurationError(f"Unsafe path in source distribution: {name}")
    return PurePosixPath(*(part for part in path.parts if part != "."))


def _archive_member_path(archive_root: PurePosixPath, path: Path) -> PurePosixPath:
    relative = PurePosixPath(path.as_posix())
    return relative if archive_root == PurePosixPath(".") else archive_root / relative


if __name__ == "__main__":
    raise SystemExit(main())
