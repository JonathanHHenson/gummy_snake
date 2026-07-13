"""Shared lifecycle contract for deterministic Synth benchmark adapters.

An adapter describes actual work phases, not a substitute renderer.  Routes which
need a native SDL3 device remain unavailable until they provide a real adapter
that opens that device; this module never changes an execution class.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter_ns


class SynthAdapterError(RuntimeError):
    """A benchmark adapter omitted a required lifecycle phase or leaked cleanup."""


@dataclass(frozen=True, slots=True)
class PhaseMeasurements:
    """Monotonic timings for the mandatory shared benchmark lifecycle."""

    prepare_ns: int
    warm_ns: int
    timed_ns: int
    synchronize_ns: int
    validate_ns: int
    teardown_ns: int

    def as_dict(self) -> dict[str, int]:
        """Return stable phase names suitable for benchmark diagnostics records."""

        return {
            "prepare_ns": self.prepare_ns,
            "warm_ns": self.warm_ns,
            "timed_ns": self.timed_ns,
            "synchronize_ns": self.synchronize_ns,
            "validate_ns": self.validate_ns,
            "teardown_ns": self.teardown_ns,
        }


@dataclass(frozen=True, slots=True)
class AdapterRun[OutputT]:
    """Validated output and measurements from one complete adapter lifecycle."""

    output: OutputT
    phases: PhaseMeasurements

    def diagnostics(self) -> dict[str, object]:
        """Return the versioned phase payload used by Synth benchmark records."""

        return {"schema_version": 1, "lifecycle": self.phases.as_dict()}


@dataclass(slots=True)
class CallableSynthAdapter[ContextT, OutputT]:
    """Concrete callback adapter for one production Synth route.

    Each callback corresponds to exactly one phase.  ``timed`` is deliberately
    isolated from fixture creation, cache warming, output validation, and cleanup
    so benchmark workers can time it without accidentally measuring harness work.
    """

    prepare: Callable[[], ContextT]
    warm: Callable[[ContextT], None]
    timed: Callable[[ContextT], OutputT]
    synchronize: Callable[[ContextT, OutputT], None]
    validate: Callable[[ContextT, OutputT], None]
    teardown: Callable[[ContextT], None]


def _measure[OutputT](action: Callable[[], OutputT]) -> tuple[OutputT, int]:
    started = perf_counter_ns()
    output = action()
    elapsed = perf_counter_ns() - started
    if elapsed < 0:  # Defensive for non-conforming clocks; perf_counter_ns should not regress.
        raise SynthAdapterError("monotonic benchmark clock regressed")
    return output, elapsed


def run_adapter[ContextT, OutputT](
    adapter: CallableSynthAdapter[ContextT, OutputT],
) -> AdapterRun[OutputT]:
    """Run prepare → warm → timed → synchronize → validate → teardown exactly once.

    Teardown runs after every successfully prepared context, including validation
    failures.  If teardown itself fails while another phase is already failing,
    the original error is retained because it identifies the production-path
    defect; callers should inspect resource diagnostics separately.
    """

    context, prepare_ns = _measure(adapter.prepare)
    warm_ns = timed_ns = synchronize_ns = validate_ns = teardown_ns = 0
    active_error: BaseException | None = None
    try:
        _, warm_ns = _measure(lambda: adapter.warm(context))
        output, timed_ns = _measure(lambda: adapter.timed(context))
        _, synchronize_ns = _measure(lambda: adapter.synchronize(context, output))
        _, validate_ns = _measure(lambda: adapter.validate(context, output))
    except BaseException as error:
        active_error = error
        raise
    finally:
        try:
            _, teardown_ns = _measure(lambda: adapter.teardown(context))
        except BaseException:
            if active_error is None:
                raise
    return AdapterRun(
        output=output,
        phases=PhaseMeasurements(
            prepare_ns=prepare_ns,
            warm_ns=warm_ns,
            timed_ns=timed_ns,
            synchronize_ns=synchronize_ns,
            validate_ns=validate_ns,
            teardown_ns=teardown_ns,
        ),
    )


def merge_lifecycle_diagnostics[OutputT](
    diagnostics: Mapping[str, object], run: AdapterRun[OutputT]
) -> dict[str, object]:
    """Attach one lifecycle payload without overwriting production diagnostics."""

    result = dict(diagnostics)
    if "benchmark_lifecycle" in result:
        raise SynthAdapterError("benchmark diagnostics already contain benchmark_lifecycle")
    result["benchmark_lifecycle"] = run.diagnostics()
    return result


__all__ = [
    "AdapterRun",
    "CallableSynthAdapter",
    "PhaseMeasurements",
    "SynthAdapterError",
    "merge_lifecycle_diagnostics",
    "run_adapter",
]
