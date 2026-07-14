#!/usr/bin/env python3
"""Validate the maintained source-to-test impact map.

The map is intentionally TOML rather than generated documentation: contributors can
review its ownership and validation choices directly, while this audit catches stale
paths, command references, empty check groups, missing category decisions, and new
unowned Python or Cargo workspace areas.
"""

from __future__ import annotations

import argparse
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MAP_PATH = Path("docs/contribute/source_test_impact_map.toml")
REQUIRED_CATEGORIES = frozenset(
    {
        "unit",
        "contract",
        "integration",
        "golden",
        "stress",
        "example",
        "documentation",
        "packaging",
    }
)
VALID_FOCUSES = frozenset({"behavior", "implementation"})
VALID_ROLES = frozenset(
    {
        "composition_root",
        "facade",
        "mandatory_rust_boundary",
        "udf_boundary",
        "implementation",
    }
)
REPOSITORY_PATH_PREFIXES = ("src/", "crates/", "tests/", "examples/", "docs/", "scripts/")


@dataclass(frozen=True, slots=True)
class ImpactMapViolation:
    """A deterministic audit finding suitable for terminal and test assertions."""

    code: str
    location: str
    message: str


def _expand_paths(repo_root: Path, patterns: list[str]) -> set[Path]:
    paths: set[Path] = set()
    for pattern in patterns:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            continue
        paths.update(path.resolve() for path in repo_root.glob(pattern))
    return paths


def _workspace_members(repo_root: Path) -> set[Path]:
    manifest = repo_root / "Cargo.toml"
    if not manifest.is_file():
        return set()
    try:
        workspace = tomllib.loads(manifest.read_text(encoding="utf-8")).get("workspace", {})
    except tomllib.TOMLDecodeError:
        return set()
    members = workspace.get("members", []) if isinstance(workspace, dict) else []
    if not isinstance(members, list):
        return set()
    discovered: set[Path] = set()
    for member in members:
        if isinstance(member, str):
            discovered.update(
                path.relative_to(repo_root) for path in repo_root.glob(member) if path.is_dir()
            )
    return discovered


def _command_path_tokens(command: str) -> list[str]:
    """Return repository-relative path tokens present in a shell command."""

    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    return [token for token in tokens if token.startswith(REPOSITORY_PATH_PREFIXES)]


def _as_string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return value


def audit(repo_root: Path = Path("."), map_path: Path | None = None) -> list[ImpactMapViolation]:
    """Return map violations without executing the referenced validation commands."""

    root = repo_root.resolve()
    path = (root / DEFAULT_MAP_PATH if map_path is None else map_path).resolve()
    if not path.is_file():
        return [
            ImpactMapViolation("missing_impact_map", str(path), "impact map TOML does not exist")
        ]

    try:
        document: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        return [ImpactMapViolation("invalid_impact_map", str(path), str(error))]

    violations: list[ImpactMapViolation] = []
    map_metadata = document.get("map")
    if not isinstance(map_metadata, dict):
        violations.append(ImpactMapViolation("missing_map_metadata", "map", "add a [map] table"))
    else:
        categories = set(_as_string_list(map_metadata.get("categories")) or [])
        if categories != REQUIRED_CATEGORIES:
            violations.append(
                ImpactMapViolation(
                    "invalid_categories",
                    "map.categories",
                    f"must declare exactly: {', '.join(sorted(REQUIRED_CATEGORIES))}",
                )
            )

    checks = document.get("checks")
    if not isinstance(checks, dict) or not checks:
        violations.append(
            ImpactMapViolation("missing_checks", "checks", "add named, non-empty checks")
        )
        checks = {}

    for check_name, raw_check in sorted(checks.items()):
        location = f"checks.{check_name}"
        if not isinstance(raw_check, dict):
            violations.append(
                ImpactMapViolation("invalid_check", location, "check must be a table")
            )
            continue
        paths = _as_string_list(raw_check.get("paths"))
        if not paths:
            violations.append(
                ImpactMapViolation(
                    "empty_check_paths", location, "check must own at least one path"
                )
            )
        else:
            for pattern in paths:
                if not _expand_paths(root, [pattern]):
                    violations.append(
                        ImpactMapViolation(
                            "stale_check_path", location, f"path `{pattern}` matches nothing"
                        )
                    )
        focus = raw_check.get("focus")
        if focus not in VALID_FOCUSES:
            violations.append(
                ImpactMapViolation(
                    "invalid_check_focus",
                    location,
                    "focus must be `behavior` or `implementation`",
                )
            )
        command = raw_check.get("command")
        if not isinstance(command, str) or not command.strip():
            violations.append(
                ImpactMapViolation(
                    "missing_check_command", location, "check must declare a command"
                )
            )
        elif not _command_path_tokens(command) and not command.startswith(
            ("uv build", "cargo test --workspace")
        ):
            violations.append(
                ImpactMapViolation(
                    "command_without_repository_path",
                    location,
                    "command must name a mapped repository path or be a package/workspace command",
                )
            )
        elif isinstance(command, str):
            for command_path in _command_path_tokens(command):
                if not _expand_paths(root, [command_path]):
                    violations.append(
                        ImpactMapViolation(
                            "stale_command_path",
                            location,
                            f"command path `{command_path}` matches nothing",
                        )
                    )

    areas = document.get("areas")
    if not isinstance(areas, dict) or not areas:
        violations.append(
            ImpactMapViolation("missing_areas", "areas", "add source ownership areas")
        )
        areas = {}

    owned_paths: set[Path] = set()
    declared_crates: set[Path] = set()
    for area_name, raw_area in sorted(areas.items()):
        location = f"areas.{area_name}"
        if not isinstance(raw_area, dict):
            violations.append(ImpactMapViolation("invalid_area", location, "area must be a table"))
            continue
        source = _as_string_list(raw_area.get("source"))
        if not source:
            violations.append(
                ImpactMapViolation("empty_area_source", location, "area must own source paths")
            )
        else:
            matches = _expand_paths(root, source)
            if not matches:
                violations.append(
                    ImpactMapViolation("stale_source_path", location, "source paths match nothing")
                )
            owned_paths.update(matches)
        roles = _as_string_list(raw_area.get("roles"))
        if not roles or not set(roles) <= VALID_ROLES:
            violations.append(
                ImpactMapViolation(
                    "invalid_area_roles",
                    location,
                    f"roles must be non-empty values from: {', '.join(sorted(VALID_ROLES))}",
                )
            )
        if not isinstance(raw_area.get("ownership"), str) or not raw_area["ownership"].strip():
            violations.append(
                ImpactMapViolation(
                    "missing_ownership", location, "add a concise ownership statement"
                )
            )
        crate = raw_area.get("crate")
        if crate is not None:
            if not isinstance(crate, str) or not (root / crate).is_dir():
                violations.append(
                    ImpactMapViolation(
                        "stale_crate", location, "crate must name an existing directory"
                    )
                )
            elif Path(crate) in declared_crates:
                violations.append(
                    ImpactMapViolation(
                        "duplicate_crate_owner", location, f"`{crate}` has multiple owners"
                    )
                )
            else:
                declared_crates.add(Path(crate))
        categories = raw_area.get("categories")
        if not isinstance(categories, dict):
            violations.append(
                ImpactMapViolation("missing_area_categories", location, "add a categories table")
            )
            continue
        category_names = set(categories)
        if category_names != REQUIRED_CATEGORIES:
            violations.append(
                ImpactMapViolation(
                    "incomplete_area_categories",
                    location,
                    f"must declare exactly: {', '.join(sorted(REQUIRED_CATEGORIES))}",
                )
            )
        for category, references in sorted(categories.items()):
            values = _as_string_list(references)
            category_location = f"{location}.categories.{category}"
            if not values:
                violations.append(
                    ImpactMapViolation(
                        "empty_category", category_location, "use a check name or `N/A: rationale`"
                    )
                )
                continue
            for reference in values:
                if reference.startswith("N/A:"):
                    if len(reference.removeprefix("N/A:").strip()) < 8:
                        violations.append(
                            ImpactMapViolation(
                                "short_na_rationale",
                                category_location,
                                "N/A entries need a short rationale",
                            )
                        )
                elif reference not in checks:
                    violations.append(
                        ImpactMapViolation(
                            "unknown_check_reference",
                            category_location,
                            f"unknown check `{reference}`",
                        )
                    )

    source_root = root / "src" / "gummysnake"
    source_files = set(source_root.rglob("*.py")) if source_root.is_dir() else set()
    for source_file in sorted(source_files):
        if source_file.resolve() not in owned_paths:
            violations.append(
                ImpactMapViolation(
                    "unowned_source_path",
                    str(source_file.relative_to(root)),
                    "source file is not covered by an area source glob",
                )
            )

    if source_root.is_dir():
        top_level_areas = [
            path for path in source_root.iterdir() if path.is_dir() and any(path.rglob("*.py"))
        ]
        for top_level_area in sorted(top_level_areas):
            area_files = tuple(top_level_area.rglob("*.py"))
            if any(source_file.resolve() not in owned_paths for source_file in area_files):
                violations.append(
                    ImpactMapViolation(
                        "unowned_top_level_python_area",
                        str(top_level_area.relative_to(root)),
                        "top-level Python area has source files without an impact-map owner",
                    )
                )
        root_modules = tuple(source_root.glob("*.py"))
        if any(source_file.resolve() not in owned_paths for source_file in root_modules):
            violations.append(
                ImpactMapViolation(
                    "unowned_top_level_python_area",
                    str(source_root.relative_to(root)),
                    "top-level Python modules do not have an impact-map owner",
                )
            )

    workspace_members = _workspace_members(root)
    for member in sorted(workspace_members - declared_crates):
        violations.append(
            ImpactMapViolation(
                "unowned_workspace_crate",
                str(member),
                "workspace crate has no impact-map area",
            )
        )
    for member in sorted(declared_crates - workspace_members):
        violations.append(
            ImpactMapViolation(
                "non_workspace_crate_owner",
                str(member),
                "declared crate owner is not a workspace member",
            )
        )

    return sorted(violations, key=lambda item: (item.code, item.location, item.message))


def main(argv: list[str] | None = None) -> int:
    """Run the impact-map audit as a repository-local command."""

    parser = argparse.ArgumentParser(description="Validate source-to-test impact-map ownership.")
    parser.add_argument(
        "--map", type=Path, default=DEFAULT_MAP_PATH, help="Map path relative to cwd."
    )
    args = parser.parse_args(argv)
    violations = audit(Path("."), args.map)
    if not violations:
        print("IMPACT_MAP_CHECK PASSED")
        return 0
    print("IMPACT_MAP_CHECK FAILED")
    for violation in violations:
        print(f"  {violation.code}: {violation.location}  # {violation.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
