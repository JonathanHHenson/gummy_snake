# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
class ThreadContext:
    """Context manager that records a parallel logical branch."""

    def __init__(self, *, name: str | None = None) -> None:
        self._name = name
        self._parent: PlanBuilder | None = None
        self._child: PlanBuilder | None = None
        self._token: object | None = None

    def __enter__(self) -> ThreadContext:
        parent = _current_builder()
        child = parent.child()
        self._parent = parent
        self._child = child
        self._token = _CURRENT_BUILDER.set(child)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        assert self._parent is not None and self._child is not None and self._token is not None
        _CURRENT_BUILDER.reset(cast(Any, self._token))
        if exc_type is not None:
            return
        self._parent.nodes.append(
            ThreadNode(
                id=_next_node_id(),
                body=tuple(self._child.nodes),
                beat=self._parent.current_beat,
                body_beats=self._child.current_beat,
                name=self._name,
            )
        )


@overload
def synth(func: _SynthFunction, /) -> SynthDefinition: ...


@overload
def synth(name: str, /, **opts: object) -> SynthContext: ...


@overload
def synth(*, name: str | None = None) -> Callable[[_SynthFunction], SynthDefinition]: ...


def synth(
    name_or_func: str | _SynthFunction | None = None,
    /,
    **opts: object,
) -> SynthContext | SynthDefinition | Callable[[_SynthFunction], SynthDefinition]:
    """Select a synth context or decorate a source-defined synth.

    ``with sy.synth("tb303")`` keeps the existing context-manager behavior.
    ``@sy.synth`` or ``@sy.synth(name="tb303")`` registers a synth definition
    written in Gummy Snake source code.
    """

    decorator_name = opts.pop("name", None)
    if callable(name_or_func) and not isinstance(name_or_func, str):
        if decorator_name is not None and not isinstance(decorator_name, str):
            raise ArgumentValidationError("@sy.synth(name=...) must be a string.")
        return SynthDefinition(name_or_func, name=decorator_name)
    if name_or_func is None:
        if decorator_name is not None and not isinstance(decorator_name, str):
            raise ArgumentValidationError("@sy.synth(name=...) must be a string.")

        def decorate(inner: _SynthFunction) -> SynthDefinition:
            return SynthDefinition(inner, name=decorator_name)

        return decorate
    if decorator_name is not None:
        raise ArgumentValidationError("sy.synth('name', ...) cannot also pass name=....")
    return SynthContext(str(name_or_func), opts)


def use_synth(name: str, **opts: object) -> None:
    """Set the current synth for the remainder of the current builder scope."""

    builder = _current_builder()
    builder.synth_stack[-1] = SynthSpec(name, dict(opts))


def synth_input(value: object = _DEFAULT_SYNTH_INPUT_NOTE, **opts: object) -> SynthSignal:
    """Start a source-synth signal builder for an ``@sy.synth`` definition.

    Pass ``defaults={...}`` to supply source-defined option defaults before
    caller overrides. The returned :class:`SynthSignal` is immutable; each
    builder method returns a new signal value.
    """

    defaults = opts.pop("defaults", None)
    if defaults is not None and not isinstance(defaults, Mapping):
        raise ArgumentValidationError("synth_input(defaults=...) must be a mapping.")
    merged = dict(defaults or {})
    merged.update(opts)
    return SynthSignal(value, merged)


def synth_output(signal: SynthSignal) -> tuple[NodeHandle, ...]:
    """Record a source-synth signal into the active synth plan.

    Single layers become low-level primitive synth events (``_sine``, ``_saw``,
    etc.). Multi-layer oscillator banks become one generic ``_layered`` primitive
    carrying serializable layer metadata, so public Sonic Pi synth names still are
    not dispatched in Rust. Sample nodes become ordinary ``sy.sample`` events,
    and explicit silences use the ``_silence`` primitive.
    """

    handles: list[NodeHandle] = []
    base_opts = dict(signal.opts)
    base_amp = base_opts.pop("amp", _DEFAULT_SYNTH_LAYER_AMP)
    if len(signal.layers) == 1:
        layer_node = signal.layers[0]
        layer_opts = dict(base_opts)
        layer_opts.update(layer_node.opts)
        layer_opts["amp"] = _multiply_synth_amp(base_amp, layer_node.amp)
        with synth(f"_{layer_node.wave}"):
            handle = play(_transposed_synth_note(signal.note, layer_node.transpose), **layer_opts)
            handle.node.control_note_transpose = layer_node.transpose
            handles.append(handle)
    elif signal.layers:
        layer_opts = dict(base_opts)
        layer_opts["amp"] = base_amp
        layer_opts["layers"] = [_synth_layer_payload(layer_node) for layer_node in signal.layers]
        with synth("_layered"):
            handles.append(play(signal.note, **layer_opts))
    for sample_node in signal.samples:
        sample_opts = dict(sample_node.opts)
        sample_opts.update(signal.opts)
        handles.append(sample(sample_node.value, *sample_node.filters, **sample_opts))
    for silence_node in signal.silences:
        silence_opts = dict(silence_node.opts)
        silence_opts.update(signal.opts)
        with synth("_silence"):
            handles.append(play(signal.note, **silence_opts))
    return tuple(handles)


def _synth_layer_payload(layer_node: SynthLayer) -> dict[str, object]:
    return {
        "wave": layer_node.wave,
        "transpose": layer_node.transpose,
        "amp": layer_node.amp,
        "opts": dict(layer_node.opts),
    }


def _transposed_synth_note(value: object, transpose: object) -> object:
    if isinstance(transpose, int | float) and transpose == 0:
        return value
    if isinstance(value, Ring):
        return Ring(_transposed_synth_note(item, transpose) for item in value)
    if isinstance(value, list):
        return [_transposed_synth_note(item, transpose) for item in value]
    if isinstance(value, tuple):
        return tuple(_transposed_synth_note(item, transpose) for item in value)
    if isinstance(value, Expression):
        return value + transpose
    if isinstance(value, str | int | float | bool) or value is None:
        resolved = note(value)
        if resolved is None:
            return None
        if isinstance(transpose, Expression):
            return ensure_expr(resolved) + transpose
        if isinstance(transpose, int | float):
            return resolved + float(transpose)
    return value


def _multiply_synth_amp(base_amp: object, layer_amp: object) -> object:
    left = _synth_numeric_or_default(base_amp, _DEFAULT_SYNTH_LAYER_AMP)
    right = _synth_numeric_or_default(layer_amp, 1.0)
    if isinstance(left, Expression) or isinstance(right, Expression):
        return ensure_expr(left) * ensure_expr(right)
    return float(cast(Any, left)) * float(cast(Any, right))


def _synth_numeric_or_default(value: object, default: float) -> object:
    if isinstance(value, Expression):
        return value
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return default


@overload
def fx(func: _FxFunction, /) -> FxDefinition: ...


@overload
def fx(name: str, /, **opts: object) -> FxContext: ...


@overload
def fx(*, name: str | None = None) -> Callable[[_FxFunction], FxDefinition]: ...


def fx(
    name_or_func: str | _FxFunction | None = None,
    /,
    **opts: object,
) -> FxContext | FxDefinition | Callable[[_FxFunction], FxDefinition]:
    """Apply an FX context or decorate a source-defined FX.

    ``with sy.fx("reverb")`` keeps the existing context-manager behavior.
    ``@sy.fx`` or ``@sy.fx(name="reverb")`` registers an FX definition that
    composes lower-level FX contexts in Gummy Snake source.
    """

    decorator_name = opts.pop("name", None)
    if callable(name_or_func) and not isinstance(name_or_func, str):
        if decorator_name is not None and not isinstance(decorator_name, str):
            raise ArgumentValidationError("@sy.fx(name=...) must be a string.")
        return FxDefinition(name_or_func, name=decorator_name)
    if name_or_func is None:
        if decorator_name is not None and not isinstance(decorator_name, str):
            raise ArgumentValidationError("@sy.fx(name=...) must be a string.")

        def decorate(inner: _FxFunction) -> FxDefinition:
            return FxDefinition(inner, name=decorator_name)

        return decorate
    if decorator_name is not None:
        raise ArgumentValidationError("sy.fx('name', ...) cannot also pass name=....")
    return FxContext(str(name_or_func), opts)


def fx_input() -> FxSignal:
    """Return the source signal placeholder for an ``@sy.fx`` definition."""

    return FxSignal()


def fx_output(signal: FxSignal, **opts: object) -> FxHandle:
    """Record the output signal for an ``@sy.fx`` definition.

    The signal operations are serialized as a generic low-level FX chain. Public
    FX definitions should use this builder instead of assembling operation lists
    by hand.
    """

    ops = [dict(operation) for operation in signal.ops]
    if not ops:
        ops = [{"op": "level"}]
    context = FxContext("_chain", {"ops": ops, **opts})
    with context as handle:
        return handle


def loop(*, times: int | None = None) -> LoopContext:
    """Repeat a nested logical block.

    ``times=None`` records an open-ended loop. Rendering repeats it until the
    requested track duration is filled.
    """

    return LoopContext(times=times)
