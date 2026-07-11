mod hash_grid;
mod hilbert;
mod registry;
pub mod tree_spatial;
mod types;

pub use hash_grid::HashGridIndex;
pub use hilbert::HilbertIndex;
pub use registry::{
    SpatialAlgorithmKind, SpatialIndexDescriptor, SpatialIndexRegistry, SpatialIndexSlot,
    SpatialIndexStats,
};
pub use tree_spatial::{OctreeIndex, QuadtreeIndex};
pub use types::{
    Dimensions, SpatialAabb, SpatialCapabilities, SpatialIndexBackend, SpatialMemoryStats,
    SpatialPoint, SpatialRecord,
};
