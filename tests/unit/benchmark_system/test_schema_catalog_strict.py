from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.schema.catalog import (
    CatalogError,
    Direction,
    MetricDomain,
    MetricSpec,
    PercentageTransform,
    ZeroPolicy,
    load_catalog,
)


def _catalog_text(*, schema_version: int = 1, extra_workload: str = "") -> str:
    return f"""
schema_version = {schema_version}
[suite]
id = "canvas"
version = 1
[[workloads]]
id = "fill"
version = 1
case_id = "small"
case_version = 2
parameter_version = 3
execution_class = "headless"
capabilities = ["canvas-runtime", "gpu"]
correctness = "pixel-checksum"
sampling_profile = "micro-v1"
source_files = ["work.py"]
{extra_workload}
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
valid_domain = "non-negative"
requires_positive_baseline = true
aggregation = "median-of-process-medians"
"""


def _write_catalog(tmp_path: Path, text: str | None = None) -> Path:
    (tmp_path / "work.py").write_text("print('benchmark')\n")
    path = tmp_path / "catalog.toml"
    path.write_text(text or _catalog_text())
    return path


def test_catalog_materializes_all_metric_and_identity_semantics(tmp_path: Path) -> None:
    workload = load_catalog(_write_catalog(tmp_path)).workloads[0]

    assert workload.suite_id == "canvas"
    assert workload.key == (
        "fill",
        1,
        "small",
        workload.parameter_digest,
        "elapsed",
        1,
        1,
    )
    assert workload.identity.case_version == 2
    assert workload.identity.parameter_version == 3
    assert workload.versioned_key == workload.identity.key
    assert workload.capabilities == ("canvas-runtime", "gpu")
    assert workload.correctness == "pixel-checksum"
    assert workload.sampling_profile == "micro-v1"
    assert workload.primary_metric.valid_domain is MetricDomain.NON_NEGATIVE
    assert workload.primary_metric.requires_positive_baseline is True
    assert workload.primary_metric.aggregation == "median-of-process-medians"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (_catalog_text(schema_version=2), "unsupported catalog schema"),
        (_catalog_text(extra_workload="dynamic_discovery = true"), "dynamic.*forbidden"),
        (_catalog_text(extra_workload="unknown_field = 1"), "unknown field"),
        (
            _catalog_text().replace('source_files = ["work.py"]', 'source_files = ["../work.py"]'),
            "escapes",
        ),
        (_catalog_text().replace("count = 10", "count_matrix = [10, 20]"), "separate workload"),
        (_catalog_text().replace("count = 10", "count = 1.5"), "binary floats"),
    ],
)
def test_catalog_rejects_dynamic_unknown_incomparable_or_noncanonical_declarations(
    tmp_path: Path, text: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog(_write_catalog(tmp_path, text))


def test_catalog_definition_digest_detects_entry_and_file_drift(tmp_path: Path) -> None:
    path = _write_catalog(tmp_path)
    catalog = load_catalog(path)
    digest = catalog.workloads[0].definition_digest
    declared = _catalog_text().replace(
        'source_files = ["work.py"]',
        f'source_files = ["work.py"]\ndefinition_digest = "{digest}"',
    )
    path.write_text(declared)
    declared_catalog = load_catalog(path)
    assert declared_catalog.workloads[0].definition_digest == digest

    (tmp_path / "work.py").write_text("print('changed without version bump')\n")
    with pytest.raises(CatalogError, match="definition digest mismatch"):
        declared_catalog.audit_definitions()
    with pytest.raises(CatalogError, match="does not match"):
        load_catalog(path)


def test_signed_and_nonpositive_metrics_require_explicit_mathematics() -> None:
    with pytest.raises(CatalogError, match="signed metrics"):
        MetricSpec(
            "slope",
            1,
            "units",
            "frame",
            Direction.LOWER_IS_BETTER,
            PercentageTransform.RATIO,
            ZeroPolicy.POSITIVE_BASELINE,
            3,
            valid_domain=MetricDomain.SIGNED,
        )

    transformed = MetricSpec(
        "slope",
        2,
        "units",
        "frame",
        Direction.LOWER_IS_BETTER,
        PercentageTransform.POSITIVE_OFFSET_RATIO,
        ZeroPolicy.EXPLICIT_TRANSFORM,
        3,
        valid_domain=MetricDomain.SIGNED,
        transform_offset=Decimal("10"),
    )
    assert transformed.percentage_change(Decimal("-5"), Decimal("-4")) == Decimal("0.2")

    absolute = MetricSpec(
        "signed-delta",
        1,
        "units",
        "frame",
        Direction.LOWER_IS_BETTER,
        PercentageTransform.ABSOLUTE,
        ZeroPolicy.ABSOLUTE_GATE,
        3,
        valid_domain=MetricDomain.SIGNED,
        absolute_limit=Decimal("2"),
    )
    assert not absolute.absolute_gate_failed(Decimal("2"))
    assert absolute.absolute_gate_failed(Decimal("2.01"))


def test_zero_tolerance_is_an_absolute_correctness_gate() -> None:
    metric = MetricSpec(
        "underruns",
        1,
        "count",
        "buffer",
        Direction.LOWER_IS_BETTER,
        PercentageTransform.ABSOLUTE,
        ZeroPolicy.ZERO_TOLERANCE,
        0,
    )

    assert metric.absolute_limit == 0
    assert not metric.absolute_gate_failed(Decimal(0))
    assert metric.absolute_gate_failed(Decimal(1))
    with pytest.raises(CatalogError, match="zero-tolerance"):
        MetricSpec(
            "underruns",
            1,
            "count",
            "buffer",
            Direction.LOWER_IS_BETTER,
            PercentageTransform.RATIO,
            ZeroPolicy.ZERO_TOLERANCE,
            0,
        )
