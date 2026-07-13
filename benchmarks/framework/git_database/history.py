"""Fixed-ref Git repository validation and first-parent history resolution."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ...governance import AUTHORITATIVE_DATA_REF
from . import DatabaseError
from .git_operations import git, git_result, git_succeeded
from .paths import is_lower_hex
from .transactions import repository_lock

_FETCH_REF = "refs/benchmark-data/fetched/benchmark-data-v1"


class GitRepositoryHistory:
    """Own strict Git/ref semantics shared by benchmark storage operations."""

    def __init__(self, repository: Path, data_ref: str = AUTHORITATIVE_DATA_REF) -> None:
        if data_ref != AUTHORITATIVE_DATA_REF:
            raise DatabaseError(
                f"benchmark database ref is fixed at {AUTHORITATIVE_DATA_REF}; migration required"
            )
        self.repository = repository.resolve()
        self.data_ref = AUTHORITATIVE_DATA_REF
        git(self.repository, "rev-parse", "--git-dir")
        object_format = git(self.repository, "rev-parse", "--show-object-format")
        if object_format not in {"sha1", "sha256"}:
            raise DatabaseError(f"unsupported Git object format: {object_format or 'unknown'}")
        self.object_format = object_format
        self.object_id_length = 40 if object_format == "sha1" else 64

    def _common_directory(self) -> Path:
        return Path(git(self.repository, "rev-parse", "--path-format=absolute", "--git-common-dir"))

    @contextmanager
    def _lock(self) -> Iterator[None]:
        with repository_lock(self._common_directory()):
            yield

    def _validate_object_id(self, object_id: str, *, field: str = "Git object id") -> str:
        normalized = object_id.lower()
        if (
            len(normalized) != self.object_id_length
            or object_id != normalized
            or not is_lower_hex(normalized)
        ):
            raise DatabaseError(
                f"{field} must be a full lowercase {self.object_format} Git object id"
            )
        return normalized

    def _commit_id(self, revision: str, *, field: str = "revision") -> str:
        result = git_result(self.repository, "rev-parse", "--verify", f"{revision}^{{commit}}")
        if result.returncode or not result.stdout:
            raise DatabaseError(f"{field} does not identify an available Git commit: {revision}")
        return self._validate_object_id(result.stdout, field=field)

    def require_complete_history(self) -> None:
        """Reject shallow repositories and configured replacement objects."""

        shallow = git(self.repository, "rev-parse", "--is-shallow-repository")
        if shallow != "false":
            if shallow == "true":
                raise DatabaseError("authoritative benchmark history must not be shallow")
            raise DatabaseError("Git could not establish whether benchmark history is complete")
        replacements = git(self.repository, "replace", "-l")
        if replacements:
            raise DatabaseError(
                "authoritative benchmark resolution rejects repositories with replacement refs; "
                "remove them before recording or auditing"
            )

    def data_tip(self) -> str:
        """Return the verified commit at the fixed authoritative data ref."""

        result = git_result(
            self.repository,
            "rev-parse",
            "--verify",
            f"{self.data_ref}^{{commit}}",
        )
        if result.returncode or not result.stdout:
            detail = f" ({result.stderr})" if result.stderr else ""
            raise DatabaseError(
                f"authoritative benchmark data ref {self.data_ref} is unavailable or "
                f"corrupt{detail}; configure the recorder remote and provision the protected "
                "v1 data branch"
            )
        return self._validate_object_id(result.stdout, field="authoritative data tip")

    def _data_ref_checked_out(self) -> bool:
        output = git(self.repository, "worktree", "list", "--porcelain")
        return any(line == f"branch {AUTHORITATIVE_DATA_REF}" for line in output.splitlines())

    def _is_ancestor(self, older: str, newer: str) -> bool:
        return git_succeeded(self.repository, "merge-base", "--is-ancestor", older, newer)

    def _delete_fetch_ref(self) -> None:
        git(self.repository, "update-ref", "-d", _FETCH_REF, check=False)

    def fetch_authoritative_ref(self, remote: str) -> str:
        """Fetch exactly the governed ref and accept only a complete fast-forward update.

        This verifies a URL or configured remote but cannot provision permissions or bypass
        protected-branch policy. A checked-out local authority branch is verified but never
        moved behind that worktree's back.
        """

        if not remote or remote.startswith("-"):
            raise DatabaseError("an authoritative data remote name or URL is required")
        self.require_complete_history()
        with self._lock():
            self._delete_fetch_ref()
            try:
                result = git_result(
                    self.repository,
                    "fetch",
                    "--no-tags",
                    "--no-write-fetch-head",
                    "--",
                    remote,
                    f"+{AUTHORITATIVE_DATA_REF}:{_FETCH_REF}",
                )
                if result.returncode:
                    detail = result.stderr or result.stdout or "remote ref unavailable"
                    raise DatabaseError(
                        f"failed to fetch required {AUTHORITATIVE_DATA_REF} from {remote}: {detail}"
                    )
                remote_tip = self._commit_id(_FETCH_REF, field="fetched authoritative data tip")
                git(self.repository, "rev-list", "--objects", remote_tip)
                local_result = git_result(
                    self.repository, "rev-parse", "--verify", f"{self.data_ref}^{{commit}}"
                )
                if local_result.returncode or not local_result.stdout:
                    if self._data_ref_checked_out():
                        raise DatabaseError(
                            "an unavailable authority ref is unexpectedly checked out"
                        )
                    git(self.repository, "update-ref", self.data_ref, remote_tip, "")
                    return remote_tip
                local_tip = self._validate_object_id(
                    local_result.stdout, field="local authoritative data tip"
                )
                if local_tip == remote_tip:
                    return local_tip
                if not self._is_ancestor(local_tip, remote_tip):
                    relation = (
                        "configured remote is behind the local authority tip"
                        if self._is_ancestor(remote_tip, local_tip)
                        else "configured remote and local authority histories diverged"
                    )
                    raise DatabaseError(
                        f"{relation}; refusing a non-fast-forward authoritative ref update"
                    )
                if self._data_ref_checked_out():
                    raise DatabaseError(
                        "the checked-out benchmark-data-v1 worktree is stale; fast-forward that "
                        "worktree explicitly before recording"
                    )
                git(self.repository, "update-ref", self.data_ref, remote_tip, local_tip)
                return remote_tip
            finally:
                self._delete_fetch_ref()

    def require_authoritative_ready(self) -> str:
        """Validate history and return the authoritative data tip."""

        self.require_complete_history()
        return self.data_tip()

    def head(self) -> str:
        """Return the current code commit, including from detached HEAD."""

        return self._commit_id("HEAD", field="HEAD")

    def require_clean_head(self) -> str:
        """Return HEAD only when the code worktree and history are authoritative."""

        if git(self.repository, "status", "--porcelain", "--untracked-files=all"):
            raise DatabaseError("record-head requires a clean worktree")
        self.require_complete_history()
        return self.head()

    def first_parent_commits(self, head: str | None = None) -> tuple[str, ...]:
        """Return commits before ``head`` on only its first-parent chain."""

        self.require_complete_history()
        subject = self._commit_id(head or "HEAD", field="benchmark subject")
        parent_result = git_result(
            self.repository, "rev-parse", "--verify", f"{subject}^1^{{commit}}"
        )
        if parent_result.returncode or not parent_result.stdout:
            return ()
        parent = self._validate_object_id(parent_result.stdout, field="first parent")
        output = git(self.repository, "rev-list", "--first-parent", parent)
        commits = tuple(line for line in output.splitlines() if line)
        for commit in commits:
            self._validate_object_id(commit, field="first-parent commit")
        return commits
