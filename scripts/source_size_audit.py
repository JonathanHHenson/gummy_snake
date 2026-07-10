#!/usr/bin/env python3
"""Report and enforce source implementation-size policy.

Report mode lists files above the 300 counted-line review threshold. ``--check``
scans every production root, including Rust workspace members discovered from the
root ``Cargo.toml``, and fails when a file above 500 lines is new or grows beyond
its reviewed limit. The two intentionally centralized PyO3 binding surfaces have
separate, bounded limits.

Counts intentionally exclude symbol import/export barrels so files such as
``src/gummysnake/__init__.py`` are not treated as large implementation modules
just because they explicitly re-export public API names for static tooling.
"""

from __future__ import annotations

import argparse
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

SOURCE_SUFFIXES = {".py", ".rs"}
PYTHON_ROOTS = (Path("src"), Path("tests"), Path("examples"))
IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "target",
}
REVIEW_THRESHOLD = 300
CHECK_THRESHOLD = 500


@dataclass(frozen=True, slots=True)
class ReviewedLimit:
    """A reviewed maximum counted-line limit and its justification."""

    maximum: int
    reason: str


# These are intentionally centralized PyO3 registration surfaces. Their limits
# are exact current baselines so implementation work cannot accumulate there.
BINDING_EXCEPTION_LIMITS: dict[Path, ReviewedLimit] = {
    Path("crates/gummy_canvas/src/canvas/methods.rs"): ReviewedLimit(
        905,
        "Canvas PyO3 binding surface; implementation belongs in split helpers.",
    ),
    Path("crates/gummy_canvas/src/bindings/ecs/world.rs"): ReviewedLimit(
        494,
        "EcsWorld PyO3 binding surface; execution belongs in split crates/modules.",
    ),
}

# Reviewed Sprint 3 baseline for ordinary production files already over the
# enforcement threshold. New files and growth beyond these exact limits fail.
REVIEWED_PRODUCTION_LIMITS: dict[Path, ReviewedLimit] = {
    Path("src/gummysnake/ecs/world_facade/world.py"): ReviewedLimit(
        502,
        "Reviewed ECS facade baseline; split work is tracked separately.",
    ),
    Path("crates/gummy_ecs/src/execution/actions.rs"): ReviewedLimit(
        598,
        "Reviewed ECS execution baseline; split work is tracked separately.",
    ),
    Path("crates/gummy_ecs/src/execution/row_local_actions.rs"): ReviewedLimit(
        1647,
        "Reviewed ECS execution baseline; split work is tracked separately.",
    ),
    Path("crates/gummy_ecs/src/execution/spatial_direct/single.rs"): ReviewedLimit(
        651,
        "Reviewed ECS spatial execution baseline; split work is tracked separately.",
    ),
    Path("crates/gummy_ecs/src/execution/spatial_runtime.rs"): ReviewedLimit(
        530,
        "Reviewed ECS spatial execution baseline; split work is tracked separately.",
    ),
    Path("crates/gummy_synth/src/lib.rs"): ReviewedLimit(
        4405,
        "Reviewed synth baseline; planned domain split retains current behavior.",
    ),
}


@dataclass(frozen=True, slots=True)
class AuditEntry:
    counted_lines: int
    path: Path
    category: str
    exception: str | None = None


@dataclass(frozen=True, slots=True)
class CheckViolation:
    counted_lines: int
    path: Path
    limit: int | None
    reason: str


def discover_rust_workspace_members(repo_root: Path = Path(".")) -> tuple[Path, ...]:
    """Return workspace-member directories declared by the root Cargo manifest."""

    manifest = repo_root / "Cargo.toml"
    if not manifest.is_file():
        return ()

    workspace = tomllib.loads(manifest.read_text()).get("workspace", {})
    members = workspace.get("members", [])
    if not isinstance(members, list):
        return ()

    discovered: set[Path] = set()
    for member in members:
        if not isinstance(member, str):
            continue
        if any(marker in member for marker in "*?["):
            candidates = repo_root.glob(member)
        else:
            candidates = (repo_root / member,)
        discovered.update(candidate for candidate in candidates if candidate.is_dir())
    return tuple(sorted(discovered, key=lambda path: path.as_posix()))


def rust_source_roots(repo_root: Path = Path(".")) -> tuple[Path, ...]:
    """Return ``src`` roots for every discovered Rust workspace member."""

    return tuple(member / "src" for member in discover_rust_workspace_members(repo_root))


def production_roots(repo_root: Path = Path(".")) -> tuple[Path, ...]:
    """Return Python and all Cargo-workspace production source roots."""

    return (repo_root / PYTHON_ROOTS[0], *rust_source_roots(repo_root))


def default_roots(repo_root: Path = Path(".")) -> tuple[Path, ...]:
    """Return report roots, including all dynamically discovered Rust crates."""

    return (*production_roots(repo_root), *(repo_root / root for root in PYTHON_ROOTS[1:]))


def _has_ignored_part(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def _starts_symbol_block(path: Path, stripped: str) -> bool:
    if path.suffix == ".py":
        return (
            stripped.startswith("__all__")
            or stripped.startswith("from ")
            or stripped.startswith("import ")
        )
    if path.suffix == ".rs":
        return (
            stripped.startswith("use ")
            or stripped.startswith("pub use ")
            or stripped.startswith("pub(crate) use ")
        )
    return False


def _balance_for_line(path: Path, line: str) -> tuple[int, int]:
    if path.suffix == ".py":
        return line.count("(") + line.count("["), line.count(")") + line.count("]")
    if path.suffix == ".rs":
        return line.count("{"), line.count("}")
    return 0, 0


def count_implementation_lines(path: Path) -> int:
    """Count non-empty implementation lines after import/export exclusions."""

    lines = path.read_text(errors="ignore").splitlines()
    counted = 0
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if _starts_symbol_block(path, stripped):
            opens, closes = _balance_for_line(path, stripped)
            index += 1
            while opens > closes and index < len(lines):
                next_opens, next_closes = _balance_for_line(path, lines[index])
                opens += next_opens
                closes += next_closes
                index += 1
            continue
        counted += 1
        index += 1
    return counted


def iter_source_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in sorted(roots, key=lambda path: path.as_posix()):
        if not root.exists():
            continue
        if root.is_file():
            if root.suffix in SOURCE_SUFFIXES and not _has_ignored_part(root):
                yield root
            continue
        for path in sorted(root.rglob("*"), key=lambda candidate: candidate.as_posix()):
            if path.is_file() and path.suffix in SOURCE_SUFFIXES and not _has_ignored_part(path):
                yield path


def _relative_to_repo(path: Path, repo_root: Path) -> Path:
    try:
        return path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def category_for(
    path: Path,
    *,
    repo_root: Path = Path("."),
    production_source_roots: Iterable[Path] | None = None,
) -> str:
    """Classify a source file using the repository and discovered workspace roots."""

    relative_path = _relative_to_repo(path, repo_root)
    if relative_path in BINDING_EXCEPTION_LIMITS:
        return "exception"
    if path.name == "tests.rs" or "tests" in relative_path.parts:
        return "test/example"
    if any(_is_within(path, repo_root / root) for root in PYTHON_ROOTS[1:]):
        return "test/example"
    roots = (
        production_roots(repo_root) if production_source_roots is None else production_source_roots
    )
    if any(_is_within(path, root) for root in roots):
        return "production"
    return "other"


def audit(
    roots: Iterable[Path],
    threshold: int,
    *,
    repo_root: Path = Path("."),
) -> list[AuditEntry]:
    """Return deterministic report entries above ``threshold``."""

    entries = [
        AuditEntry(
            count_implementation_lines(path),
            path,
            category_for(path, repo_root=repo_root),
            BINDING_EXCEPTION_LIMITS.get(
                _relative_to_repo(path, repo_root), ReviewedLimit(0, "")
            ).reason
            if _relative_to_repo(path, repo_root) in BINDING_EXCEPTION_LIMITS
            else None,
        )
        for path in iter_source_files(roots)
    ]
    return sorted(
        (entry for entry in entries if entry.counted_lines > threshold),
        key=lambda entry: (-entry.counted_lines, entry.path.as_posix()),
    )


def check(
    repo_root: Path = Path("."),
    *,
    reviewed_limits: Mapping[Path, ReviewedLimit] | None = None,
    exception_limits: Mapping[Path, ReviewedLimit] | None = None,
) -> list[CheckViolation]:
    """Return unapproved production growth above the enforced size policy."""

    reviewed_limits = REVIEWED_PRODUCTION_LIMITS if reviewed_limits is None else reviewed_limits
    exception_limits = BINDING_EXCEPTION_LIMITS if exception_limits is None else exception_limits
    violations: list[CheckViolation] = []
    production_source_roots = production_roots(repo_root)
    for path in iter_source_files(production_source_roots):
        relative_path = _relative_to_repo(path, repo_root)
        counted_lines = count_implementation_lines(path)
        exception = exception_limits.get(relative_path)
        if exception is not None:
            if counted_lines > exception.maximum:
                violations.append(
                    CheckViolation(
                        counted_lines,
                        relative_path,
                        exception.maximum,
                        exception.reason,
                    )
                )
            continue
        if (
            category_for(
                path,
                repo_root=repo_root,
                production_source_roots=production_source_roots,
            )
            != "production"
            or counted_lines <= CHECK_THRESHOLD
        ):
            continue
        reviewed = reviewed_limits.get(relative_path)
        if reviewed is None:
            violations.append(
                CheckViolation(
                    counted_lines,
                    relative_path,
                    None,
                    "new production file over the 500-line enforcement threshold",
                )
            )
        elif counted_lines > reviewed.maximum:
            violations.append(
                CheckViolation(counted_lines, relative_path, reviewed.maximum, reviewed.reason)
            )
    return sorted(
        violations,
        key=lambda violation: (-violation.counted_lines, violation.path.as_posix()),
    )


def _print_report(entries: list[AuditEntry], category: str) -> None:
    for entry in entries:
        reason = f"  # {entry.exception}" if entry.exception else ""
        print(f"{entry.counted_lines:4} {entry.category:12} {entry.path}{reason}")
    print(f"TOTAL {len(entries)}")
    if category == "all":
        ordinary = [entry for entry in entries if entry.category != "exception"]
        print(f"NON_EXCEPTION_TOTAL {len(ordinary)}")


def _print_check(violations: list[CheckViolation]) -> None:
    if not violations:
        print("SOURCE_SIZE_CHECK PASSED")
        return
    print("SOURCE_SIZE_CHECK FAILED")
    for violation in violations:
        limit = "unapproved" if violation.limit is None else str(violation.limit)
        print(
            f"{violation.counted_lines:4} limit {limit:10} {violation.path}  # {violation.reason}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report files over 300 lines or enforce reviewed 500-line production limits."
    )
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        help=(
            "Optional report roots. Defaults to Python, tests/examples, "
            "and Cargo workspace sources."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=REVIEW_THRESHOLD,
        help="Report review threshold (default: 300; ignored by --check).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Fail on new or enlarged production files over 500 lines; "
            "always scans all production roots."
        ),
    )
    parser.add_argument(
        "--category",
        choices=("all", "production", "test/example", "exception", "other"),
        default="production",
        help="Limit report output to one category (default: production; ignored by --check).",
    )
    args = parser.parse_args(argv)

    repo_root = Path(".")
    if args.check:
        violations = check(repo_root)
        _print_check(violations)
        return int(bool(violations))

    roots = tuple(args.roots) if args.roots else default_roots(repo_root)
    entries = audit(roots, args.threshold, repo_root=repo_root)
    if args.category != "all":
        entries = [entry for entry in entries if entry.category == args.category]
    _print_report(entries, args.category)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
