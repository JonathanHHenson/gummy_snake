from __future__ import annotations

from decimal import Decimal

import pytest

from benchmarks.governance import (
    AUTHORITATIVE_DATA_REF,
    DATABASE_GOVERNANCE,
    EXECUTION_CLASS_POLICIES,
    LEGACY_BENCHMARK_DATA_AUTHORITY,
    LOCAL_HISTORY_DIRECTORY,
    MODE_POLICIES,
    PERCENT_REGRESSION_LIMIT,
    PRODUCTION_DOMAINS,
    REGRESSION_LIMIT_FRACTION,
    REGRESSION_LIMIT_PERCENT,
    AuthorityError,
    AuthorityRequirements,
    BenchmarkDomain,
    BenchmarkMode,
    ExecutionClass,
    GovernanceError,
    degradation_exceeds_limit,
    reject_authority_overrides,
    require_authoritative_workload,
)


def test_authoritative_reference_and_requirements_are_frozen() -> None:
    assert AUTHORITATIVE_DATA_REF == "refs/heads/benchmark-data-v1"
    with pytest.raises(AuthorityError):
        require_authoritative_workload(AuthorityRequirements(True, True, True, True, True, False))


def test_authority_bypass_flags_are_rejected() -> None:
    for argument in ("--threshold=0.02", "--regression-limit", "--database-ref=other"):
        with pytest.raises(GovernanceError, match="override is not supported"):
            reject_authority_overrides(["worktree", argument])


def test_five_percent_policy_has_consistent_fraction_and_display_definitions() -> None:
    assert Decimal("5.00") == REGRESSION_LIMIT_PERCENT
    assert Decimal("0.05") == REGRESSION_LIMIT_FRACTION
    assert PERCENT_REGRESSION_LIMIT == REGRESSION_LIMIT_FRACTION
    assert not degradation_exceeds_limit(Decimal("0.0500"))
    assert degradation_exceeds_limit(Decimal("0.0500001"))
    with pytest.raises(GovernanceError, match="finite Decimal"):
        degradation_exceeds_limit(Decimal("NaN"))


def test_production_domain_inventory_covers_the_replacement_scope() -> None:
    assert set(PRODUCTION_DOMAINS) == set(BenchmarkDomain)
    assert {domain.value for domain in PRODUCTION_DOMAINS} == {
        "canvas",
        "ecs",
        "synth",
        "python-bridge",
        "gpu",
        "spatial",
        "dsp",
        "device",
        "output",
    }
    for domain, entry in PRODUCTION_DOMAINS.items():
        assert entry.domain is domain
        assert entry.owner
        assert entry.concerns
        assert entry.capability_families
        assert entry.permitted_execution_classes


def test_execution_mode_and_database_authority_are_structured_and_fail_closed() -> None:
    assert set(EXECUTION_CLASS_POLICIES) == set(ExecutionClass)
    assert not EXECUTION_CLASS_POLICIES[ExecutionClass.TRIAL].authoritative_eligible
    native = EXECUTION_CLASS_POLICIES[ExecutionClass.NATIVE_INTERACTIVE]
    assert "frames-presented-counter" in native.fail_closed_capabilities
    assert "headless" in native.timing_authority

    assert not MODE_POLICIES[BenchmarkMode.WORKTREE].database_writes
    assert MODE_POLICIES[BenchmarkMode.RECORD_HEAD].database_writes
    assert "exact HEAD" in MODE_POLICIES[BenchmarkMode.WORKTREE].baseline
    assert "ancestor" in MODE_POLICIES[BenchmarkMode.WORKTREE].baseline
    assert DATABASE_GOVERNANCE.default_backend == "local-filesystem"
    assert DATABASE_GOVERNANCE.history_directory == LOCAL_HISTORY_DIRECTORY
    assert DATABASE_GOVERNANCE.remote_required is False
    assert DATABASE_GOVERNANCE.configurable_value == "local-history-directory-only"
    assert DATABASE_GOVERNANCE.data_ref == AUTHORITATIVE_DATA_REF
    assert LEGACY_BENCHMARK_DATA_AUTHORITY == "historical-non-authoritative-not-imported"
