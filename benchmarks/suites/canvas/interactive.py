"""Retired physical-input benchmark boundary.

Canvas native-window benchmarks now use the ordinary bounded workloads in
``workloads.py``. The former input-injection protocol is intentionally unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Never

from benchmarks.governance import ExecutionClass


class InteractiveWorkloadError(RuntimeError):
    """The retired physical-input benchmark route was requested."""


def dispatch(parameters: Mapping[str, object], execution_class: ExecutionClass | str) -> Never:
    """Reject the retired automation-only native-input workload."""

    del parameters, execution_class
    raise InteractiveWorkloadError(
        "native-input-window automation workloads were removed; "
        "run a bounded native-interactive Canvas workload instead"
    )


__all__ = ["InteractiveWorkloadError", "dispatch"]
