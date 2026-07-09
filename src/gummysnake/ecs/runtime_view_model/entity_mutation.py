# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
"""Entity handles and Python runtime views for the ECS world."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, cast

from gummysnake.ecs.schema_helpers import _schema_name, _validate_storage_value
from gummysnake.ecs.systems import BuiltSystem
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag
from gummysnake.exceptions import MissingComponentError, SystemPlanError


def _copy_stored_value(value: object) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, tuple):
        return tuple(value)
    return copy.deepcopy(value)


if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld

ComponentT = TypeVar("ComponentT")
_ENTITY_MUTATION_COMPONENT_UNSET = object()


@dataclass(frozen=True)
class Entity:
    """Stable handle for an ECS entity stored in the Rust world."""

    index: int
    generation: int
    world_id: int

    def __class_getitem__(cls, item: object) -> EntityAnnotation:
        """Create an annotation marker such as ``ecs.Entity[Position]``."""
        return EntityAnnotation(item, mutable=False)

    def __getitem__(self, component_type: type[ComponentT]) -> ComponentT:
        """Explain why raw entity handles cannot read components directly.

        Args:
            component_type: Component type requested with subscription syntax.

        Returns:
            This method always raises because component access needs an ``EntityView``.
        """
        del component_type
        raise TypeError(
            "ecs.Entity[...] is a Python UDF/system annotation marker. Runtime component "
            "access is available on EntityView objects materialized by explicit Python "
            "ECS boundaries."
        )

    def add_component(self, component: DataclassInstance) -> None:
        """Reject direct mutation and point callers to ``EntityView``."""
        del component
        raise TypeError("Raw Entity handles cannot mutate components directly; use EntityView.")

    def remove_component(self, component_type: type[Any]) -> None:
        """Reject direct mutation and point callers to ``EntityView``."""
        del component_type
        raise TypeError("Raw Entity handles cannot mutate components directly; use EntityView.")

    def add_tag(self, tag: EcsTag) -> None:
        """Reject direct tag mutation and point callers to ``EntityView``."""
        del tag
        raise TypeError("Raw Entity handles cannot mutate tags directly; use EntityView.")

    def remove_tag(self, tag: EcsTag) -> None:
        """Reject direct tag mutation and point callers to ``EntityView``."""
        del tag
        raise TypeError("Raw Entity handles cannot mutate tags directly; use EntityView.")

    def despawn(self) -> None:
        """Reject direct despawning and point callers to ``EntityView``."""
        raise TypeError("Raw Entity handles cannot despawn directly; use EntityView.")


@dataclass(frozen=True)
class EntityAnnotation:
    """Annotation marker created by ``ecs.Entity[Component]``.

    The marker is consumed when planning explicit Python ECS boundaries; raw entity
    handles still need an ``EntityView`` before component data can be read or changed.
    """

    component_type: object
    mutable: bool = False


@dataclass(frozen=True)
class EntityMutation:
    """Describe which component changes a Python ECS boundary may perform."""

    component_type: object = _ENTITY_MUTATION_COMPONENT_UNSET
    add: bool = False
    remove: bool = False
    update: bool = True

    def __post_init__(self) -> None:
        if self.component_type is _ENTITY_MUTATION_COMPONENT_UNSET:
            raise SystemPlanError(
                "EntityMutation must be parameterized as ecs.EntityMutation[Component](...)."
            )
        if not (self.add or self.remove or self.update):
            raise SystemPlanError(
                "EntityMutation must allow at least one of add, remove, or update."
            )

    def __class_getitem__(cls, item: object) -> _EntityMutationAlias:
        """Create a mutation descriptor factory for one component type."""
        return _EntityMutationAlias(item)


@dataclass(frozen=True)
class _EntityMutationAlias:
    component_type: object

    def __call__(
        self, *, add: bool = False, remove: bool = False, update: bool = True
    ) -> EntityMutation:
        return EntityMutation(self.component_type, add=add, remove=remove, update=update)


class MutEntity:
    """Deprecated mutable entity annotation marker."""

    def __class_getitem__(cls, item: object) -> EntityAnnotation:
        """Raise with migration guidance for old ``ecs.MutEntity[...]`` annotations."""
        raise SystemPlanError(
            "ecs.MutEntity has been replaced by ecs.Entity[...] plus EntityMutation[...] "
            "metadata on @ecs.udf or @ecs.system."
        )

    def __getitem__(self, component_type: type[ComponentT]) -> ComponentT:
        """Raise with migration guidance for old runtime ``MutEntity`` access."""
        raise TypeError(
            "ecs.MutEntity is deprecated; use ecs.Entity[...] and EntityMutation metadata."
        )
