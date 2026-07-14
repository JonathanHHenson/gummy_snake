"""Rust ECS bridge validation through the mandatory canvas extension."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any, Protocol, cast

from gummysnake.exceptions import BackendCapabilityError
from gummysnake.rust.canvas import GUMMY_CANVAS_BUILD_COMMAND

EXPECTED_ECS_ABI_VERSION = 5

_REQUIRED_ECS_WORLD_METHODS = (
    "query_with_terms",
    "compiled_plan_count",
    "spatial_index_cache_len",
    "structural_revision",
    "field_revision",
    "diagnostics",
    "reset_diagnostics",
    "execute_compiled_plan",
    "execute_compiled_plans",
    "execute_compiled_plan_to_canvas",
    "execute_compiled_plans_to_canvas",
)


class _RustEcsWorld(Protocol):
    def allocate_entity(self) -> tuple[int, int]: ...

    def spawn_with_defaults(self, components: list[str]) -> tuple[int, int]: ...

    def despawn_entity(self, index: int, generation: int) -> None: ...

    def validate_entity(self, index: int, generation: int) -> None: ...

    def register_schema(self, name: str, fields: list[tuple[str, str]]) -> None: ...

    def alive_count(self) -> int: ...

    def schema_count(self) -> int: ...

    def schema_fingerprint(self) -> int: ...

    def compile_bridge_plan(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def execute_compiled_plan(self, handle: int, include_writes: bool = True) -> dict[str, Any]: ...

    def execute_compiled_plans(
        self, handles: list[int], include_writes: bool = True
    ) -> list[dict[str, Any]]: ...

    def execute_compiled_plan_to_canvas(
        self,
        handle: int,
        canvas: Any,
        matrix: Any,
        direct_fill_allowed: bool,
        include_writes: bool = True,
    ) -> dict[str, Any]: ...

    def execute_compiled_plans_to_canvas(
        self,
        handles: list[int],
        canvas: Any,
        matrix: Any,
        direct_fill_allowed: bool,
        include_writes: bool = True,
    ) -> list[dict[str, Any]]: ...

    def execute_compiled_plans_sequential(
        self, handles: list[int], include_writes: bool = True
    ) -> list[dict[str, Any]]: ...

    def warm_compiled_plan_spatial_indexes(self, handle: int) -> dict[str, Any]: ...

    def release_compiled_plan(self, handle: int) -> bool: ...

    def compiled_plan_count(self) -> int: ...

    def spatial_index_cache_len(self) -> int: ...

    def structural_revision(self) -> int: ...

    def field_revision(self) -> int: ...

    def set_input_state(self, name: str, value: Any, code: int | None = None) -> None: ...

    def execute_bridge_plan(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def archetype_count(self) -> int: ...

    def add_component_default(self, index: int, generation: int, component: str) -> None: ...

    def remove_component(self, index: int, generation: int, component: str) -> None: ...

    def add_tag(self, index: int, generation: int, tag: str) -> None: ...

    def remove_tag(self, index: int, generation: int, tag: str) -> None: ...

    def entity_components(self, index: int, generation: int) -> list[str]: ...

    def entity_tags(self, index: int, generation: int) -> list[str]: ...

    def set_field(
        self, index: int, generation: int, component: str, field: str, value: Any
    ) -> None: ...

    def set_field_f64_many(
        self, component: str, field: str, writes: list[tuple[int, int, float]]
    ) -> int: ...

    def get_field(self, index: int, generation: int, component: str, field: str) -> Any: ...

    def query_entities(self, components: list[str]) -> list[tuple[int, int]]: ...

    def query_with_terms(self, terms: list[tuple[str, str]]) -> list[tuple[int, int]]: ...

    def query_filtered(
        self,
        required_components: list[str],
        required_tags: list[str],
        excluded_components: list[str],
        excluded_tags: list[str],
    ) -> list[tuple[int, int]]: ...

    def query_component_fields(
        self,
        required_components: list[str],
        required_tags: list[str],
        component: str,
        fields: list[str],
    ) -> list[tuple[Any, ...]]: ...

    def insert_resource(self, name: str, fields: dict[str, Any]) -> None: ...

    def remove_resource(self, name: str) -> dict[str, Any]: ...

    def resource_field(self, name: str, field: str) -> Any: ...

    def set_resource_field(self, name: str, field: str, value: Any) -> None: ...

    def has_resource(self, name: str) -> bool: ...

    def resource_count(self) -> int: ...

    def resource_revision(self, name: str) -> int: ...

    def set_frame(self, frame: int) -> None: ...

    def emit_event(self, event_type: str, payload: Any) -> None: ...

    def read_events(self, event_type: str) -> list[dict[str, Any]]: ...

    def clear_events(self, event_type: str | None = None) -> None: ...

    def event_queue_len(self, event_type: str) -> int: ...

    def stage_spawn(self, components: list[str]) -> None: ...

    def stage_add_component(self, index: int, generation: int, component: str) -> None: ...

    def stage_remove_component(self, index: int, generation: int, component: str) -> None: ...

    def stage_despawn(self, index: int, generation: int) -> None: ...

    def apply_staged(self) -> None: ...

    def staged_command_count(self) -> int: ...

    def record_diagnostic_message(self, message: str) -> None: ...

    def reset_diagnostics(self) -> None: ...

    def diagnostics(self) -> dict[str, int | list[str]]: ...


class _RustEcsSpatialIndexRegistry(Protocol):
    def intern(
        self,
        target_query: list[str],
        dimensions: int,
        algorithm: str,
        update_policy: str,
        name: str | None = None,
    ) -> int: ...

    def release(self, id: int) -> None: ...

    def mark_stale(self, reason: str) -> None: ...

    def len(self) -> int: ...

    def get(self, id: int) -> dict[str, Any] | None: ...


class _EcsCanvasModule(Protocol):
    EcsWorld: type[_RustEcsWorld]
    EcsSpatialIndexRegistry: type[_RustEcsSpatialIndexRegistry]

    def ecs_abi_version(self) -> int: ...

    def ecs_health_check(self) -> str: ...


_loaded_canvas: ModuleType | None
_ECS_IMPORT_ERROR: ImportError | None

try:
    _loaded_canvas = import_module("gummysnake.rust._canvas")
except ImportError as exc:
    _loaded_canvas = None
    _ECS_IMPORT_ERROR = exc
else:
    _ECS_IMPORT_ERROR = None

_canvas = cast(_EcsCanvasModule | None, _loaded_canvas)


def ecs_import_error() -> ImportError | None:
    """Return the import error from loading the Rust ECS bridge, if any."""
    return _ECS_IMPORT_ERROR


def ecs_abi_version() -> int | None:
    """Return the ECS ABI version exposed by the Rust canvas runtime."""
    if _canvas is None:
        return None
    marker = getattr(_canvas, "ecs_abi_version", None)
    if not callable(marker):
        return None
    try:
        value: Any = marker()
    except Exception:
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def is_ecs_runtime_available() -> bool:
    """Return whether the required Rust ECS bridge is available and compatible."""
    try:
        require_ecs_runtime()
    except BackendCapabilityError:
        return False
    return True


def ecs_health_check() -> str:
    """Return a short status string from the Rust ECS bridge."""
    if _canvas is None:
        return "unavailable"
    health = getattr(_canvas, "ecs_health_check", None)
    if not callable(health):
        return "unavailable"
    try:
        return str(health())
    except Exception as exc:
        return f"unhealthy: {exc}"


def require_ecs_runtime() -> _EcsCanvasModule:
    """Return the Rust ECS bridge or raise a capability error with rebuild guidance."""
    if _canvas is None:
        raise BackendCapabilityError(
            "The Rust ECS runtime is unavailable because gummysnake.rust._canvas could not "
            f"be imported. Rebuild it with: {GUMMY_CANVAS_BUILD_COMMAND}"
        ) from _ECS_IMPORT_ERROR
    marker = ecs_abi_version()
    if marker != EXPECTED_ECS_ABI_VERSION:
        raise BackendCapabilityError(
            "The Rust ECS runtime ABI is missing or incompatible "
            f"(expected {EXPECTED_ECS_ABI_VERSION}, got {marker!r}). "
            f"Rebuild it with: {GUMMY_CANVAS_BUILD_COMMAND}"
        )
    health_check = getattr(_canvas, "ecs_health_check", None)
    if not callable(health_check):
        raise BackendCapabilityError(
            "The Rust ECS runtime is missing ecs_health_check(). "
            f"Rebuild it with: {GUMMY_CANVAS_BUILD_COMMAND}"
        )
    try:
        health = health_check()
    except Exception as exc:
        raise BackendCapabilityError(
            "The Rust ECS runtime failed its health check. "
            f"Rebuild it with: {GUMMY_CANVAS_BUILD_COMMAND}. Health check error: {exc}"
        ) from exc
    if not isinstance(health, str) or not health.strip() or health == "unavailable":
        raise BackendCapabilityError(
            "The Rust ECS runtime reported an unhealthy runtime state "
            f"({health!r}). Rebuild it with: {GUMMY_CANVAS_BUILD_COMMAND}"
        )
    world_type = getattr(_canvas, "EcsWorld", None)
    if not isinstance(world_type, type):
        raise BackendCapabilityError(
            "The Rust ECS runtime is missing EcsWorld. "
            f"Rebuild it with: {GUMMY_CANVAS_BUILD_COMMAND}"
        )
    missing_methods = [
        name
        for name in _REQUIRED_ECS_WORLD_METHODS
        if not callable(getattr(world_type, name, None))
    ]
    if missing_methods:
        raise BackendCapabilityError(
            "The Rust ECS runtime is missing required EcsWorld method(s) "
            f"{', '.join(missing_methods)}. Rebuild it with: {GUMMY_CANVAS_BUILD_COMMAND}"
        )
    return _canvas


def create_ecs_world() -> _RustEcsWorld:
    """Create a Rust-owned ECS world used by the Python ECS facade."""
    return require_ecs_runtime().EcsWorld()


def create_spatial_index_registry() -> _RustEcsSpatialIndexRegistry:
    """Create a Rust-owned registry for compiled ECS spatial indexes."""
    runtime = require_ecs_runtime()
    if not hasattr(runtime, "EcsSpatialIndexRegistry"):
        raise BackendCapabilityError(
            "The Rust ECS runtime is missing EcsSpatialIndexRegistry. "
            f"Rebuild it with: {GUMMY_CANVAS_BUILD_COMMAND}"
        )
    return runtime.EcsSpatialIndexRegistry()


__all__ = [
    "EXPECTED_ECS_ABI_VERSION",
    "create_ecs_world",
    "create_spatial_index_registry",
    "ecs_abi_version",
    "ecs_health_check",
    "ecs_import_error",
    "is_ecs_runtime_available",
    "require_ecs_runtime",
]
