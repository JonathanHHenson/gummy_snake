# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
@overload
def track(
    func: None = None,
    *,
    loop: bool = False,
    loop_times: int | None = None,
    bpm: float = 60.0,
    seed: int = 0,
) -> Callable[[_TrackFunction], TrackDefinition]: ...


@overload
def track(
    func: _TrackFunction,
    *,
    loop: bool = False,
    loop_times: int | None = None,
    bpm: float = 60.0,
    seed: int = 0,
) -> TrackDefinition: ...


def track(
    func: _TrackFunction | None = None,
    *,
    loop: bool = False,
    loop_times: int | None = None,
    bpm: float = 60.0,
    seed: int = 0,
) -> Callable[[_TrackFunction], TrackDefinition] | TrackDefinition:
    """Decorate a function as a logical synth track.

    The decorator may be used as ``@sy.track`` or ``@sy.track(loop=True)``. The
    resulting object is callable. Outside another track it returns a built
    :class:`Track`; inside another track it inlines the decorated function into
    the active logical plan.
    """

    def decorate(inner: _TrackFunction) -> TrackDefinition:
        definition = TrackDefinition(inner, loop=loop, loop_times=loop_times, bpm=bpm, seed=seed)
        package = sys.modules.get("gummysnake.synth")
        if package is not None and not hasattr(package, definition.__name__):
            setattr(package, definition.__name__, definition)
        return definition

    if func is not None:
        return decorate(func)
    return decorate
