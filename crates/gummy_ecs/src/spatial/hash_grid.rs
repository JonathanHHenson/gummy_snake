use std::collections::HashMap;

use crate::error::{EcsError, Result};

use super::{
    Dimensions, SpatialAabb, SpatialCapabilities, SpatialIndexBackend, SpatialMemoryStats,
    SpatialPoint, SpatialRecord,
};

mod queries;

#[cfg(test)]
mod tests;

const MAX_SPATIAL_QUERY_CELLS: u64 = 1_000_000;

#[derive(Debug, Clone)]
pub struct HashGridIndex {
    dimensions: Dimensions,
    cell_size: f64,
    buckets: HashMap<[i64; 3], Vec<SpatialRecord>>,
    records: Vec<SpatialRecord>,
    record_cells: HashMap<u64, [i64; 3]>,
    has_multicell_records: bool,
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
            record_cells: HashMap::new(),
            has_multicell_records: false,
        })
    }

    pub(super) fn cell(&self, point: &SpatialPoint) -> Result<[i64; 3]> {
        if point.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "hash grid point dimensions do not match index dimensions".to_string(),
            ));
        }
        self.cell_from_coords([point.coord(0), point.coord(1), point.coord(2)])
    }

    pub(super) fn cell_from_coords(&self, coords: [f64; 3]) -> Result<[i64; 3]> {
        let mut cell = [0_i64; 3];
        for (axis, slot) in cell.iter_mut().enumerate().take(self.dimensions.len()) {
            let value = (coords[axis] / self.cell_size).floor();
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
            incremental_updates: true,
        }
    }

    fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        self.buckets.clear();
        self.records.clear();
        self.record_cells.clear();
        self.has_multicell_records = false;
        self.records.extend_from_slice(records);
        self.records.sort_by_key(|record| record.entity.raw());
        for index in 0..self.records.len() {
            let record = &self.records[index];
            if let Some(bounds) = &record.bounds {
                let min_cell = self.cell(bounds.minimum())?;
                let max_cell = self.cell(bounds.maximum())?;
                validate_cell_span(self.dimensions, min_cell, max_cell)?;
                let mut first = true;
                for cell in iter_cells(self.dimensions, min_cell, max_cell) {
                    if first {
                        first = false;
                    } else {
                        self.has_multicell_records = true;
                    }
                    self.buckets.entry(cell).or_default().push(record.clone());
                }
            } else {
                let cell = self.cell(&record.point)?;
                self.record_cells.insert(record.entity.raw(), cell);
                self.buckets.entry(cell).or_default().push(record.clone());
            }
        }
        for bucket in self.buckets.values_mut() {
            bucket.sort_by_key(|record| record.entity.raw());
        }
        Ok(())
    }

    fn update_incremental(&mut self, records: &[SpatialRecord]) -> Result<bool> {
        if self.has_multicell_records || records.iter().any(|record| record.bounds.is_some()) {
            self.build(records)?;
            return Ok(false);
        }
        let mut next_records = records.to_vec();
        next_records.sort_by_key(|record| record.entity.raw());
        let mut next_cells = HashMap::with_capacity(next_records.len());
        for record in &next_records {
            if record.point.dimensions() != self.dimensions {
                return Err(EcsError::InvalidSpatialInput(
                    "hash grid record dimensions do not match index dimensions".to_string(),
                ));
            }
            next_cells.insert(record.entity.raw(), self.cell(&record.point)?);
        }

        let removed = self
            .record_cells
            .keys()
            .copied()
            .filter(|entity| !next_cells.contains_key(entity))
            .collect::<Vec<_>>();
        for entity in removed {
            if let Some(old_cell) = self.record_cells.remove(&entity) {
                remove_record_from_bucket(&mut self.buckets, old_cell, entity);
            }
        }

        for record in &next_records {
            let entity = record.entity.raw();
            let next_cell = next_cells[&entity];
            match self.record_cells.get(&entity).copied() {
                Some(old_cell) if old_cell == next_cell => {
                    replace_record_in_bucket(&mut self.buckets, next_cell, record.clone());
                }
                Some(old_cell) => {
                    remove_record_from_bucket(&mut self.buckets, old_cell, entity);
                    self.buckets
                        .entry(next_cell)
                        .or_default()
                        .push(record.clone());
                    self.record_cells.insert(entity, next_cell);
                }
                None => {
                    self.buckets
                        .entry(next_cell)
                        .or_default()
                        .push(record.clone());
                    self.record_cells.insert(entity, next_cell);
                }
            }
        }
        self.records = next_records;
        self.has_multicell_records = false;
        self.buckets.retain(|_, bucket| !bucket.is_empty());
        for bucket in self.buckets.values_mut() {
            bucket.sort_by_key(|record| record.entity.raw());
        }
        Ok(true)
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
        self.query_radius_ordered(origin, radius, out)
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        self.query_aabb_ordered(bounds, out)
    }
}

fn remove_record_from_bucket(
    buckets: &mut HashMap<[i64; 3], Vec<SpatialRecord>>,
    cell: [i64; 3],
    entity: u64,
) {
    if let Some(bucket) = buckets.get_mut(&cell) {
        bucket.retain(|record| record.entity.raw() != entity);
    }
}

fn replace_record_in_bucket(
    buckets: &mut HashMap<[i64; 3], Vec<SpatialRecord>>,
    cell: [i64; 3],
    record: SpatialRecord,
) {
    if let Some(bucket) = buckets.get_mut(&cell) {
        if let Some(slot) = bucket
            .iter_mut()
            .find(|candidate| candidate.entity.raw() == record.entity.raw())
        {
            *slot = record;
            return;
        }
    }
    buckets.entry(cell).or_default().push(record);
}

pub(super) fn distance_squared_unchecked(
    left: &SpatialPoint,
    right: &SpatialPoint,
    dimensions: Dimensions,
) -> f64 {
    let mut distance_sq = 0.0;
    for axis in 0..dimensions.len() {
        let delta = right.coord(axis) - left.coord(axis);
        distance_sq += delta * delta;
    }
    distance_sq
}

pub(super) fn validate_cell_span(
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

pub(super) fn iter_cells(
    dimensions: Dimensions,
    min_cell: [i64; 3],
    max_cell: [i64; 3],
) -> Vec<[i64; 3]> {
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
