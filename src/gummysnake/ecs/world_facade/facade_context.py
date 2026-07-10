"""Python-facing ECS world and entity APIs.

Rust owns canonical ECS entity/component/resource storage and physical system execution. This module
keeps the public Python API, schema conversion, logical-plan construction, and explicit Python UDF
integration at the boundary.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import fields, is_dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    get_type_hints,
)

from gummysnake.ecs.actions import Action, UdfArgument
from gummysnake.ecs.expressions import (
    Expression,
    FieldExpression,
    QueryProxy,
)
from gummysnake.ecs.runtime_views import (
    Entity,
    EntityMutation,
    EntityView,
    MutEntity,
    SystemHandle,
    _ScheduledSystem,
    _SystemSetConfig,
)
from gummysnake.ecs.scheduling_helpers import sorted_scheduled_systems, validate_group_name
from gummysnake.ecs.schema_helpers import (
    _schema_name,
    _storage_type_for,
    _validate_storage_value,
)
from gummysnake.ecs.specs import QuerySpec
from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.types import StorageType
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsStoredValue, EcsTag
from gummysnake.ecs.world_runtime import entities as entity_runtime
from gummysnake.ecs.world_runtime import query as query_runtime
from gummysnake.ecs.world_runtime import resources as resource_runtime
from gummysnake.ecs.world_runtime import state as state_runtime
from gummysnake.ecs.world_runtime import systems as system_runtime
from gummysnake.exceptions import ComponentSchemaError
from gummysnake.rust.ecs import create_ecs_world

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.context import SketchContext

ComponentT = TypeVar("ComponentT")
ResourceT = TypeVar("ResourceT")
