use std::collections::HashMap;

use crate::entity::Entity;
use crate::error::{EcsError, Result};

const MAX_SPATIAL_QUERY_CELLS: u64 = 1_000_000;

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

    fn new(coords: [f64; 3], dimensions: Dimensions) -> Result<Self> {
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
    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()>;
    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()>;
}

#[derive(Debug, Clone)]
pub struct HashGridIndex {
    dimensions: Dimensions,
    cell_size: f64,
    buckets: HashMap<[i64; 3], Vec<SpatialRecord>>,
    records: Vec<SpatialRecord>,
}

impl HashGridIndex {
    pub fn new(dimensions: Dimensions, cell_size: f64) -> Result<Self> {
        if !cell_size.is_finite() || cell_size <= 0.0 {
            return Err(EcsError::InvalidSpatialInput(
                "hash grid cell_size must be finite and positive".to_string(),
            ));
        }
        Ok(Self {
            dimensions,
            cell_size,
            buckets: HashMap::new(),
            records: Vec::new(),
        })
    }

    fn cell(&self, point: &SpatialPoint) -> Result<[i64; 3]> {
        if point.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "hash grid point dimensions do not match index dimensions".to_string(),
            ));
        }
        let mut cell = [0_i64; 3];
        for (axis, slot) in cell.iter_mut().enumerate().take(self.dimensions.len()) {
            let value = (point.coord(axis) / self.cell_size).floor();
            if value < i64::MIN as f64 || value > i64::MAX as f64 {
                return Err(EcsError::InvalidSpatialInput(
                    "hash grid cell coordinate overflow".to_string(),
                ));
            }
            *slot = value as i64;
        }
        Ok(cell)
    }
}

impl SpatialIndexBackend for HashGridIndex {
    fn capabilities(&self) -> SpatialCapabilities {
        SpatialCapabilities {
            dimensions: self.dimensions,
            radius_queries: true,
            aabb_queries: true,
            incremental_updates: false,
        }
    }

    fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        self.buckets.clear();
        self.records.clear();
        self.records.extend_from_slice(records);
        self.records.sort_by_key(|record| record.entity.raw());
        for record in self.records.clone() {
            if let Some(bounds) = &record.bounds {
                let min_cell = self.cell(bounds.minimum())?;
                let max_cell = self.cell(bounds.maximum())?;
                validate_cell_span(self.dimensions, min_cell, max_cell)?;
                for cell in iter_cells(self.dimensions, min_cell, max_cell) {
                    self.buckets.entry(cell).or_default().push(record.clone());
                }
            } else {
                let cell = self.cell(&record.point)?;
                self.buckets.entry(cell).or_default().push(record);
            }
        }
        for bucket in self.buckets.values_mut() {
            bucket.sort_by_key(|record| record.entity.raw());
        }
        Ok(())
    }

    fn memory_stats(&self) -> SpatialMemoryStats {
        SpatialMemoryStats {
            records_len: self.records.len(),
            records_capacity: self.records.capacity(),
            buckets_len: self.buckets.len(),
            buckets_capacity: self.buckets.capacity(),
            nodes_len: 0,
            overflow_len: 0,
            overflow_capacity: 0,
        }
    }

    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        if origin.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "query point dimensions do not match index dimensions".to_string(),
            ));
        }
        if !radius.is_finite() || radius < 0.0 {
            return Err(EcsError::InvalidSpatialInput(
                "query radius must be finite and non-negative".to_string(),
            ));
        }
        out.clear();
        let min_point = SpatialPoint::new(
            [
                origin.coord(0) - radius,
                origin.coord(1) - radius,
                if self.dimensions == Dimensions::D3 {
                    origin.coord(2) - radius
                } else {
                    0.0
                },
            ],
            self.dimensions,
        )?;
        let max_point = SpatialPoint::new(
            [
                origin.coord(0) + radius,
                origin.coord(1) + radius,
                if self.dimensions == Dimensions::D3 {
                    origin.coord(2) + radius
                } else {
                    0.0
                },
            ],
            self.dimensions,
        )?;
        let min_cell = self.cell(&min_point)?;
        let max_cell = self.cell(&max_point)?;
        validate_cell_span(self.dimensions, min_cell, max_cell)?;
        let mut seen = HashMap::new();
        for x in min_cell[0]..=max_cell[0] {
            for y in min_cell[1]..=max_cell[1] {
                if self.dimensions == Dimensions::D2 {
                    if let Some(bucket) = self.buckets.get(&[x, y, 0]) {
                        for record in bucket {
                            seen.insert(record.entity.raw(), record.clone());
                        }
                    }
                } else {
                    for z in min_cell[2]..=max_cell[2] {
                        if let Some(bucket) = self.buckets.get(&[x, y, z]) {
                            for record in bucket {
                                seen.insert(record.entity.raw(), record.clone());
                            }
                        }
                    }
                }
            }
        }
        let mut keys = seen.keys().copied().collect::<Vec<_>>();
        keys.sort_unstable();
        for key in keys {
            let record = seen.remove(&key).expect("key came from map");
            if origin.distance_squared(&record.point)? <= radius * radius {
                out.push(record);
            }
        }
        Ok(())
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        if bounds.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "query bounds dimensions do not match index dimensions".to_string(),
            ));
        }
        out.clear();
        let min_cell = self.cell(bounds.minimum())?;
        let max_cell = self.cell(bounds.maximum())?;
        validate_cell_span(self.dimensions, min_cell, max_cell)?;
        let mut seen = HashMap::new();
        for cell in iter_cells(self.dimensions, min_cell, max_cell) {
            if let Some(bucket) = self.buckets.get(&cell) {
                for record in bucket {
                    seen.insert(record.entity.raw(), record.clone());
                }
            }
        }
        let mut keys = seen.keys().copied().collect::<Vec<_>>();
        keys.sort_unstable();
        for key in keys {
            let record = seen.remove(&key).expect("key came from map");
            match &record.bounds {
                Some(record_bounds) if bounds.overlaps(record_bounds)? => out.push(record),
                None => {
                    let point_bounds =
                        SpatialAabb::new(record.point.clone(), record.point.clone())?;
                    if bounds.overlaps(&point_bounds)? {
                        out.push(record);
                    }
                }
                _ => {}
            }
        }
        Ok(())
    }
}

fn validate_cell_span(
    dimensions: Dimensions,
    min_cell: [i64; 3],
    max_cell: [i64; 3],
) -> Result<()> {
    let mut total = 1_u64;
    for axis in 0..dimensions.len() {
        let span = max_cell[axis]
            .checked_sub(min_cell[axis])
            .and_then(|value| value.checked_add(1))
            .ok_or_else(|| {
                EcsError::InvalidSpatialInput("hash grid cell span overflow".to_string())
            })?;
        let span = u64::try_from(span).map_err(|_| {
            EcsError::InvalidSpatialInput("hash grid cell span must be non-negative".to_string())
        })?;
        total = total.checked_mul(span).ok_or_else(|| {
            EcsError::InvalidSpatialInput("hash grid cell span overflow".to_string())
        })?;
        if total > MAX_SPATIAL_QUERY_CELLS {
            return Err(EcsError::InvalidSpatialInput(format!(
                "hash grid query spans {total} cells; maximum is {MAX_SPATIAL_QUERY_CELLS}"
            )));
        }
    }
    Ok(())
}

fn iter_cells(dimensions: Dimensions, min_cell: [i64; 3], max_cell: [i64; 3]) -> Vec<[i64; 3]> {
    let mut cells = Vec::new();
    for x in min_cell[0]..=max_cell[0] {
        for y in min_cell[1]..=max_cell[1] {
            if dimensions == Dimensions::D2 {
                cells.push([x, y, 0]);
            } else {
                for z in min_cell[2]..=max_cell[2] {
                    cells.push([x, y, z]);
                }
            }
        }
    }
    cells
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entity(index: u32) -> Entity {
        Entity {
            index,
            generation: 0,
        }
    }

    #[test]
    fn hash_grid_returns_radius_matches_in_entity_order() {
        let records = vec![
            SpatialRecord {
                entity: entity(2),
                point: SpatialPoint::point2(10.0, 0.0).unwrap(),
                bounds: None,
            },
            SpatialRecord {
                entity: entity(0),
                point: SpatialPoint::point2(0.0, 0.0).unwrap(),
                bounds: None,
            },
            SpatialRecord {
                entity: entity(1),
                point: SpatialPoint::point2(3.0, 4.0).unwrap(),
                bounds: None,
            },
        ];
        let mut index = HashGridIndex::new(Dimensions::D2, 5.0).unwrap();
        index.build(&records).unwrap();
        let mut out = Vec::new();
        index
            .query_radius(&SpatialPoint::point2(0.0, 0.0).unwrap(), 5.0, &mut out)
            .unwrap();
        assert_eq!(
            out.iter()
                .map(|record| record.entity.index)
                .collect::<Vec<_>>(),
            vec![0, 1]
        );
    }

    #[test]
    fn hash_grid_handles_negative_3d_cells_deterministically() {
        let records = vec![
            SpatialRecord {
                entity: entity(1),
                point: SpatialPoint::point3(-2.0, -2.0, -2.0).unwrap(),
                bounds: None,
            },
            SpatialRecord {
                entity: entity(0),
                point: SpatialPoint::point3(-1.0, -1.0, -1.0).unwrap(),
                bounds: None,
            },
        ];
        let mut index = HashGridIndex::new(Dimensions::D3, 2.0).unwrap();
        index.build(&records).unwrap();
        let mut out = Vec::new();
        index
            .query_radius(
                &SpatialPoint::point3(-1.0, -1.0, -1.0).unwrap(),
                2.0,
                &mut out,
            )
            .unwrap();
        assert_eq!(
            out.iter()
                .map(|record| record.entity.index)
                .collect::<Vec<_>>(),
            vec![0, 1]
        );
    }

    #[test]
    fn hash_grid_reports_capacity_reuse_stats() {
        let records = (0..32)
            .map(|index| SpatialRecord {
                entity: entity(index),
                point: SpatialPoint::point2(index as f64, 0.0).unwrap(),
                bounds: None,
            })
            .collect::<Vec<_>>();
        let mut index = HashGridIndex::new(Dimensions::D2, 2.0).unwrap();
        index.build(&records).unwrap();
        let first = index.memory_stats();
        assert_eq!(first.records_len, records.len());
        assert!(first.records_capacity >= records.len());
        assert!(first.buckets_len > 0);
        assert!(first.buckets_capacity >= first.buckets_len);

        index.build(&records[..4]).unwrap();
        let second = index.memory_stats();
        assert_eq!(second.records_len, 4);
        assert!(second.records_capacity >= first.records_capacity);
        assert!(second.buckets_capacity >= first.buckets_capacity);
    }

    #[test]
    fn hash_grid_returns_aabb_matches_in_entity_order() {
        let records = vec![
            SpatialRecord {
                entity: entity(2),
                point: SpatialPoint::point2(20.0, 0.0).unwrap(),
                bounds: Some(SpatialAabb::point2(19.0, -1.0, 21.0, 1.0).unwrap()),
            },
            SpatialRecord {
                entity: entity(0),
                point: SpatialPoint::point2(0.0, 0.0).unwrap(),
                bounds: Some(SpatialAabb::point2(-2.0, -2.0, 2.0, 2.0).unwrap()),
            },
            SpatialRecord {
                entity: entity(1),
                point: SpatialPoint::point2(3.0, 0.0).unwrap(),
                bounds: Some(SpatialAabb::point2(1.0, -1.0, 4.0, 1.0).unwrap()),
            },
        ];
        let mut index = HashGridIndex::new(Dimensions::D2, 4.0).unwrap();
        index.build(&records).unwrap();
        let mut out = Vec::new();
        index
            .query_aabb(
                &SpatialAabb::point2(-1.0, -1.0, 2.5, 1.0).unwrap(),
                &mut out,
            )
            .unwrap();
        assert_eq!(
            out.iter()
                .map(|record| record.entity.index)
                .collect::<Vec<_>>(),
            vec![0, 1]
        );
    }

    #[test]
    fn hash_grid_rejects_pathological_cell_spans() {
        let mut index = HashGridIndex::new(Dimensions::D2, 1.0).unwrap();
        index.build(&[]).unwrap();
        let mut out = Vec::new();
        let err = index
            .query_aabb(
                &SpatialAabb::point2(0.0, 0.0, 2_000.0, 2_000.0).unwrap(),
                &mut out,
            )
            .unwrap_err();
        assert!(err.to_string().contains("maximum"));
    }
}
