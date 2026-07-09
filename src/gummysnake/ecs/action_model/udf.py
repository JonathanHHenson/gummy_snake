# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
@dataclass(frozen=True)
class RuntimeUdfDefinition(_RuntimeUdfBase):
    """Metadata for a runtime Python UDF action."""

    def __call__(self, *args: UdfArgument) -> DefaultAction | None:
        """Create or append a Python UDF action."""

        action = DefaultAction("udf", udf=self, udf_args=tuple(args))
        if active_build_session():
            append_action(action, operation=f"@ecs.udf {self.function.__name__}()")
            return None
        return action


@dataclass(frozen=True)
class UdfIterableDefinition(_RuntimeUdfBase):
    """Metadata for a Python UDF that produces values for ``ecs.for_each``."""

    def __call__(self, *args: UdfArgument) -> UdfIterableSource:
        """Create an iterable ECS loop source from this Python UDF.

        Args:
            args: Values or ECS expressions passed to the decorated UDF.

        Returns:
            An iterable source accepted by ``ecs.for_each``.
        """

        return UdfIterableSource(self, tuple(args))


def validate_mutation_metadata(
    callback: Callable[..., Any], mutations: Mapping[str, object] | None
) -> dict[str, frozenset[object]]:
    """Validate EntityMutation metadata keyed by callback parameter name."""

    if not mutations:
        return {}
    from gummysnake.ecs.world import EntityMutation

    parameter_names = builtins.set(inspect.signature(callback).parameters)
    normalized: dict[str, frozenset[object]] = {}
    for parameter_name, declared in mutations.items():
        if parameter_name not in parameter_names:
            raise SystemPlanError(
                f"ECS mutation metadata for {callback.__name__} references unknown "
                f"parameter {parameter_name!r}."
            )
        if isinstance(declared, EntityMutation):
            mutation_set = frozenset({declared})
        elif isinstance(declared, Iterable) and not isinstance(declared, str | bytes):
            mutation_set = frozenset(declared)
        else:
            raise SystemPlanError(
                f"ECS mutation metadata for {parameter_name!r} must be a set of "
                "ecs.EntityMutation[...] declarations."
            )
        if not mutation_set:
            raise SystemPlanError(f"ECS mutation metadata for {parameter_name!r} cannot be empty.")
        for mutation in mutation_set:
            if not isinstance(mutation, EntityMutation):
                raise SystemPlanError(
                    f"ECS mutation metadata for {parameter_name!r} must contain only "
                    "ecs.EntityMutation[...] declarations."
                )
        normalized[parameter_name] = mutation_set
    return normalized


def _is_iterable_annotation(annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin is None:
        return False
    return origin in {Iterable, list, tuple} or getattr(origin, "__name__", "") in {
        "Iterable",
        "Iterator",
        "Generator",
    }


@dataclass(frozen=True, eq=False)
class UdfCallExpression(Expression):
    """Lazy expression node for a Rust-backed ECS UDF call."""

    definition: UdfPlanDefinition
    args: tuple[UdfArgument, ...]

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        """Reject Python evaluation for Rust-backed UDF expression nodes.

        Args:
            ctx: Current ECS expression bindings.
            world: ECS world that would provide runtime storage.

        Returns:
            This method always raises because Rust-backed UDFs execute in Rust plans only.
        """

        del ctx, world
        raise SystemExecutionError(
            f"Rust-backed ECS UDF {self.definition.function.__name__!r} cannot execute in Python."
        )


@dataclass(frozen=True)
class _RuntimeUdfDecorator:
    mutations: Mapping[str, object] | None = None

    @overload
    def __call__(self, callback: Callable[..., Iterable[Any]]) -> UdfIterableDefinition: ...

    @overload
    def __call__(self, callback: Callable[..., Any]) -> RuntimeUdfDefinition: ...

    def __call__(
        self, callback: Callable[..., Any]
    ) -> RuntimeUdfDefinition | UdfIterableDefinition:
        """Create a runtime Python UDF definition."""

        return _build_runtime_udf_definition(callback, mutations=self.mutations)


@dataclass(frozen=True)
class _UdfPlanDecorator:
    def __call__(self, callback: Callable[..., Any]) -> UdfPlanDefinition:
        """Create a Rust-backed UDF plan definition."""

        return _build_udf_plan_definition(callback)


def _udf_type_hints(callback: Callable[..., Any]) -> dict[str, Any]:
    hints = get_type_hints(callback, include_extras=True)
    signature = inspect.signature(callback)
    for parameter in signature.parameters.values():
        if parameter.name not in hints:
            raise SystemPlanError(
                f"ECS UDF {callback.__name__} parameter {parameter.name!r} needs a type annotation."
            )
    if "return" not in hints:
        raise SystemPlanError(f"ECS UDF {callback.__name__} needs a return annotation.")
    return hints


def _build_runtime_udf_definition(
    callback: Callable[..., Any],
    *,
    mutations: Mapping[str, object] | None,
) -> RuntimeUdfDefinition | UdfIterableDefinition:
    hints = _udf_type_hints(callback)
    definition_type = (
        UdfIterableDefinition if _is_iterable_annotation(hints["return"]) else RuntimeUdfDefinition
    )
    return definition_type(
        callback,
        hints["return"],
        mutations=validate_mutation_metadata(callback, mutations),
    )


def _build_udf_plan_definition(callback: Callable[..., Any]) -> UdfPlanDefinition:
    hints = _udf_type_hints(callback)
    signature = inspect.signature(callback)
    for parameter in signature.parameters.values():
        if hints[parameter.name] is not Expression:
            raise SystemPlanError(
                f"Rust-backed ECS UDF plan {callback.__name__} parameter {parameter.name!r} "
                "must be annotated as ecs.Expression[T]. Use @ecs.udf "
                "for runtime Python vector/materialized inputs."
            )
    if hints["return"] is not Expression:
        raise SystemPlanError(
            f"Rust-backed ECS UDF plan {callback.__name__} return type must be ecs.Expression[T]."
        )
    return UdfPlanDefinition(callback, hints["return"])


@overload
def udf(function: Callable[..., Iterable[Any]], /) -> UdfIterableDefinition: ...


@overload
def udf(function: Callable[..., Any], /) -> RuntimeUdfDefinition: ...


@overload
def udf(
    function: None = None,
    *,
    mutations: Mapping[str, object] | None = None,
) -> _RuntimeUdfDecorator: ...


def udf(
    function: Callable[..., Any] | None = None,
    *,
    mutations: Mapping[str, object] | None = None,
) -> _RuntimeUdfDecorator | RuntimeUdfDefinition | UdfIterableDefinition:
    """Declare a runtime Python UDF usable from ECS plans.

    Python UDFs are explicit Python execution boundaries for side effects,
    materialized entity/resource access, or iterable sources. Use
    :func:`udf_plan` for Rust-backed expression UDF plans.

    Args:
        function: Function to decorate when ``@ecs.udf`` is used without parentheses.
        mutations: Entity mutation declarations keyed by Python UDF parameter name.

    Returns:
        A UDF definition, or a decorator that creates one.
    """

    decorator = _RuntimeUdfDecorator(mutations=mutations)
    if function is not None:
        return decorator(function)
    return decorator


@overload
def udf_plan(function: Callable[..., Any], /) -> UdfPlanDefinition: ...


@overload
def udf_plan(function: None = None) -> _UdfPlanDecorator: ...


def udf_plan(
    function: Callable[..., Any] | None = None,
) -> _UdfPlanDecorator | UdfPlanDefinition:
    """Declare a Rust-backed expression UDF for ECS system plans.

    UDF plans describe pure expression work for the ECS planner and must annotate
    parameters and return values as ``ecs.Expression[T]``. Use :func:`udf` when
    the function must run Python code at ECS runtime.

    Args:
        function: Function to decorate when ``@ecs.udf_plan`` is used without parentheses.

    Returns:
        A UDF definition, or a decorator that creates one.
    """

    decorator = _UdfPlanDecorator()
    if function is not None:
        return decorator(function)
    return decorator
