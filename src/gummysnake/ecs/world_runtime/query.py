"""Private helpers for Python-side ECS query materialization."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.logical_plan.actions import Action, UdfArgument, action_write_targets
from gummysnake.ecs.logical_plan.expressions import (
    Expression,
    ExpressionInput,
    FieldExpression,
    QueryProxy,
    expression_queries,
)
from gummysnake.ecs.logical_plan.specifications import (
    ChangeTerm,
    Query,
    QuerySpec,
    TagTerm,
    WithoutTerm,
)
from gummysnake.ecs.runtime_view_model import Entity, EntityView
from gummysnake.ecs.schema_helpers import _schema_name
from gummysnake.exceptions import SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world_facade import EcsWorld


type MaterializedUdfArgument = list[EntityView] | ExpressionInput


def match_query(world: EcsWorld, spec: QuerySpec) -> list[EntityView]:
    """Materialize Rust-filtered entity views for a query specification.

    Rust evaluates all component, tag, exclusion, and change terms against its
    canonical world and active change epoch. Python constructs views only after
    that query returns, so UDF/materialized paths do not maintain a second
    component-change mirror.
    """

    terms: list[tuple[str, str]] = []
    for term in spec.terms:
        if isinstance(term, TagTerm):
            terms.append(("with_tag", str(term.value)))
        elif isinstance(term, ChangeTerm):
            world.validate_schema(term.component_type)
            terms.append((term.kind, _schema_name(term.component_type)))
        elif isinstance(term, WithoutTerm):
            value = term.value
            if isinstance(value, TagTerm):
                terms.append(("without_tag", str(value.value)))
            elif isinstance(value, type):
                world.validate_schema(value)
                terms.append(("without_component", _schema_name(value)))
            else:
                raise SystemPlanError(f"Unsupported ecs.Without query term {value!r}.")
        elif isinstance(term, type):
            world.validate_schema(term)
            terms.append(("with_component", _schema_name(term)))
        else:
            raise SystemPlanError(f"Unsupported ECS query term {term!r}.")
    rows = world._rust.query_with_terms(terms)
    return [
        EntityView(world, Entity(index, generation, world._world_id)) for index, generation in rows
    ]


def iter_join_contexts_for(
    world: EcsWorld,
    base_ctx: dict[object, Any],
    expr: Expression,
    *,
    include_query: QueryProxy | None = None,
) -> Iterator[dict[object, Any]]:
    """Yield context dictionaries for all query combinations needed by an expression."""
    queries = expression_queries(expr)
    if include_query is not None:
        queries.add(include_query)
    yield from iter_join_contexts_for_queries(world, base_ctx, queries)


def iter_join_contexts_for_queries(
    world: EcsWorld, base_ctx: dict[object, Any], queries: Iterable[QueryProxy]
) -> Iterator[dict[object, Any]]:
    """Yield context dictionaries for every combination of currently unbound queries."""
    missing = sorted(
        (query for query in set(queries) if query not in base_ctx), key=lambda q: q.name
    )
    if not missing:
        yield dict(base_ctx)
        return
    matches = [world.match_query(cast(QuerySpec, query.spec)) for query in missing]
    for combo in itertools.product(*matches):
        joined = dict(base_ctx)
        for query, entity in zip(missing, combo, strict=True):
            joined[query] = entity
        yield joined


def write_key(
    target: FieldExpression, ctx: dict[object, Any]
) -> tuple[int, type[Any], str] | tuple[str, type[Any], str]:
    """Return the deterministic write-conflict key for a field mutation target."""
    if isinstance(target.source, QueryProxy):
        entity = ctx[target.source]
        return (entity.entity.index, target.component_type, target.field_name)
    return ("resource", target.component_type, target.field_name)


def check_parallel_children(world: EcsWorld, children: tuple[Action, ...]) -> None:
    """Validate that parallel action children do not write the same target twice."""
    seen: set[tuple[object, type[Any], str]] = set()
    for child in children:
        targets = action_write_targets(child)
        conflict = seen & targets
        if conflict:
            message = (
                "ECS do_in_parallel() children write overlapping targets; "
                "deterministic last-write-wins is used."
            )
            if world.strict:
                raise SystemPlanError(message)
            world.record_ambiguity(message)
            return
        seen.update(targets)


def materialize_udf_arg(world: EcsWorld, arg: UdfArgument) -> MaterializedUdfArgument:
    """Convert a query proxy UDF argument into concrete entity views when needed."""
    if isinstance(arg, QueryProxy):
        spec = cast(QuerySpec, arg.spec)
        batch = world._active_python_access_batch
        if batch is not None and getattr(batch, "active", False):
            rows = batch.materialize_query(spec)
            if rows is not None:
                return list(rows)
        return world.match_query(spec)
    if isinstance(arg, Query):
        raise SystemPlanError(
            "ECS UDF arguments require system query proxies, not ecs.Query markers."
        )
    return arg
