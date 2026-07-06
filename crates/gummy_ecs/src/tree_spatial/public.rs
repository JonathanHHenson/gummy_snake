use crate::error::Result;
use crate::spatial::{
    Dimensions, SpatialAabb, SpatialCapabilities, SpatialIndexBackend, SpatialMemoryStats,
    SpatialPoint, SpatialRecord,
};

use super::core::TreeIndex;

#[derive(Debug, Clone)]
pub struct QuadtreeIndex {
    inner: TreeIndex,
}

impl QuadtreeIndex {
    pub fn new(bounds: SpatialAabb, capacity: usize) -> Result<Self> {
        Ok(Self {
            inner: TreeIndex::new(Dimensions::D2, bounds, capacity)?,
        })
    }

    pub fn query_radius_unordered(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        self.inner.query_radius_unordered(origin, radius, out)
    }
}

impl SpatialIndexBackend for QuadtreeIndex {
    fn capabilities(&self) -> SpatialCapabilities {
        self.inner.capabilities()
    }

    fn memory_stats(&self) -> SpatialMemoryStats {
        self.inner.memory_stats()
    }

    fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        self.inner.build(records)
    }

    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        self.inner.query_radius(origin, radius, out)
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        self.inner.query_aabb(bounds, out)
    }
}

#[derive(Debug, Clone)]
pub struct OctreeIndex {
    inner: TreeIndex,
}

impl OctreeIndex {
    pub fn new(bounds: SpatialAabb, capacity: usize) -> Result<Self> {
        Ok(Self {
            inner: TreeIndex::new(Dimensions::D3, bounds, capacity)?,
        })
    }

    pub fn query_radius_unordered(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        self.inner.query_radius_unordered(origin, radius, out)
    }
}

impl SpatialIndexBackend for OctreeIndex {
    fn capabilities(&self) -> SpatialCapabilities {
        self.inner.capabilities()
    }

    fn memory_stats(&self) -> SpatialMemoryStats {
        self.inner.memory_stats()
    }

    fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        self.inner.build(records)
    }

    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        self.inner.query_radius(origin, radius, out)
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        self.inner.query_aabb(bounds, out)
    }
}
