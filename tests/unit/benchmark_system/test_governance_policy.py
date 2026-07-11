from __future__ import annotations

import pytest

from benchmarks.governance import (
    AUTHORITATIVE_DATA_REF,
    AuthorityError,
    AuthorityRequirements,
    GovernanceError,
    reject_authority_overrides,
    require_authoritative_workload,
)


def test_authoritative_reference_and_requirements_are_frozen() -> None:
    assert AUTHORITATIVE_DATA_REF == "refs/heads/benchmark-data-v1"
    with pytest.raises(AuthorityError):
        require_authoritative_workload(AuthorityRequirements(True, True, True, True, True, False))


def test_authority_bypass_flags_are_rejected() -> None:
    with pytest.raises(GovernanceError):
        reject_authority_overrides(["worktree", "--threshold=0.02"])
