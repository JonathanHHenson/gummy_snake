from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from gummysnake.exceptions import ArgumentValidationError
from gummysnake.synth.synth_runtime.builder_context import (
    _CURRENT_BUILDER,
    FxContext,
    SynthContext,
    _next_node_id,
)
from gummysnake.synth.synth_runtime.event_api import (
    _bind_track_call_value,
    _expand_fx_handle,
    _fx_definition_key,
    _synth_definition_key,
    play,
    sleep,
)
from gummysnake.synth.synth_runtime.logical_nodes import CallNode, TrackPlan
from gummysnake.synth.synth_runtime.physical_plan import PhysicalPlan
from gummysnake.synth.synth_runtime.runtime_foundation import _SAMPLE_RATE, Duration, SynthPlanError
from gummysnake.synth.synth_runtime.scales_and_specs import (
    _FX_DEFINITION_CAPTURE,
    _FX_DEFINITIONS,
    _FX_EXPANSION_STACK,
    _SYNTH_DEFINITIONS,
    _SYNTH_EXPANSION_STACK,
    FxHandle,
)
from gummysnake.synth.synth_runtime.track import Track

if TYPE_CHECKING:
    pass

type _TrackFunction = Callable[..., object]
type _SynthFunction = Callable[..., object]
type _FxFunction = Callable[..., object]


class SynthDefinition:
    """Callable wrapper produced by ``@sy.synth`` for source-defined synths."""

    def __init__(self, func: _SynthFunction, *, name: str | None = None) -> None:
        self.func = func
        function_name = str(getattr(func, "__name__", "synth"))
        self.name = _synth_definition_key(name or function_name)
        self.__name__ = function_name
        self.__doc__ = getattr(func, "__doc__", None)
        _SYNTH_DEFINITIONS[self.name] = self
        package = sys.modules.get("gummysnake.synth")
        if package is not None and not hasattr(package, self.name):
            setattr(package, self.name, self)

    def __call__(self, value: object = 60, **opts: object) -> Track:
        """Build this synth definition as a standalone source track."""

        return self.build(value, **opts)

    def build(self, value: object = 60, **opts: object) -> Track:
        from gummysnake.synth.synth_runtime.plan_builder import PlanBuilder

        builder = PlanBuilder(seed=0)
        token_builder = _CURRENT_BUILDER.set(builder)
        token_stack = _SYNTH_EXPANSION_STACK.set((self.name,))
        try:
            result = self.func(value, **opts)
        finally:
            _SYNTH_EXPANSION_STACK.reset(token_stack)
            _CURRENT_BUILDER.reset(token_builder)
        if result is not None:
            raise SynthPlanError("@sy.synth functions must build actions and return None.")
        plan = TrackPlan(
            self.name,
            tuple(builder.nodes),
            builder.current_beat,
            bpm=builder.bpm,
            seed=builder.seed,
        )
        return Track(self, plan)

    def physical_plan(
        self, duration: Duration | float | None = None, **opts: object
    ) -> PhysicalPlan:
        return self.build(**opts).physical_plan(duration)

    def save(
        self,
        path: str | Path,
        *,
        duration: Duration | float | None = None,
        sample_rate: int = _SAMPLE_RATE,
        **opts: object,
    ) -> Path:
        return self.build(**opts).save(path, duration=duration, sample_rate=sample_rate)


class FxDefinition:
    """Callable wrapper produced by ``@sy.fx`` for source-defined FX."""

    def __init__(self, func: _FxFunction, *, name: str | None = None) -> None:
        self.func = func
        function_name = str(getattr(func, "__name__", "fx"))
        self.name = _fx_definition_key(name or function_name)
        self.__name__ = function_name
        self.__doc__ = getattr(func, "__doc__", None)
        _FX_DEFINITIONS[self.name] = self
        package = sys.modules.get("gummysnake.synth")
        if package is not None and not hasattr(package, self.name):
            setattr(package, self.name, self)

    def __call__(self, **opts: object) -> FxContext:
        """Return an FX context using this source-defined FX name."""

        return FxContext(self.name, opts)

    def build_chain(self, source_id: int, opts: Mapping[str, object]) -> tuple[FxHandle, ...]:
        """Expand this source FX into lower-level FX handles for an event."""

        from gummysnake.synth.synth_runtime.plan_builder import PlanBuilder

        stack = _FX_EXPANSION_STACK.get()
        if self.name in stack:
            raise SynthPlanError(f"Recursive FX definition expansion for {self.name!r}.")
        child = PlanBuilder(seed=0)
        captured: list[FxHandle] = []
        token_builder = _CURRENT_BUILDER.set(child)
        token_stack = _FX_EXPANSION_STACK.set((*stack, self.name))
        token_capture = _FX_DEFINITION_CAPTURE.set(captured)
        try:
            result = self.func(**dict(opts))
        finally:
            _FX_DEFINITION_CAPTURE.reset(token_capture)
            _FX_EXPANSION_STACK.reset(token_stack)
            _CURRENT_BUILDER.reset(token_builder)
        if result is not None:
            raise SynthPlanError("@sy.fx functions must build FX contexts and return None.")
        expanded: list[FxHandle] = []
        for child_handle in captured:
            expanded.extend(
                _expand_fx_handle(FxHandle(source_id, child_handle.name, dict(child_handle.opts)))
            )
        return tuple(expanded)

    def build(self, **opts: object) -> Track:
        """Build this FX definition as a standalone source track for asset compilation."""

        from gummysnake.synth.synth_runtime.plan_builder import PlanBuilder

        builder = PlanBuilder(seed=0)
        token_builder = _CURRENT_BUILDER.set(builder)
        try:
            with FxContext(self.name, opts):
                with SynthContext("_saw", {}):
                    play(60, release=0.08, amp=0.35)
                sleep(0.08)
        finally:
            _CURRENT_BUILDER.reset(token_builder)
        plan = TrackPlan(
            self.name,
            tuple(builder.nodes),
            builder.current_beat,
            bpm=builder.bpm,
            seed=builder.seed,
        )
        return Track(self, plan)

    def physical_plan(
        self, duration: Duration | float | None = None, **opts: object
    ) -> PhysicalPlan:
        return self.build(**opts).physical_plan(duration)

    def save(
        self,
        path: str | Path,
        *,
        duration: Duration | float | None = None,
        sample_rate: int = _SAMPLE_RATE,
        **opts: object,
    ) -> Path:
        return self.build(**opts).save(path, duration=duration, sample_rate=sample_rate)


class TrackDefinition:
    """Callable wrapper produced by :func:`track`."""

    def __init__(
        self,
        func: _TrackFunction,
        *,
        loop: bool = False,
        loop_times: int | None = None,
        bpm: float = 60.0,
        seed: int = 0,
    ) -> None:
        if loop_times is not None and loop_times < 0:
            raise ArgumentValidationError("track(loop_times=...) cannot be negative.")
        self.func = func
        self.__name__ = getattr(func, "__name__", "track")
        self.__doc__ = getattr(func, "__doc__", None)
        self.loop = bool(loop)
        self.loop_times = loop_times
        self.bpm = float(bpm)
        self.seed = int(seed)

    def __call__(self, *args: object, **kwargs: object) -> Track:
        active = _CURRENT_BUILDER.get()
        if active is not None:
            call_id = _next_node_id()
            child = active.child()
            bound_args = tuple(_bind_track_call_value(arg, call_id) for arg in args)
            bound_kwargs = {
                name: _bind_track_call_value(value, call_id) for name, value in kwargs.items()
            }
            token = _CURRENT_BUILDER.set(child)
            try:
                result = self.func(*bound_args, **bound_kwargs)
            finally:
                _CURRENT_BUILDER.reset(token)
            if result is not None:
                raise SynthPlanError("@sy.track functions must build actions and return None.")
            active.nodes.append(
                CallNode(
                    id=call_id,
                    name=self.__name__,
                    body=tuple(child.nodes),
                    beat=active.current_beat,
                    body_beats=child.current_beat,
                )
            )
            active.current_beat += child.current_beat
            return Track(self, TrackPlan(self.__name__, (), 0.0, self.loop, self.loop_times))
        return self.build(*args, **kwargs)

    def build(self, *args: object, **kwargs: object) -> Track:
        """Build and return a logical track plan."""

        from gummysnake.synth.synth_runtime.plan_builder import PlanBuilder

        builder = PlanBuilder(bpm=self.bpm, seed=self.seed)
        token = _CURRENT_BUILDER.set(builder)
        try:
            result = self.func(*args, **kwargs)
        finally:
            _CURRENT_BUILDER.reset(token)
        if result is not None:
            raise SynthPlanError("@sy.track functions must build actions and return None.")
        plan = TrackPlan(
            self.__name__,
            tuple(builder.nodes),
            builder.current_beat,
            loop=self.loop,
            loop_times=self.loop_times,
            bpm=builder.bpm,
            seed=builder.seed,
        )
        return Track(self, plan)
