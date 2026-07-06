"""Query, resource, field, and entity expression proxies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

from gummysnake.ecs.expressions.core import Expression, ExpressionContext

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.actions import EntityIteratorSource
    from gummysnake.ecs.specs import Query, QuerySpec
    from gummysnake.ecs.world import EcsWorld, EntityView


@dataclass(frozen=True, eq=False)
class QueryProxy:
    name: str
    spec: QuerySpec | type[Query]

    @property
    def ctx(self) -> QueryProxy:
        return self

    @property
    def entity(self) -> EntityExpression:
        return EntityExpression(self)

    def __getitem__(self, component_type: type[Any]) -> ComponentExpressionProxy:
        return ComponentExpressionProxy(self, component_type)

    def as_iter(self, *component_types: type[Any]) -> EntityIteratorSource:
        """Use each matched entity as an ``ecs.for_each`` source.

        Args:
            component_types: Component classes to materialize; each must be in this query.

        Returns:
            An iterable source for ``ecs.for_each``.
        """

        from gummysnake.ecs.actions import EntityIteratorSource
        from gummysnake.ecs.specs import QuerySpec
        from gummysnake.exceptions import SystemPlanError

        if not isinstance(self.spec, QuerySpec):
            raise SystemPlanError(
                "Query.as_iter() requires a concrete ecs.Query[...] specification."
            )
        available = {term for term in self.spec.terms if isinstance(term, type)}
        for component_type in component_types:
            if component_type not in available:
                raise SystemPlanError(
                    f"Query.as_iter() projection {component_type.__name__} is not present "
                    f"in query {self.name!r}."
                )
        return EntityIteratorSource(self, tuple(component_types))

    def __repr__(self) -> str:
        return f"QueryProxy({self.name})"


@dataclass(frozen=True, eq=False)
class ResourceProxy:
    name: str
    resource_type: type[Any]
    mutable: bool = False

    def __getitem__(self, resource_type: type[Any]) -> ComponentExpressionProxy:
        if resource_type is not self.resource_type:
            raise KeyError(
                f"Resource parameter {self.name!r} was declared for "
                f"{self.resource_type.__name__}, not {resource_type.__name__}."
            )
        return ComponentExpressionProxy(self, resource_type)

    def __repr__(self) -> str:
        mode = "ResMut" if self.mutable else "Res"
        return f"{mode}({self.name})"


@dataclass(frozen=True, eq=False)
class ComponentExpressionProxy:
    source: QueryProxy | ResourceProxy
    component_type: type[Any]

    def __getattr__(self, field_name: str) -> FieldExpression:
        if field_name.startswith("__"):
            raise AttributeError(field_name)
        return FieldExpression(self.source, self.component_type, field_name)


@dataclass(frozen=True, eq=False)
class FieldExpression(Expression):
    source: QueryProxy | ResourceProxy
    component_type: type[Any]
    field_name: str

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> Any:
        if isinstance(self.source, QueryProxy):
            entity = ctx[self.source]
            return getattr(entity[self.component_type], self.field_name)
        value = world.get_resource(self.component_type)
        return getattr(value, self.field_name)

    def set_value(self, ctx: ExpressionContext, world: EcsWorld, value: Any) -> None:
        if isinstance(self.source, QueryProxy):
            entity = ctx[self.source]
            setattr(entity[self.component_type], self.field_name, value)
            return
        if not self.source.mutable:
            from gummysnake.exceptions import SystemPlanError

            raise SystemPlanError(
                f"Resource parameter {self.source.name!r} is read-only; use ecs.ResMut[...] "
                f"to write {self.component_type.__name__}.{self.field_name}."
            )
        resource = world.get_resource(self.component_type)
        setattr(resource, self.field_name, value)

    def set_to(self, value: object) -> None:
        """Append a logical field assignment to the active ECS system build block.

        Args:
            value: Python value or lazy ECS expression to store in the field.
        """

        self._ensure_writable()
        from gummysnake.ecs.actions import append_action, set

        append_action(
            set(self, value), operation=f"{self.component_type.__name__}.{self.field_name}.set_to()"
        )

    def increase_by(self, amount: object) -> None:
        """Append ``field = field + amount`` to the active ECS system build block.

        Args:
            amount: Numeric value or expression to add to the current field value.
        """

        self._ensure_numeric_update(amount, "increase_by")
        self.set_to(self + amount)

    def decrease_by(self, amount: object) -> None:
        """Append ``field = field - amount`` to the active ECS system build block.

        Args:
            amount: Numeric value or expression to subtract from the current field value.
        """

        self._ensure_numeric_update(amount, "decrease_by")
        self.set_to(self - amount)

    def _ensure_writable(self) -> None:
        from gummysnake.exceptions import SystemPlanError

        if isinstance(self.source, ResourceProxy) and not self.source.mutable:
            raise SystemPlanError(
                f"Resource parameter {self.source.name!r} is read-only; use "
                f"ecs.ResMut[{self.component_type.__name__}] to write "
                f"{self.component_type.__name__}.{self.field_name}."
            )

    def _ensure_numeric_update(self, amount: object, method: str) -> None:
        from gummysnake.exceptions import SystemPlanError

        if not _field_annotation_is_numeric(self.component_type, self.field_name):
            raise SystemPlanError(
                f"{self.component_type.__name__}.{self.field_name}.{method}() requires "
                "a numeric field."
            )
        if isinstance(amount, bool | str):
            raise SystemPlanError(f"{method}() requires a numeric expression or literal amount.")


@dataclass(frozen=True, eq=False)
class EntityExpression(Expression):
    query: QueryProxy

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> EntityView:
        del world
        return ctx[self.query]

    def add_component(self, component: object | type[Any]) -> None:
        """Add a component to every entity matched by this query.

        Args:
            component: Component class to add, or a component instance whose values should be used.
        """

        from gummysnake.ecs.actions import add_component_action, append_action

        append_action(
            add_component_action(self, component), operation="query.entity.add_component()"
        )

    def remove_component(self, component_type: type[Any]) -> None:
        """Remove a component from every entity matched by this query.

        Args:
            component_type: Component class to remove.
        """

        from gummysnake.ecs.actions import append_action, remove_component_action

        append_action(
            remove_component_action(self, component_type),
            operation="query.entity.remove_component()",
        )

    def add_tag(self, tag: object) -> None:
        """Add a tag to every entity matched by this query.

        Args:
            tag: Tag value to add.
        """

        from gummysnake.ecs.actions import add_tag_action, append_action

        append_action(add_tag_action(self, tag), operation="query.entity.add_tag()")

    def remove_tag(self, tag: object) -> None:
        """Remove a tag from every entity matched by this query.

        Args:
            tag: Tag value to remove.
        """

        from gummysnake.ecs.actions import append_action, remove_tag_action

        append_action(remove_tag_action(self, tag), operation="query.entity.remove_tag()")

    def despawn(self) -> None:
        """Despawn every entity matched by this query."""

        from gummysnake.ecs.actions import append_action, despawn_action

        append_action(despawn_action(self), operation="query.entity.despawn()")


def _field_annotation_is_numeric(component_type: type[Any], field_name: str) -> bool:
    try:
        annotations = get_type_hints(component_type, include_extras=True)
    except Exception:
        annotations = getattr(component_type, "__annotations__", {})
    annotation = annotations.get(field_name)
    if annotation is None:
        return True
    origin = get_origin(annotation)
    if origin is Annotated:
        base, *metadata = get_args(annotation)
        if any(getattr(item, "python_type", None) in {int, float} for item in metadata):
            return True
        annotation = base
        origin = get_origin(annotation)
    if annotation in {int, float}:
        return True
    if origin in {tuple, list}:
        return False
    return False


__all__ = [
    "ComponentExpressionProxy",
    "EntityExpression",
    "FieldExpression",
    "QueryProxy",
    "ResourceProxy",
]
