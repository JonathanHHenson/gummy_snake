"""Public builder functions for ECS spatial relations."""

from __future__ import annotations

from gummysnake.ecs.expressions import QueryProxy, ensure_expr
from gummysnake.exceptions import SystemPlanError

from .config import FallbackPolicy, HashGrid, PairPolicy, SpatialAlgorithm, _default_cell_size
from .relations import SpatialAabb, SpatialPoint, SpatialRelation
from .runtime import _validate_relation


def point2(x: object, y: object) -> SpatialPoint:
    """Create a lazy 2D point from two ECS expressions or values.

    Args:
        x: X coordinate expression or value.
        y: Y coordinate expression or value.

    Returns:
        A ``SpatialPoint`` that can be used with ``neighbors()``, ``join()``, or ``aabb2()``.
    """

    return SpatialPoint((ensure_expr(x), ensure_expr(y)))


def point3(x: object, y: object, z: object) -> SpatialPoint:
    """Create a lazy 3D point from three ECS expressions or values.

    Args:
        x: X coordinate expression or value.
        y: Y coordinate expression or value.
        z: Z coordinate expression or value.

    Returns:
        A ``SpatialPoint`` that can be used with ``neighbors()``, ``join()``, or ``aabb3()``.
    """

    return SpatialPoint((ensure_expr(x), ensure_expr(y), ensure_expr(z)))


def aabb2(min_x: object, min_y: object, max_x: object, max_y: object) -> SpatialAabb:
    """Create a lazy 2D axis-aligned bounding box.

    Args:
        min_x: Minimum x coordinate expression or value.
        min_y: Minimum y coordinate expression or value.
        max_x: Maximum x coordinate expression or value.
        max_y: Maximum y coordinate expression or value.

    Returns:
        A ``SpatialAabb`` suitable for ``overlaps()``.
    """

    return SpatialAabb(point2(min_x, min_y), point2(max_x, max_y))


def aabb3(
    min_x: object,
    min_y: object,
    min_z: object,
    max_x: object,
    max_y: object,
    max_z: object,
) -> SpatialAabb:
    """Create a lazy 3D axis-aligned bounding box.

    Args:
        min_x: Minimum x coordinate expression or value.
        min_y: Minimum y coordinate expression or value.
        min_z: Minimum z coordinate expression or value.
        max_x: Maximum x coordinate expression or value.
        max_y: Maximum y coordinate expression or value.
        max_z: Maximum z coordinate expression or value.

    Returns:
        A ``SpatialAabb`` suitable for ``overlaps()``.
    """

    return SpatialAabb(point3(min_x, min_y, min_z), point3(max_x, max_y, max_z))


def neighbors(
    query: object,
    *,
    position: SpatialPoint,
    radius: object,
    algorithm: SpatialAlgorithm | None = None,
    include_self: bool = False,
    allow_fallback: FallbackPolicy = None,
    name: str | None = None,
) -> SpatialRelation:
    """Create a relation from each query row to nearby rows of the same query.

    Args:
        query: ``ecs.Query`` system parameter whose rows should search for neighbors.
        position: Lazy point expression describing each row's position.
        radius: Search radius expression or value.
        algorithm: Optional spatial index configuration. A hash grid is chosen by default.
        include_self: Include the origin entity as a possible match when true.
        allow_fallback: Override whether explicit Python boundaries may materialize this relation.
        name: Optional label used in explain output and diagnostics.

    Returns:
        A lazy ``SpatialRelation`` that can be filtered or aggregated inside an ECS system.
    """

    origin = _as_query_proxy(query, "neighbors query")
    if not isinstance(position, SpatialPoint):
        raise SystemPlanError(
            "spatial.neighbors() position must be spatial.point2(...) or point3(...)."
        )
    item = QueryProxy(f"{origin.name}.item", origin.spec)
    return _validated_relation(
        SpatialRelation(
            origin=origin,
            item=item,
            origin_position=position,
            target_position=position.replace_query(origin, item),
            radius=ensure_expr(radius),
            algorithm=algorithm
            or HashGrid(_default_cell_size(radius), dimensions=position.dimensions),
            include_self=include_self,
            allow_fallback=allow_fallback,
            name=name,
        )
    )


def join(
    origin: object,
    target: object,
    *,
    origin_position: SpatialPoint,
    target_position: SpatialPoint,
    radius: object | None = None,
    bounds: object | None = None,
    algorithm: SpatialAlgorithm | None = None,
    include_self: bool = False,
    allow_fallback: FallbackPolicy = None,
    name: str | None = None,
) -> SpatialRelation:
    """Create a relation from origin query rows to nearby target query rows.

    Args:
        origin: ``ecs.Query`` system parameter that starts each lookup.
        target: ``ecs.Query`` system parameter searched for matching rows.
        origin_position: Lazy point expression for each origin row.
        target_position: Lazy point expression for each target row.
        radius: Optional search radius expression or value. ``None`` means use the index
            broad phase.
        bounds: Reserved compatibility value for bounds-based relations.
        algorithm: Optional spatial index configuration. A hash grid is chosen by default.
        include_self: Include the same entity as a possible match when the queries overlap.
        allow_fallback: Override whether explicit Python boundaries may materialize this relation.
        name: Optional label used in explain output and diagnostics.

    Returns:
        A lazy ``SpatialRelation`` that can be filtered or aggregated inside an ECS system.
    """

    origin_query = _as_query_proxy(origin, "join origin")
    target_query = _as_query_proxy(target, "join target")
    if not isinstance(origin_position, SpatialPoint) or not isinstance(
        target_position, SpatialPoint
    ):
        raise SystemPlanError(
            "spatial.join() positions must be spatial.point2(...) or point3(...)."
        )
    return _validated_relation(
        SpatialRelation(
            origin=origin_query,
            item=target_query,
            origin_position=origin_position,
            target_position=target_position,
            radius=None if radius is None else ensure_expr(radius),
            bounds=bounds,
            algorithm=algorithm
            or HashGrid(_default_cell_size(radius), dimensions=origin_position.dimensions),
            include_self=include_self,
            allow_fallback=allow_fallback,
            name=name,
        )
    )


def overlaps(
    origin: object,
    target: object,
    *,
    origin_bounds: SpatialAabb,
    target_bounds: SpatialAabb,
    algorithm: SpatialAlgorithm | None = None,
    include_self: bool = False,
    pair_policy: PairPolicy = "all",
    allow_fallback: FallbackPolicy = None,
    name: str | None = None,
) -> SpatialRelation:
    """Create a relation for rows whose axis-aligned bounding boxes overlap.

    Args:
        origin: ``ecs.Query`` system parameter that starts each lookup.
        target: ``ecs.Query`` system parameter searched for overlapping rows.
        origin_bounds: Lazy bounds expression for each origin row.
        target_bounds: Lazy bounds expression for each target row.
        algorithm: Optional spatial index configuration. A hash grid is chosen by default.
        include_self: Include the same entity as a possible match when the queries overlap.
        pair_policy: ``"all"`` for every ordered pair, or ``"unique_unordered"`` once per pair.
        allow_fallback: Override whether explicit Python boundaries may materialize this relation.
        name: Optional label used in explain output and diagnostics.

    Returns:
        A lazy ``SpatialRelation`` that can be filtered or aggregated inside an ECS system.
    """

    origin_query = _as_query_proxy(origin, "overlaps origin")
    target_query = _as_query_proxy(target, "overlaps target")
    if not isinstance(origin_bounds, SpatialAabb) or not isinstance(target_bounds, SpatialAabb):
        raise SystemPlanError("spatial.overlaps() bounds must be spatial.aabb2(...) or aabb3(...).")
    if pair_policy not in {"all", "unique_unordered"}:
        raise SystemPlanError("spatial.overlaps() pair_policy must be 'all' or 'unique_unordered'.")
    return _validated_relation(
        SpatialRelation(
            origin=origin_query,
            item=target_query,
            origin_position=origin_bounds.center(),
            target_position=target_bounds.center(),
            origin_bounds=origin_bounds,
            target_bounds=target_bounds,
            algorithm=algorithm or HashGrid(1.0, dimensions=origin_bounds.dimensions),
            include_self=include_self,
            allow_fallback=allow_fallback,
            name=name,
            pair_policy=pair_policy,
        )
    )


def _as_query_proxy(value: object, role: str) -> QueryProxy:
    if not isinstance(value, QueryProxy):
        raise SystemPlanError(f"spatial.{role} must be an ecs.Query system parameter.")
    return value


def _validated_relation(relation: SpatialRelation) -> SpatialRelation:
    _validate_relation(relation)
    return relation
