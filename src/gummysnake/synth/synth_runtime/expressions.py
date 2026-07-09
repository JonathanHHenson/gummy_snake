# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
@dataclass(frozen=True, slots=True, eq=False)
class LiteralExpression(Expression):
    value: object
    id: int = field(default_factory=_next_expression_id, repr=False, compare=False)
    repeat_depth: int | None = field(
        default_factory=_current_repeat_depth_or_none,
        repr=False,
        compare=False,
    )

    def evaluate(self, ctx: EvalContext) -> object:
        return _cached_expression_value(
            ctx,
            self.repeat_depth,
            self.id,
            lambda: resolve_value(self.value, ctx),
        )


@dataclass(frozen=True, slots=True, eq=False)
class UnaryExpression(Expression):
    op: str
    operand: Expression
    id: int = field(default_factory=_next_expression_id, repr=False, compare=False)
    repeat_depth: int | None = field(
        default_factory=_current_repeat_depth_or_none,
        repr=False,
        compare=False,
    )

    def evaluate(self, ctx: EvalContext) -> object:
        return _cached_expression_value(
            ctx,
            self.repeat_depth,
            self.id,
            lambda: self._evaluate_uncached(ctx),
        )

    def _evaluate_uncached(self, ctx: EvalContext) -> object:
        value = resolve_value(self.operand, ctx)
        if self.op == "neg":
            return -cast(Number, value)
        raise SynthPlanError(f"Unknown unary synth expression op: {self.op}.")


@dataclass(frozen=True, slots=True, eq=False)
class BinaryExpression(Expression):
    op: str
    left: Expression
    right: Expression
    id: int = field(default_factory=_next_expression_id, repr=False, compare=False)
    repeat_depth: int | None = field(
        default_factory=_current_repeat_depth_or_none,
        repr=False,
        compare=False,
    )

    def evaluate(self, ctx: EvalContext) -> object:
        return _cached_expression_value(
            ctx,
            self.repeat_depth,
            self.id,
            lambda: self._evaluate_uncached(ctx),
        )

    def _evaluate_uncached(self, ctx: EvalContext) -> object:
        left = resolve_value(self.left, ctx)
        right = resolve_value(self.right, ctx)
        if self.op == "add":
            return cast(Any, left) + cast(Any, right)
        if self.op == "sub":
            return cast(Any, left) - cast(Any, right)
        if self.op == "mul":
            return cast(Any, left) * cast(Any, right)
        if self.op == "truediv":
            return cast(Any, left) / cast(Any, right)
        if self.op == "mod":
            return cast(Any, left) % cast(Any, right)
        if self.op == "pow":
            return cast(Any, left) ** cast(Any, right)
        raise SynthPlanError(f"Unknown binary synth expression op: {self.op}.")


@dataclass(frozen=True, slots=True, eq=False)
class CompareExpression(Expression):
    op: str
    left: Expression
    right: Expression
    id: int = field(default_factory=_next_expression_id, repr=False, compare=False)
    repeat_depth: int | None = field(
        default_factory=_current_repeat_depth_or_none,
        repr=False,
        compare=False,
    )

    def evaluate(self, ctx: EvalContext) -> object:
        return _cached_expression_value(
            ctx,
            self.repeat_depth,
            self.id,
            lambda: self._evaluate_uncached(ctx),
        )

    def _evaluate_uncached(self, ctx: EvalContext) -> object:
        left = resolve_value(self.left, ctx)
        right = resolve_value(self.right, ctx)
        if self.op == "lt":
            return cast(Any, left) < cast(Any, right)
        if self.op == "le":
            return cast(Any, left) <= cast(Any, right)
        if self.op == "gt":
            return cast(Any, left) > cast(Any, right)
        if self.op == "ge":
            return cast(Any, left) >= cast(Any, right)
        if self.op == "eq":
            return left == right
        if self.op == "ne":
            return left != right
        raise SynthPlanError(f"Unknown comparison synth expression op: {self.op}.")


@dataclass(frozen=True, slots=True, eq=False)
class RandomExpression(Expression):
    kind: Literal["rand", "rand_i", "rrand", "rrand_i", "dice", "one_in"]
    args: tuple[Expression, ...]
    id: int = field(default_factory=_next_expression_id, repr=False, compare=False)
    repeat_depth: int | None = field(
        default_factory=_current_repeat_depth_or_none,
        repr=False,
        compare=False,
    )

    def evaluate(self, ctx: EvalContext) -> object:
        return _cached_expression_value(
            ctx,
            self.repeat_depth,
            self.id,
            lambda: self._evaluate_uncached(ctx),
        )

    def _evaluate_uncached(self, ctx: EvalContext) -> object:
        values = tuple(resolve_value(arg, ctx) for arg in self.args)
        if self.kind == "rand":
            max_value = _as_float(values[0]) if values else 1.0
            return ctx.rng.random() * max_value
        if self.kind == "rand_i":
            max_value = _as_int(values[0]) if values else 2
            return ctx.rng.randrange(max(1, max_value))
        if self.kind == "rrand":
            low, high = (_as_float(values[0]), _as_float(values[1]))
            return ctx.rng.uniform(low, high)
        if self.kind == "rrand_i":
            low, high = (_as_int(values[0]), _as_int(values[1]))
            return ctx.rng.randint(low, high)
        if self.kind == "dice":
            sides = _as_int(values[0]) if values else 6
            if sides <= 0:
                raise ArgumentValidationError("dice sides must be positive.")
            return ctx.rng.randint(1, sides)
        if self.kind == "one_in":
            sides = _as_int(values[0])
            if sides <= 0:
                raise ArgumentValidationError("one_in probability denominator must be positive.")
            return ctx.rng.randrange(sides) == 0
        raise SynthPlanError(f"Unknown random synth expression kind: {self.kind}.")


@dataclass(frozen=True, slots=True, eq=False)
class ChoiceExpression(Expression):
    source: Expression
    id: int = field(default_factory=_next_expression_id, repr=False, compare=False)
    repeat_depth: int | None = field(
        default_factory=_current_repeat_depth_or_none,
        repr=False,
        compare=False,
    )

    def evaluate(self, ctx: EvalContext) -> object:
        return _cached_expression_value(
            ctx,
            self.repeat_depth,
            self.id,
            lambda: self._evaluate_uncached(ctx),
        )

    def _evaluate_uncached(self, ctx: EvalContext) -> object:
        source = resolve_value(self.source, ctx)
        if (
            isinstance(source, Ring)
            or isinstance(source, Sequence)
            and not isinstance(source, str | bytes | bytearray)
        ):
            values = tuple(source)
        else:
            raise ArgumentValidationError("choose() requires a non-empty sequence or ring.")
        if not values:
            raise ArgumentValidationError("choose() requires a non-empty sequence or ring.")
        return resolve_value(values[ctx.rng.randrange(len(values))], ctx)


@dataclass(frozen=True, slots=True, eq=False)
class BoundExpression(Expression):
    """Lazy value bound once for each expanded nested track call."""

    id: int
    call_id: int
    source: Expression

    def evaluate(self, ctx: EvalContext) -> object:
        key = ("bound", _call_scope_prefix(ctx.scope, self.call_id), self.id)
        if key not in ctx.bindings:
            ctx.bindings[key] = resolve_value(self.source, ctx)
        return ctx.bindings[key]


@dataclass(frozen=True, slots=True, eq=False)
class SourceBoundExpression(Expression):
    """Lazy value captured at its source position in a track plan."""

    id: int
    repeat_depth: int
    source: Expression

    def evaluate(self, ctx: EvalContext) -> object:
        key = _source_bind_key(ctx, self.repeat_depth, self.id)
        if key not in ctx.bindings:
            ctx.bindings[key] = resolve_value(self.source, ctx)
        return ctx.bindings[key]
