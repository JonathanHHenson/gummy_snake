"""Replacement-safe subprocess operations for authoritative Git access."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import DatabaseError


@dataclass(frozen=True, slots=True)
class GitResult:
    """Captured output from a Git command that may legitimately fail."""

    returncode: int
    stdout: str
    stderr: str


def git_result(repository: Path, *arguments: str) -> GitResult:
    """Run Git with replacement objects and interactive prompting disabled."""

    environment = os.environ.copy()
    environment.update(
        {
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    return GitResult(result.returncode, result.stdout.strip(), result.stderr.strip())


def git(repository: Path, *arguments: str, check: bool = True) -> str:
    """Run Git and return stripped stdout, raising a database error by default."""

    result = git_result(repository, *arguments)
    if check and result.returncode:
        detail = result.stderr or result.stdout or "unknown Git failure"
        raise DatabaseError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout


def git_succeeded(repository: Path, *arguments: str) -> bool:
    """Return whether a replacement-safe Git command completed successfully."""

    return git_result(repository, *arguments).returncode == 0


def show_file(repository: Path, reference: str, path: str) -> bytes | None:
    """Read one file from a Git tree without decoding its authoritative bytes."""

    environment = os.environ.copy()
    environment.update({"GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"})
    result = subprocess.run(
        ("git", "-C", str(repository), "show", f"{reference}:{path}"),
        capture_output=True,
        env=environment,
        check=False,
    )
    return None if result.returncode else result.stdout
