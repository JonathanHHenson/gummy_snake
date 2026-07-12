from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.schema.canonical import CanonicalJsonError, canonical_json
from benchmarks.schema.catalog import (
    CatalogError,
    Direction,
    MetricSpec,
    PercentageTransform,
    ZeroPolicy,
    load_catalog,
)
from benchmarks.schema.records import ComparisonFingerprint, RecordError


def test_catalog_is_static_and_digests_declared_workload_files(tmp_path: Path) -> None:
    (tmp_path / "work.py").write_text("print('benchmark')\n")
    catalog_path = tmp_path / "catalog.toml"
    catalog_path.write_text(
        """
schema_version = 1
[suite]
id = "canvas"
version = 1
[[workloads]]
id = "fill"
version = 1
case_id = "small"
execution_class = "headless"
capabilities = ["gpu"]
correctness = "checksum"
sampling_profile = "micro"
source_files = ["work.py"]
[workloads.parameters]
count = 10
[workloads.primary_metric]
id = "elapsed"
version = 1
unit = "ns"
work_unit = "draw"
direction = "lower-is-better"
transform = "ratio"
zero_policy = "positive-baseline"
precision = 3
"""
    )
    catalog = load_catalog(catalog_path)
    assert catalog.workloads[0].definition_digest.startswith("sha256:")
    assert catalog.workloads[0].primary_metric.normalized(50, 10) == Decimal(5)


def test_catalog_rejects_unexecuted_matrix_parameters(tmp_path: Path) -> None:
    (tmp_path / "work.py").write_text("print('benchmark')\n")
    catalog_path = tmp_path / "catalog.toml"
    catalog_path.write_text(
        """
schema_version = 1
[suite]
id = "canvas"
version = 1
[[workloads]]
id = "fill"
version = 1
case_id = "small"
execution_class = "headless"
capabilities = ["gpu"]
correctness = "checksum"
sampling_profile = "micro"
source_files = ["work.py"]
[workloads.parameters]
count_matrix = [10, 100]
[workloads.primary_metric]
id = "elapsed"
version = 1
unit = "ns"
work_unit = "draw"
direction = "lower-is-better"
transform = "ratio"
zero_policy = "positive-baseline"
precision = 3
"""
    )

    with pytest.raises(CatalogError, match=r"count_matrix.*separate workload"):
        load_catalog(catalog_path)


def test_metric_zero_policy_and_fingerprint_provenance_exclusion_are_strict() -> None:
    with pytest.raises(CatalogError):
        MetricSpec(
            "lost",
            1,
            "count",
            "frame",
            Direction.LOWER_IS_BETTER,
            PercentageTransform.RATIO,
            ZeroPolicy.ZERO_TOLERANCE,
            0,
        )
    with pytest.raises(RecordError):
        ComparisonFingerprint({"hostname": "private-machine"})
    with pytest.raises(CanonicalJsonError):
        canonical_json({"value": float("nan")})
