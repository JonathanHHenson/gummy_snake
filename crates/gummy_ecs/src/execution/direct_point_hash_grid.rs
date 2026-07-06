use std::collections::HashMap;

use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::spatial::{Dimensions, SpatialAabb, SpatialPoint, SpatialRecord};

mod dense_buckets;
mod regular_grid;
mod validation;

use self::dense_buckets::DirectPointDenseBuckets;
use self::regular_grid::DirectPointRegularGrid;
use self::validation::validate_direct_point_cell_span;
pub(super) const DIRECT_POINT_HASH_GRID_DENSE_MAX_CELLS: usize = 262_144;
pub(super) const DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER: usize = 2;
pub(super) const DIRECT_POINT_HASH_GRID_DENSE_CELL_PADDING: i64 = 16;

#[derive(Debug, Clone)]
pub(super) struct DirectPointRecord {
    pub(super) entity: Entity,
    pub(super) point: SpatialPoint,
}

#[derive(Debug, Clone)]
pub(crate) struct DirectPointHashGrid {
    dimensions: Dimensions,
    cell_size: f64,
    buckets: HashMap<[i64; 3], Vec<usize>>,
    dense_buckets: Option<DirectPointDenseBuckets>,
    regular_grid: Option<DirectPointRegularGrid>,
    records: Vec<DirectPointRecord>,
}

impl DirectPointHashGrid {
    pub(super) fn new(dimensions: Dimensions, cell_size: f64) -> Result<Self> {
        if !cell_size.is_finite() || cell_size <= 0.0 {
            return Err(EcsError::InvalidSpatialInput(
                "hash grid cell_size must be finite and positive".to_string(),
            ));
        }
        Ok(Self {
            dimensions,
            cell_size,
            buckets: HashMap::new(),
            dense_buckets: None,
            regular_grid: None,
            records: Vec::new(),
        })
    }

    pub(super) fn records(&self) -> &[DirectPointRecord] {
        &self.records
    }

    pub(super) fn is_empty(&self) -> bool {
        self.records.is_empty()
    }

    pub(super) fn record_count(&self) -> usize {
        self.records.len()
    }

    pub(super) fn has_regular_grid(&self) -> bool {
        self.regular_grid.is_some()
    }

    pub(super) fn build_sorted_points(&mut self, records: Vec<DirectPointRecord>) -> Result<()> {
        self.buckets.clear();
        self.dense_buckets = None;
        self.regular_grid = None;
        let mut cells = Vec::with_capacity(records.len());
        for record in &records {
            if record.point.dimensions() != self.dimensions {
                return Err(EcsError::InvalidSpatialInput(
                    "hash grid record dimensions do not match index dimensions".to_string(),
                ));
            }
            cells.push(self.cell(&record.point)?);
        }
        self.records = records;
        self.regular_grid = DirectPointRegularGrid::new(&self.records);
        if let Some(mut dense) = DirectPointDenseBuckets::new(self.dimensions, &cells) {
            for (index, cell) in cells.iter().enumerate() {
                let pushed = dense.try_push(*cell, index);
                debug_assert!(pushed, "validated dense bucket cell should be in range");
            }
            self.dense_buckets = Some(dense);
            return Ok(());
        }
        self.build_sparse_buckets(cells);
        Ok(())
    }

    fn build_sparse_buckets(&mut self, cells: Vec<[i64; 3]>) {
        self.buckets.clear();
        for (index, cell) in cells.into_iter().enumerate() {
            self.buckets.entry(cell).or_default().push(index);
        }
    }

    pub(super) fn build_from_spatial_records(&mut self, records: &[SpatialRecord]) -> Result<()> {
        self.build_sorted_points(Self::sorted_direct_records(records)?)
    }

    pub(super) fn update_from_spatial_records(
        &mut self,
        records: &[SpatialRecord],
    ) -> Result<bool> {
        let direct = Self::sorted_direct_records(records)?;
        self.update_sorted_points(&direct)
    }

    fn sorted_direct_records(records: &[SpatialRecord]) -> Result<Vec<DirectPointRecord>> {
        if records.iter().any(|record| record.bounds.is_some()) {
            return Err(EcsError::InvalidSpatialInput(
                "direct point hash grid only supports point records".to_string(),
            ));
        }
        let mut direct = records
            .iter()
            .map(|record| DirectPointRecord {
                entity: record.entity,
                point: record.point.clone(),
            })
            .collect::<Vec<_>>();
        direct.sort_by_key(|record| record.entity.raw());
        Ok(direct)
    }

    pub(super) fn update_sorted_points(&mut self, records: &[DirectPointRecord]) -> Result<bool> {
        if records.len() != self.records.len() {
            self.build_sorted_points(records.to_vec())?;
            return Ok(false);
        }
        // A moved point can break the exact regular-grid shortcut. The hash buckets
        // are also populated during builds, so drop the shortcut and mutate them.
        self.regular_grid = None;
        for (index, next) in records.iter().enumerate() {
            if self.records[index].entity != next.entity {
                self.build_sorted_points(records.to_vec())?;
                return Ok(false);
            }
            if next.point.dimensions() != self.dimensions {
                return Err(EcsError::InvalidSpatialInput(
                    "hash grid record dimensions do not match index dimensions".to_string(),
                ));
            }
            if !self.update_record_cell(index, next)? {
                self.build_sorted_points(records.to_vec())?;
                return Ok(false);
            }
            self.records[index] = next.clone();
        }
        Ok(true)
    }

    fn update_record_cell(&mut self, index: usize, next: &DirectPointRecord) -> Result<bool> {
        let old_cell = self.cell(&self.records[index].point)?;
        let new_cell = self.cell(&next.point)?;
        if old_cell == new_cell {
            return Ok(true);
        }
        if let Some(dense) = &mut self.dense_buckets {
            if !dense.remove(old_cell, index) || !dense.try_push(new_cell, index) {
                return Ok(false);
            }
            return Ok(true);
        }
        if let Some(bucket) = self.buckets.get_mut(&old_cell) {
            if let Some(position) = bucket.iter().position(|candidate| *candidate == index) {
                bucket.swap_remove(position);
            }
            if bucket.is_empty() {
                self.buckets.remove(&old_cell);
            }
        }
        self.buckets.entry(new_cell).or_default().push(index);
        Ok(true)
    }

    fn cell(&self, point: &SpatialPoint) -> Result<[i64; 3]> {
        if point.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "hash grid point dimensions do not match index dimensions".to_string(),
            ));
        }
        self.cell_from_coords([point.coord(0), point.coord(1), point.coord(2)])
    }

    fn cell_from_coords(&self, coords: [f64; 3]) -> Result<[i64; 3]> {
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

    pub(super) fn visit_radius_unordered_indexed<F>(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        mut visit: F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        self.validate_radius_query(origin, radius)?;
        let origin_x = origin.coord(0);
        let origin_y = origin.coord(1);
        let origin_z = if self.dimensions == Dimensions::D3 {
            origin.coord(2)
        } else {
            0.0
        };
        let radius_sq = radius * radius;
        if self.dimensions == Dimensions::D2 {
            if let Some(regular_grid) = &self.regular_grid {
                return regular_grid.visit_radius(
                    &self.records,
                    origin_x,
                    origin_y,
                    radius,
                    radius_sq,
                    &mut visit,
                );
            }
        }
        self.visit_hash_grid_radius(origin_x, origin_y, origin_z, radius, radius_sq, &mut visit)
    }

    fn validate_radius_query(&self, origin: &SpatialPoint, radius: f64) -> Result<()> {
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
        Ok(())
    }

    fn visit_hash_grid_radius<F>(
        &self,
        origin_x: f64,
        origin_y: f64,
        origin_z: f64,
        radius: f64,
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        let min_cell = self.query_cell(origin_x - radius, origin_y - radius, origin_z - radius)?;
        let max_cell = self.query_cell(origin_x + radius, origin_y + radius, origin_z + radius)?;
        validate_direct_point_cell_span(self.dimensions, min_cell, max_cell)?;
        if self.dimensions == Dimensions::D2 {
            return self.visit_hash_grid_radius_2d(
                min_cell, max_cell, origin_x, origin_y, radius_sq, visit,
            );
        }
        self.visit_hash_grid_radius_3d(
            min_cell,
            max_cell,
            [origin_x, origin_y, origin_z],
            radius_sq,
            visit,
        )
    }

    fn visit_hash_grid_radius_2d<F>(
        &self,
        min_cell: [i64; 3],
        max_cell: [i64; 3],
        origin_x: f64,
        origin_y: f64,
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        for x in min_cell[0]..=max_cell[0] {
            for y in min_cell[1]..=max_cell[1] {
                if let Some(bucket) = self.direct_bucket([x, y, 0]) {
                    self.visit_radius_bucket_2d(bucket, origin_x, origin_y, radius_sq, visit)?;
                }
            }
        }
        Ok(())
    }

    fn visit_hash_grid_radius_3d<F>(
        &self,
        min_cell: [i64; 3],
        max_cell: [i64; 3],
        origin: [f64; 3],
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        for x in min_cell[0]..=max_cell[0] {
            for y in min_cell[1]..=max_cell[1] {
                self.visit_z_radius_buckets(
                    x,
                    y,
                    min_cell[2],
                    max_cell[2],
                    origin,
                    radius_sq,
                    visit,
                )?;
            }
        }
        Ok(())
    }

    fn query_cell(&self, x: f64, y: f64, z: f64) -> Result<[i64; 3]> {
        self.cell_from_coords([
            x,
            y,
            if self.dimensions == Dimensions::D3 {
                z
            } else {
                0.0
            },
        ])
    }

    fn visit_z_radius_buckets<F>(
        &self,
        x: i64,
        y: i64,
        min_z: i64,
        max_z: i64,
        origin: [f64; 3],
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        for z in min_z..=max_z {
            if let Some(bucket) = self.direct_bucket([x, y, z]) {
                self.visit_radius_bucket_3d(
                    bucket, origin[0], origin[1], origin[2], radius_sq, visit,
                )?;
            }
        }
        Ok(())
    }

    fn direct_bucket(&self, cell: [i64; 3]) -> Option<&[usize]> {
        if let Some(dense) = &self.dense_buckets {
            return dense.bucket(cell);
        }
        self.buckets.get(&cell).map(Vec::as_slice)
    }

    fn visit_radius_bucket_2d<F>(
        &self,
        bucket: &[usize],
        origin_x: f64,
        origin_y: f64,
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        for record_index in bucket {
            let record = &self.records[*record_index];
            let dx = record.point.coord(0) - origin_x;
            let dy = record.point.coord(1) - origin_y;
            let distance_sq = dx * dx + dy * dy;
            if distance_sq <= radius_sq {
                visit(*record_index, record, distance_sq)?;
            }
        }
        Ok(())
    }

    fn visit_radius_bucket_3d<F>(
        &self,
        bucket: &[usize],
        origin_x: f64,
        origin_y: f64,
        origin_z: f64,
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        for record_index in bucket {
            let record = &self.records[*record_index];
            let dx = record.point.coord(0) - origin_x;
            let dy = record.point.coord(1) - origin_y;
            let dz = record.point.coord(2) - origin_z;
            let distance_sq = dx * dx + dy * dy + dz * dz;
            if distance_sq <= radius_sq {
                visit(*record_index, record, distance_sq)?;
            }
        }
        Ok(())
    }

    pub(super) fn query_radius_unordered(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        out.clear();
        self.visit_radius_unordered_indexed(origin, radius, |_, record, _| {
            out.push(SpatialRecord {
                entity: record.entity,
                point: record.point.clone(),
                bounds: None,
            });
            Ok(())
        })
    }

    pub(super) fn query_aabb(
        &self,
        bounds: &SpatialAabb,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        if bounds.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "query bounds dimensions do not match index dimensions".to_string(),
            ));
        }
        out.clear();
        let min_cell = self.cell(bounds.minimum())?;
        let max_cell = self.cell(bounds.maximum())?;
        validate_direct_point_cell_span(self.dimensions, min_cell, max_cell)?;
        for x in min_cell[0]..=max_cell[0] {
            for y in min_cell[1]..=max_cell[1] {
                if self.dimensions == Dimensions::D2 {
                    if let Some(bucket) = self.direct_bucket([x, y, 0]) {
                        self.push_aabb_matches(bucket, bounds, out);
                    }
                } else {
                    for z in min_cell[2]..=max_cell[2] {
                        if let Some(bucket) = self.direct_bucket([x, y, z]) {
                            self.push_aabb_matches(bucket, bounds, out);
                        }
                    }
                }
            }
        }
        Ok(())
    }

    fn push_aabb_matches(
        &self,
        bucket: &[usize],
        bounds: &SpatialAabb,
        out: &mut Vec<SpatialRecord>,
    ) {
        for index in bucket {
            let record = &self.records[*index];
            let inside = (0..self.dimensions.len()).all(|axis| {
                let coord = record.point.coord(axis);
                bounds.minimum().coord(axis) <= coord && coord <= bounds.maximum().coord(axis)
            });
            if inside {
                out.push(SpatialRecord {
                    entity: record.entity,
                    point: record.point.clone(),
                    bounds: None,
                });
            }
        }
    }
}
