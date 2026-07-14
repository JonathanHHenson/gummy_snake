"""Suite-local production-path and qualification diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from benchmarks.governance import ExecutionClass

from .adapters import DeviceQualification


class SynthPathError(ValueError):
    """A workload requested an execution route outside its cataloged Synth identity."""


def path_diagnostics(
    execution_class: ExecutionClass,
    path: Sequence[str],
    *,
    work_units: int,
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Describe the exact exercised path without implying physical audio qualification."""

    if not path or work_units <= 0:
        raise SynthPathError("Synth path diagnostics require a route and positive work units")
    result: dict[str, object] = {
        "execution_class": execution_class.value,
        "path": list(path),
        "work_units": work_units,
        "physical_audio_requested": execution_class is ExecutionClass.NATIVE_AUDIO,
        "physical_audio_qualified": False,
        "audibility_claimed": False,
        "device_qualification": DeviceQualification.unavailable(
            requested=execution_class is ExecutionClass.NATIVE_AUDIO,
            reason=(
                "physical route must provide complete device evidence"
                if execution_class is ExecutionClass.NATIVE_AUDIO
                else "workload does not open a physical audio device"
            ),
        ).as_dict(),
    }
    if details:
        result.update(details)
    return result


def require_route(execution_class: ExecutionClass, *, simulated: bool = False) -> None:
    """Fail closed when a catalog case reaches the wrong offline/simulated route."""

    expected = ExecutionClass.SIMULATED_REALTIME if simulated else ExecutionClass.HEADLESS
    if execution_class is not expected:
        raise SynthPathError(
            f"Synth workload requires execution_class={expected.value!r}; "
            f"got {execution_class.value!r}. No alternate audio route is permitted."
        )


def require_physical_route(execution_class: ExecutionClass) -> None:
    """Require the selected native-audio route without opening or substituting a sink."""

    if execution_class is not ExecutionClass.NATIVE_AUDIO:
        raise SynthPathError(
            "physical SDL Synth workload requires execution_class='native-audio'; "
            "no offline or simulated audio route is permitted"
        )


__all__ = [
    "SynthPathError",
    "path_diagnostics",
    "require_physical_route",
    "require_route",
]
