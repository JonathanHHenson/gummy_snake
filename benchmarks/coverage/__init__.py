"""Auditable coverage projections for static benchmark catalogs."""

from .manifest import (
    MANIFEST_SCHEMA_VERSION,
    CoverageEntry,
    CoverageManifest,
    CoverageManifestError,
    MetricIdentity,
    assert_checked_manifest,
    build_manifest,
    load_checked_manifest,
    load_manifest,
    manifest_from_dict,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "CoverageEntry",
    "CoverageManifest",
    "CoverageManifestError",
    "MetricIdentity",
    "assert_checked_manifest",
    "build_manifest",
    "load_checked_manifest",
    "load_manifest",
    "manifest_from_dict",
]
