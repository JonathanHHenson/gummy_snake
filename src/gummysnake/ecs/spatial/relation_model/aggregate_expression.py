# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
@dataclass(frozen=True, eq=False)
class SpatialAggregateExpression(Expression):
    """Lazy aggregate expression computed from a ``SpatialRelation``.

    Args:
        kind: Aggregate operation name, such as ``"count"`` or ``"mean"``.
        relation: Spatial relation to aggregate.
        value: Optional expression evaluated for each matched item.
        default: Optional value used when ``min``, ``max``, or ``mean`` has no matches.
    """

    kind: str
    relation: SpatialRelation
    value: Expression | None = None
    default: object | None = None

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        epoch = getattr(world, "_spatial_epoch", 0)
        cache = getattr(world, "_spatial_aggregate_cache", None)
        if cache is None:
            cache = {}
            world._spatial_aggregate_cache = cache
        cache_key = (
            id(self),
            epoch,
            _spatial_context_key(ctx, self.relation.origin, exclude=self.relation.item),
        )
        if cache_key in cache:
            world._diagnostics["ecs_spatial_aggregate_cache_hits"] += 1
            return cache[cache_key]
        world._diagnostics["ecs_spatial_aggregate_cache_misses"] += 1

        values: list[Any] = []
        count = 0
        result: Any
        for joined in self.relation.iter_contexts(ctx, world):
            count += 1
            if self.kind == "any":
                cache[cache_key] = True
                return True
            if self.value is not None:
                values.append(self.value.eval(joined, world))
        if self.kind == "any":
            result = False
        elif self.kind == "count":
            result = count
        elif self.kind == "sum":
            result = sum(values) if values else 0
        elif self.kind == "min":
            if values:
                result = min(values)
            elif self.default is not None:
                result = self.default
            else:
                raise ValueError("Spatial min aggregate is empty and no default was provided.")
        elif self.kind == "max":
            if values:
                result = max(values)
            elif self.default is not None:
                result = self.default
            else:
                raise ValueError("Spatial max aggregate is empty and no default was provided.")
        elif self.kind == "mean":
            if values:
                result = sum(values) / len(values)
            elif self.default is not None:
                result = self.default
            else:
                raise ValueError("Spatial mean aggregate is empty and no default was provided.")
        else:
            raise ValueError(f"Unsupported spatial aggregate {self.kind!r}.")
        cache[cache_key] = result
        return result

    def _ecs_outer_queries(self) -> set[QueryProxy]:
        return {self.relation.origin}
