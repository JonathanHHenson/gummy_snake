"""Configuration objects for ECS spatial relation algorithms."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Dimensions = Literal[2, 3]
UpdatePolicy = Literal["auto", "rebuild_each_use", "rebuild_each_frame", "incremental"]
OutOfBoundsPolicy = Literal["overflow", "error"]
PairPolicy = Literal["all", "unique_unordered"]


@dataclass(frozen=True)
class Bounds2D:
    """Axis-aligned 2D bounds for spatial indexes.

    Args:
        min_x: Smallest x coordinate included in the bounds.
        min_y: Smallest y coordinate included in the bounds.
        max_x: Largest x coordinate included in the bounds.
        max_y: Largest y coordinate included in the bounds.
    """

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        _validate_finite_bounds((self.min_x, self.min_y, self.max_x, self.max_y), 2)
        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError("Bounds2D minimum values must be <= maximum values.")


@dataclass(frozen=True)
class Bounds3D:
    """Axis-aligned 3D bounds for spatial indexes.

    Args:
        min_x: Smallest x coordinate included in the bounds.
        min_y: Smallest y coordinate included in the bounds.
        min_z: Smallest z coordinate included in the bounds.
        max_x: Largest x coordinate included in the bounds.
        max_y: Largest y coordinate included in the bounds.
        max_z: Largest z coordinate included in the bounds.
    """

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def __post_init__(self) -> None:
        _validate_finite_bounds(
            (self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z), 3
        )
        if self.min_x > self.max_x or self.min_y > self.max_y or self.min_z > self.max_z:
            raise ValueError("Bounds3D minimum values must be <= maximum values.")


@dataclass(frozen=True)
class HashGrid:
    """Uniform-grid spatial index for nearby point queries.

    Args:
        cell_size: Width of each grid cell in world units. Use a value near the query radius.
        dimensions: Set to ``2`` or ``3`` when the relation cannot infer dimensionality.
        update: Cache update policy used by the Rust ECS executor.
    """

    cell_size: float
    dimensions: Dimensions | None = None
    update: UpdatePolicy = "auto"

    kind: str = "hash_grid"

    def __post_init__(self) -> None:
        _validate_positive_finite(self.cell_size, "HashGrid.cell_size")
        _validate_dimensions(self.dimensions)
        _validate_update(self.update)


@dataclass(frozen=True)
class Quadtree:
    """2D tree spatial index for clustered point or bounds queries.

    Args:
        bounds: World-space rectangle covered by the tree.
        capacity: Maximum number of records in a node before it subdivides.
        max_depth: Maximum subdivision depth.
        update: Cache update policy used by the Rust ECS executor.
        out_of_bounds: How records outside ``bounds`` are handled.
    """

    bounds: Bounds2D
    capacity: int = 16
    max_depth: int = 16
    update: UpdatePolicy = "auto"
    out_of_bounds: OutOfBoundsPolicy = "overflow"

    kind: str = "quadtree"
    dimensions: Dimensions = 2

    def __post_init__(self) -> None:
        _validate_tree_config(self.capacity, self.max_depth, self.update, self.out_of_bounds)


@dataclass(frozen=True)
class Octree:
    """3D tree spatial index for clustered point or bounds queries.

    Args:
        bounds: World-space box covered by the tree.
        capacity: Maximum number of records in a node before it subdivides.
        max_depth: Maximum subdivision depth.
        update: Cache update policy used by the Rust ECS executor.
        out_of_bounds: How records outside ``bounds`` are handled.
    """

    bounds: Bounds3D
    capacity: int = 16
    max_depth: int = 12
    update: UpdatePolicy = "auto"
    out_of_bounds: OutOfBoundsPolicy = "overflow"

    kind: str = "octree"
    dimensions: Dimensions = 3

    def __post_init__(self) -> None:
        _validate_tree_config(self.capacity, self.max_depth, self.update, self.out_of_bounds)


@dataclass(frozen=True)
class HilbertCurve:
    """Spatial index that sorts records by Hilbert curve position.

    Args:
        bounds: 2D or 3D world bounds used to normalize coordinates.
        bits: Number of Hilbert bits per axis. Higher values preserve more coordinate detail.
        dimensions: Optional explicit dimensionality; it must match ``bounds`` when provided.
        update: Cache update policy used by the Rust ECS executor.
        out_of_bounds: How records outside ``bounds`` are handled.
    """

    bounds: Bounds2D | Bounds3D
    bits: int = 16
    dimensions: Dimensions | None = None
    update: UpdatePolicy = "auto"
    out_of_bounds: OutOfBoundsPolicy = "overflow"

    kind: str = "hilbert_curve"

    def __post_init__(self) -> None:
        inferred = 2 if isinstance(self.bounds, Bounds2D) else 3
        dimensions = inferred if self.dimensions is None else self.dimensions
        _validate_dimensions(dimensions)
        if dimensions != inferred:
            raise ValueError("HilbertCurve dimensions must match the provided bounds object.")
        if self.bits <= 0 or self.bits > 31:
            raise ValueError("HilbertCurve.bits must be in the range 1..31.")
        _validate_update(self.update)
        _validate_out_of_bounds(self.out_of_bounds)


SpatialAlgorithm = HashGrid | Quadtree | Octree | HilbertCurve


def _default_cell_size(radius: object | None) -> float:
    if isinstance(radius, int | float):
        _validate_positive_finite(float(radius), "spatial radius/cell_size")
        return float(radius) if float(radius) > 0 else 1.0
    return 1.0


def _validate_dimensions(dimensions: int | None) -> None:
    if dimensions is not None and dimensions not in {2, 3}:
        raise ValueError("Spatial dimensions must be 2, 3, or None for inference.")


def _validate_update(update: str) -> None:
    if update not in {"auto", "rebuild_each_use", "rebuild_each_frame", "incremental"}:
        raise ValueError(
            "Spatial update must be 'auto', 'rebuild_each_use', 'rebuild_each_frame', "
            "or 'incremental'."
        )


def _validate_tree_config(capacity: int, max_depth: int, update: str, out_of_bounds: str) -> None:
    if capacity <= 0:
        raise ValueError("Spatial tree capacity must be positive.")
    if max_depth <= 0:
        raise ValueError("Spatial tree max_depth must be positive.")
    _validate_update(update)
    _validate_out_of_bounds(out_of_bounds)


def _validate_out_of_bounds(out_of_bounds: str) -> None:
    if out_of_bounds not in {"overflow", "error"}:
        raise ValueError("out_of_bounds must be 'overflow' or 'error'.")


def _validate_positive_finite(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive.")


def _validate_positive_or_zero_finite(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative.")


def _validate_finite_bounds(values: tuple[float, ...], dimensions: int) -> None:
    if len(values) != dimensions * 2 or any(not math.isfinite(value) for value in values):
        raise ValueError("Spatial bounds must contain finite min/max coordinates.")
