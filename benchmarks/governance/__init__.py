"""Frozen authority rules for the replacement benchmark system."""

from .policy import (
    AUTHORITATIVE_DATA_REF,
    PERCENT_REGRESSION_LIMIT,
    AuthorityError,
    AuthorityRequirements,
    BenchmarkMode,
    ExecutionClass,
    GovernanceError,
    capability_error,
    reject_authority_overrides,
    require_authoritative_workload,
)

__all__ = [
    "AUTHORITATIVE_DATA_REF",
    "PERCENT_REGRESSION_LIMIT",
    "AuthorityError",
    "AuthorityRequirements",
    "BenchmarkMode",
    "ExecutionClass",
    "GovernanceError",
    "capability_error",
    "reject_authority_overrides",
    "require_authoritative_workload",
]
