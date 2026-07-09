use crate::entity::Entity;
use crate::error::{EcsError, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Dimensions {
    D2,
    D3,
}

impl Dimensions {
    pub fn len(self) -> usize {
        match self {
            Self::D2 => 2,
            Self::D3 => 3,
        }
    }

    pub fn is_empty(self) -> bool {
        false
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpatialPoint {
    coords: [f64; 3],
    dimensions: Dimensions,
}

impl SpatialPoint {
    pub fn point2(x: f64, y: f64) -> Result<Self> {
        Self::new([x, y, 0.0], Dimensions::D2)
    }

    pub fn point3(x: f64, y: f64, z: f64) -> Result<Self> {
        Self::new([x, y, z], Dimensions::D3)
    }

    pub(super) fn new(coords: [f64; 3], dimensions: Dimensions) -> Result<Self> {
        if coords[..dimensions.len()]
            .iter()
            .any(|value| !value.is_finite())
        {
            return Err(EcsError::InvalidSpatialInput(
                "spatial point coordinates must be finite".to_string(),
            ));
        }
        Ok(Self { coords, dimensions })
    }

    pub fn dimensions(&self) -> Dimensions {
        self.dimensions
    }

    pub fn coord(&self, axis: usize) -> f64 {
        self.coords[axis]
    }

    pub fn distance_squared(&self, other: &Self) -> Result<f64> {
        if self.dimensions != other.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "spatial point dimensions must match".to_string(),
            ));
        }
        Ok((0..self.dimensions.len())
            .map(|axis| {
                let delta = other.coords[axis] - self.coords[axis];
                delta * delta
            })
            .sum())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpatialAabb {
    minimum: SpatialPoint,
    maximum: SpatialPoint,
}

impl SpatialAabb {
    pub fn new(minimum: SpatialPoint, maximum: SpatialPoint) -> Result<Self> {
        if minimum.dimensions() != maximum.dimensions() {
            return Err(EcsError::InvalidSpatialInput(
                "spatial AABB min/max dimensions must match".to_string(),
            ));
        }
        for axis in 0..minimum.dimensions().len() {
            if minimum.coord(axis) > maximum.coord(axis) {
                return Err(EcsError::InvalidSpatialInput(
                    "spatial AABB minimum values must be <= maximum values".to_string(),
                ));
            }
        }
        Ok(Self { minimum, maximum })
    }

    pub fn point2(min_x: f64, min_y: f64, max_x: f64, max_y: f64) -> Result<Self> {
        Self::new(
            SpatialPoint::point2(min_x, min_y)?,
            SpatialPoint::point2(max_x, max_y)?,
        )
    }

    pub fn point3(
        min_x: f64,
        min_y: f64,
        min_z: f64,
        max_x: f64,
        max_y: f64,
        max_z: f64,
    ) -> Result<Self> {
        Self::new(
            SpatialPoint::point3(min_x, min_y, min_z)?,
            SpatialPoint::point3(max_x, max_y, max_z)?,
        )
    }

    pub fn dimensions(&self) -> Dimensions {
        self.minimum.dimensions()
    }

    pub fn minimum(&self) -> &SpatialPoint {
        &self.minimum
    }

    pub fn maximum(&self) -> &SpatialPoint {
        &self.maximum
    }

    pub fn overlaps(&self, other: &Self) -> Result<bool> {
        if self.dimensions() != other.dimensions() {
            return Err(EcsError::InvalidSpatialInput(
                "spatial AABB dimensions must match".to_string(),
            ));
        }
        Ok((0..self.dimensions().len()).all(|axis| {
            self.minimum.coord(axis) <= other.maximum.coord(axis)
                && other.minimum.coord(axis) <= self.maximum.coord(axis)
        }))
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpatialRecord {
    pub entity: Entity,
    pub point: SpatialPoint,
    pub bounds: Option<SpatialAabb>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SpatialCapabilities {
    pub dimensions: Dimensions,
    pub radius_queries: bool,
    pub aabb_queries: bool,
    pub incremental_updates: bool,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct SpatialMemoryStats {
    pub records_len: usize,
    pub records_capacity: usize,
    pub buckets_len: usize,
    pub buckets_capacity: usize,
    pub nodes_len: usize,
    pub overflow_len: usize,
    pub overflow_capacity: usize,
}

pub trait SpatialIndexBackend {
    fn capabilities(&self) -> SpatialCapabilities;
    fn memory_stats(&self) -> SpatialMemoryStats {
        SpatialMemoryStats::default()
    }
    fn build(&mut self, records: &[SpatialRecord]) -> Result<()>;
    fn update_incremental(&mut self, records: &[SpatialRecord]) -> Result<bool> {
        self.build(records)?;
        Ok(false)
    }
    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()>;
    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()>;
}
