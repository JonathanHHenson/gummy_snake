"""Generic ECS spatial relation APIs.

The public API models spatial work as lazy relations over ECS query rows. Scheduled
systems serialize these relations into Rust physical plans, where hash-grid,
quadtree, octree, and 2D Hilbert backends execute behind the shared spatial trait.
"""

from __future__ import annotations

from .builders import aabb2, aabb3, join, neighbors, overlaps, point2, point3
from .config import (
    Bounds2D,
    Bounds3D,
    HashGrid,
    HilbertCurve,
    Octree,
    Quadtree,
)
from .config import (
    Dimensions as Dimensions,
)
from .config import (
    OutOfBoundsPolicy as OutOfBoundsPolicy,
)
from .config import (
    PairPolicy as PairPolicy,
)
from .config import (
    SpatialAlgorithm as SpatialAlgorithm,
)
from .config import (
    UpdatePolicy as UpdatePolicy,
)
from .relation_model import (
    SpatialAabb,
    SpatialAggregateExpression,
    SpatialPoint,
    SpatialRelation,
)
from .relation_model import (
    SpatialDeltaProxy as SpatialDeltaProxy,
)
from .relation_model import (
    SpatialMetadataExpression as SpatialMetadataExpression,
)

__all__ = [
    "Bounds2D",
    "Bounds3D",
    "HashGrid",
    "HilbertCurve",
    "Octree",
    "Quadtree",
    "SpatialAabb",
    "SpatialAggregateExpression",
    "SpatialPoint",
    "SpatialRelation",
    "aabb2",
    "aabb3",
    "join",
    "neighbors",
    "overlaps",
    "point2",
    "point3",
]
