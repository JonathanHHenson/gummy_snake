"""Private batched access helpers for explicit Python ECS runtime boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.runtime_views import Entity, EntityView, _copy_stored_value
from gummysnake.ecs.schema_helpers import _schema_name, _tag_name, _validate_storage_value
from gummysnake.ecs.specs import ChangeTerm, QuerySpec, TagTerm, WithoutTerm
from gummysnake.ecs.world_helpers import _component_key
from gummysnake.exceptions import SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld

_BATCH_MISS = object()


@dataclass(frozen=True)
class _BatchedQuery:
    components: tuple[type[Any], ...]
    component_names: tuple[str, ...]
    tags: tuple[str, ...]
    entities: tuple[Entity, ...]


def _batched_component_init(
    self: Any,
    batch: PythonEcsAccessBatch,
    entity: Entity,
    component_type: type[Any],
    row: list[Any],
) -> None:
    object.__setattr__(self, "_batch", batch)
    object.__setattr__(self, "_entity", entity)
    object.__setattr__(self, "_component_type", component_type)
    object.__setattr__(self, "_row", row)


def _make_proxy_getter(field_index: int) -> Any:
    def getter(self: Any) -> object:
        return self._row[field_index]

    return getter


def _make_proxy_setter(field_index: int, field_name: str) -> Any:
    def setter(self: Any, value: object) -> None:
        self._batch.set_field_by_index(
            self._entity,
            self._component_type,
            field_name,
            field_index,
            value,
            self._row,
        )

    return setter


def _batched_component_snapshot(self: Any) -> object:
    self._batch.flush()
    return self._batch._world.component_snapshot(self._entity, self._component_type)


def _batched_component_repr(self: Any) -> str:
    component_name = self._component_type.__name__
    return f"ComponentView({component_name}@{self._entity.index}:{self._entity.generation})"


class PythonEcsAccessBatch:
    """Batch field reads/writes within one explicit Python ECS boundary."""

    def __init__(self, world: EcsWorld) -> None:
        self._world = world
        self._queries: dict[int, _BatchedQuery] = {}
        self._next_query_key = 1
        self._component_cache: dict[tuple[int, type[Any]], dict[tuple[int, int], list[Any]]] = {}
        self._field_orders: dict[tuple[int, type[Any]], tuple[str, ...]] = {}
        self._field_indices: dict[tuple[int, type[Any]], dict[str, int]] = {}
        self._proxy_types: dict[type[Any], type[Any]] = {}
        self._dirty: dict[tuple[type[Any], str], dict[Entity, object]] = {}
        self._active = True
        self._needs_invalidate = False

    @property
    def active(self) -> bool:
        """Return whether this batch still owns live cached views."""

        return self._active

    def materialize_query(self, spec: QuerySpec) -> tuple[EntityView, ...] | None:
        """Materialize a query if it can use the fast batched path."""

        parsed = self._parse_fast_query(spec)
        if parsed is None:
            return None
        components, component_names, tags = parsed
        rows = self._world._rust.query_filtered(list(component_names), list(tags), [], [])
        entities = tuple(
            Entity(index, generation, self._world._world_id) for index, generation in rows
        )
        query_key = self._next_query_key
        self._next_query_key += 1
        self._queries[query_key] = _BatchedQuery(components, component_names, tags, entities)
        return tuple(
            EntityView(self._world, entity, access_batch=self, query_key=query_key)
            for entity in entities
        )

    def _parse_fast_query(
        self, spec: QuerySpec
    ) -> tuple[tuple[type[Any], ...], tuple[str, ...], tuple[str, ...]] | None:
        components: list[type[Any]] = []
        tags: list[str] = []
        for term in spec.terms:
            if isinstance(term, TagTerm):
                tags.append(_tag_name(term.value))
            elif isinstance(term, ChangeTerm | WithoutTerm):
                return None
            elif isinstance(term, type):
                self._world.validate_schema(term)
                if term not in components:
                    components.append(term)
            else:
                raise SystemPlanError(f"Unsupported ECS query term {term!r}.")
        if not components:
            return None
        return (
            tuple(components),
            tuple(_schema_name(component) for component in components),
            tuple(tags),
        )

    def component_proxy(
        self, query_key: int | None, entity: Entity, component_type: type[Any]
    ) -> object:
        """Return a generated slotted component proxy or ``_BATCH_MISS``."""

        if not self._active or query_key is None:
            return _BATCH_MISS
        row = self._component_row(query_key, entity, component_type)
        if row is None:
            return _BATCH_MISS
        proxy_type = self._proxy_type(component_type)
        return proxy_type(self, entity, component_type, row)

    def get_field(
        self,
        query_key: int | None,
        entity: Entity,
        component_type: type[Any],
        field_name: str,
    ) -> object:
        """Read a cached field value or return ``_BATCH_MISS`` for fallback."""

        if not self._active or query_key is None:
            return _BATCH_MISS
        row = self._component_row(query_key, entity, component_type)
        if row is None:
            return _BATCH_MISS
        field_index = self._field_indices[(query_key, component_type)].get(field_name)
        if field_index is None:
            return _BATCH_MISS
        return row[field_index]

    def set_field(
        self,
        query_key: int | None,
        entity: Entity,
        component_type: type[Any],
        field_name: str,
        value: object,
    ) -> bool:
        """Buffer a field write. Returns ``False`` when the caller should fall back."""

        if not self._active or query_key is None:
            return False
        row = self._component_row(query_key, entity, component_type)
        if row is None:
            return False
        field_index = self._field_indices[(query_key, component_type)].get(field_name)
        if field_index is None:
            return False
        self.set_field_by_index(entity, component_type, field_name, field_index, value, row)
        return True

    def set_field_by_index(
        self,
        entity: Entity,
        component_type: type[Any],
        field_name: str,
        field_index: int,
        value: object,
        row: list[Any],
    ) -> None:
        """Validate and buffer a field write for a cached row list."""

        schema = self._world._schemas[component_type]
        storage_type = schema[field_name]
        _validate_storage_value(component_type, field_name, value, storage_type)
        stored = _copy_stored_value(value)
        row[field_index] = stored
        self._dirty.setdefault((component_type, field_name), {})[entity] = stored
        self._world._diagnostics["ecs_rows_updated"] += 1
        self._world._changed_components.add(_component_key(entity, component_type))
        self._needs_invalidate = True

    def _component_row(
        self, query_key: int, entity: Entity, component_type: type[Any]
    ) -> list[Any] | None:
        query = self._queries.get(query_key)
        if query is None or component_type not in query.components:
            return None
        cache_key = (query_key, component_type)
        rows = self._component_cache.get(cache_key)
        if rows is None:
            rows = self._load_component_rows(query_key, query, component_type)
            self._component_cache[cache_key] = rows
        return rows.get((entity.index, entity.generation))

    def _load_component_rows(
        self, query_key: int, query: _BatchedQuery, component_type: type[Any]
    ) -> dict[tuple[int, int], list[Any]]:
        fields = tuple(self._world._schemas[component_type])
        cache_key = (query_key, component_type)
        self._field_orders[cache_key] = fields
        self._field_indices[cache_key] = {field: index for index, field in enumerate(fields)}
        raw_rows = self._world._rust.query_component_fields(
            list(query.component_names),
            list(query.tags),
            _schema_name(component_type),
            list(fields),
        )
        out: dict[tuple[int, int], list[Any]] = {}
        for entity, values in zip(query.entities, raw_rows, strict=True):
            out[(entity.index, entity.generation)] = list(values)
        return out

    def _proxy_type(self, component_type: type[Any]) -> type[Any]:
        cached = self._proxy_types.get(component_type)
        if cached is not None:
            return cached
        namespace: dict[str, object] = {
            "__slots__": ("_batch", "_entity", "_component_type", "_row"),
            "__module__": __name__,
            "__init__": _batched_component_init,
            "snapshot": _batched_component_snapshot,
            "__repr__": _batched_component_repr,
        }
        for field_index, field_name in enumerate(self._world._schemas[component_type]):
            namespace[field_name] = property(
                _make_proxy_getter(field_index),
                _make_proxy_setter(field_index, field_name),
            )
        proxy_type = type(f"_Batched{component_type.__name__}View", (), namespace)
        self._proxy_types[component_type] = proxy_type
        return proxy_type

    def flush(self) -> None:
        """Write buffered values back to Rust storage."""

        if not self._dirty:
            return
        dirty = self._dirty
        self._dirty = {}
        for (component_type, field_name), writes in dirty.items():
            schema_name = _schema_name(component_type)
            storage_type = self._world._schemas[component_type][field_name]
            if storage_type.name in {"Float32", "Float64"}:
                payload = [
                    (entity.index, entity.generation, float(cast(int | float, value)))
                    for entity, value in writes.items()
                ]
                self._world._rust.set_field_f64_many(schema_name, field_name, payload)
                continue
            for entity, value in writes.items():
                self._world._rust.set_field(
                    entity.index,
                    entity.generation,
                    schema_name,
                    field_name,
                    _copy_stored_value(value),
                )
        if self._needs_invalidate:
            self._needs_invalidate = False
            self._world._invalidate_spatial_indexes()

    def close(self) -> None:
        """Disable cached access for views that escape the Python boundary."""

        self._active = False


__all__ = ["PythonEcsAccessBatch", "_BATCH_MISS"]
