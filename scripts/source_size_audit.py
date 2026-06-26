#!/usr/bin/env python3
"""Report Python and Rust source files over a counted-line threshold.

The count intentionally excludes symbol import/export barrels so files such as
``src/gummysnake/__init__.py`` are not treated as large implementation modules
just because they explicitly re-export public API names for static tooling.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SOURCE_SUFFIXES = {".py", ".rs"}
DEFAULT_ROOTS = (
    Path("src"),
    Path("crates/gummy_canvas/src"),
    Path("crates/gummy_accel/src"),
    Path("tests"),
    Path("examples"),
)
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
PRODUCTION_ROOTS = (Path("src"), Path("crates/gummy_canvas/src"), Path("crates/gummy_accel/src"))
TEST_EXAMPLE_ROOTS = (Path("tests"), Path("examples"))
JUSTIFIED_EXCEPTIONS = {
    Path("crates/gummy_canvas/src/canvas/methods.rs"): (
        "single explicit PyO3 binding surface for Canvas; implementation lives in split helpers"
    ),
}


@dataclass(frozen=True, slots=True)
class AuditEntry:
    counted_lines: int
    path: Path
    category: str
    exception: str | None = None


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
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            if root.suffix in SOURCE_SUFFIXES and not _has_ignored_part(root):
                yield root
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in SOURCE_SUFFIXES and not _has_ignored_part(path):
                yield path


def category_for(path: Path) -> str:
    if path in JUSTIFIED_EXCEPTIONS:
        return "exception"
    if path.name == "tests.rs" or "tests" in path.parts:
        return "test/example"
    if any(path == root or root in path.parents for root in TEST_EXAMPLE_ROOTS):
        return "test/example"
    if any(path == root or root in path.parents for root in PRODUCTION_ROOTS):
        return "production"
    return "other"


def audit(roots: Iterable[Path], threshold: int) -> list[AuditEntry]:
    entries = [
        AuditEntry(
            count_implementation_lines(path),
            path,
            category_for(path),
            JUSTIFIED_EXCEPTIONS.get(path),
        )
        for path in iter_source_files(roots)
    ]
    return sorted(
        (entry for entry in entries if entry.counted_lines > threshold),
        key=lambda entry: (-entry.counted_lines, str(entry.path)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, default=list(DEFAULT_ROOTS))
    parser.add_argument("--threshold", type=int, default=300)
    parser.add_argument(
        "--category",
        choices=("all", "production", "test/example", "exception", "other"),
        default="all",
        help="Limit output to one category.",
    )
    args = parser.parse_args()

    entries = audit(args.roots, args.threshold)
    if args.category != "all":
        entries = [entry for entry in entries if entry.category == args.category]

    for entry in entries:
        reason = f"  # {entry.exception}" if entry.exception else ""
        print(f"{entry.counted_lines:4} {entry.category:12} {entry.path}{reason}")
    print(f"TOTAL {len(entries)}")
    if args.category == "all":
        ordinary = [entry for entry in entries if entry.category != "exception"]
        print(f"NON_EXCEPTION_TOTAL {len(ordinary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
