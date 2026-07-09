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
def system(function: Callable[..., object], /) -> RuntimeSystemDefinition: ...


@overload
def system(
    function: Callable[..., object],
    /,
    *,
    name: str | None = None,
    queries: Mapping[str, object] | None = None,
    mutations: Mapping[str, object] | None = None,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> RuntimeSystemDefinition: ...


@overload
def system(
    function: None = None,
    *,
    name: str | None = None,
    queries: Mapping[str, object] | None = None,
    mutations: Mapping[str, object] | None = None,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> Callable[[Callable[..., object]], RuntimeSystemDefinition]: ...


def system(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    queries: Mapping[str, object] | None = None,
    mutations: Mapping[str, object] | None = None,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> RuntimeSystemDefinition | Callable[[Callable[..., object]], RuntimeSystemDefinition]:
    """Decorate a function as a runtime Python ECS system.

    Python systems execute during the ECS schedule as explicit scheduler
    barriers. Use :func:`system_plan` for Rust-executed logical plans.

    Args:
        function: Function to decorate when ``@ecs.system`` is used without parentheses.
        name: Optional scheduler name to show in diagnostics instead of the function name.
        queries: Query metadata for unannotated parameters in Python systems.
        mutations: Entity mutation metadata for Python systems.
        group: Optional system group name or sequence of group names. Group names are
            validated at registration.
        before: Group names that this system's implicit group should run before.
        after: Group names that this system's implicit group should run after.

    Returns:
        A system definition, or a decorator that creates one.
    """

    normalized_before, normalized_after = _normalize_scheduling("@ecs.system", group, before, after)

    def decorate(callback: Callable[..., object]) -> RuntimeSystemDefinition:
        return RuntimeSystemDefinition(
            callback,
            name=name,
            group=group,
            before=normalized_before,
            after=normalized_after,
            queries=_validate_query_metadata(callback, queries),
            mutations=validate_mutation_metadata(callback, mutations),
        )

    if function is not None:
        return decorate(function)
    return decorate


@overload
def system_plan(function: Callable[..., object], /) -> SystemPlanDefinition: ...


@overload
def system_plan(
    function: Callable[..., object],
    /,
    *,
    name: str | None = None,
    parallel: bool = False,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> SystemPlanDefinition: ...


@overload
def system_plan(
    function: None = None,
    *,
    name: str | None = None,
    parallel: bool = False,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> Callable[[Callable[..., object]], SystemPlanDefinition]: ...


def system_plan(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    parallel: bool = False,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> SystemPlanDefinition | Callable[[Callable[..., object]], SystemPlanDefinition]:
    """Decorate a function as a Rust-executed ECS logical plan.

    Plan systems run once at registration to record context-managed ECS actions.
    They execute later through the Rust physical-plan runtime and must return
    ``None``. Use :func:`system` for runtime Python systems.

    Args:
        function: Function to decorate when ``@ecs.system_plan`` is used without parentheses.
        name: Optional scheduler name to show in diagnostics instead of the function name.
        parallel: Whether Rust may execute independent recorded actions in parallel.
        group: Optional system group name or sequence of group names. Group names are
            validated at registration.
        before: Group names that this system's implicit group should run before.
        after: Group names that this system's implicit group should run after.

    Returns:
        A system definition, or a decorator that creates one.
    """

    normalized_before, normalized_after = _normalize_scheduling(
        "@ecs.system_plan", group, before, after
    )

    def decorate(callback: Callable[..., object]) -> SystemPlanDefinition:
        return SystemPlanDefinition(
            callback,
            name=name,
            group=group,
            before=normalized_before,
            after=normalized_after,
            parallel=bool(parallel),
        )

    if function is not None:
        return decorate(function)
    return decorate


def _normalize_scheduling(
    api_name: str,
    group: str | Iterable[str] | None,
    before: Iterable[str],
    after: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    normalized_before = tuple(str(item) for item in before)
    normalized_after = tuple(str(item) for item in after)
    if group is not None and (normalized_before or normalized_after):
        raise SystemPlanError(
            f"{api_name}(group=...) cannot also declare before=... or after=...; "
            "configure group order with gs.group() or gs.order()."
        )
    return normalized_before, normalized_after


def _validate_query_metadata(
    callback: Callable[..., object], queries: Mapping[str, object] | None
) -> dict[str, QuerySpec]:
    if not queries:
        return {}
    parameter_names = set(inspect.signature(callback).parameters)
    normalized: dict[str, QuerySpec] = {}
    for parameter_name, query in queries.items():
        if parameter_name not in parameter_names:
            raise SystemPlanError(
                f"Python ECS system query metadata for {callback.__name__} references "
                f"unknown parameter {parameter_name!r}."
            )
        if not isinstance(query, QuerySpec):
            raise SystemPlanError(
                f"Python ECS system query metadata for {parameter_name!r} must be ecs.Query[...]."
            )
        normalized[parameter_name] = query
    return normalized


__all__ = [
    "BuiltSystem",
    "PlanBuiltSystem",
    "RuntimeBuiltSystem",
    "RuntimeSystemDefinition",
    "SystemDefinition",
    "SystemPlanDefinition",
    "system",
    "system_plan",
]
