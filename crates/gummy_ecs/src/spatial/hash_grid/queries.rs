use std::collections::HashMap;

use crate::error::{EcsError, Result};

use super::{distance_squared_unchecked, iter_cells, validate_cell_span, HashGridIndex};
use crate::spatial::{Dimensions, SpatialAabb, SpatialPoint, SpatialRecord};

impl HashGridIndex {
    pub fn visit_radius_unordered<F>(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        mut visit: F,
    ) -> Result<()>
    where
        F: FnMut(&SpatialRecord, f64) -> Result<()>,
    {
        if self.has_multicell_records {
            let mut records = Vec::new();
            self.query_radius_ordered(origin, radius, &mut records)?;
            for record in &records {
                visit(
                    record,
                    distance_squared_unchecked(origin, &record.point, self.dimensions),
                )?;
            }
            return Ok(());
        }
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
        let min_cell = self.cell_from_coords([
            origin.coord(0) - radius,
            origin.coord(1) - radius,
            if self.dimensions == Dimensions::D3 {
                origin.coord(2) - radius
            } else {
                0.0
            },
        ])?;
        let max_cell = self.cell_from_coords([
            origin.coord(0) + radius,
            origin.coord(1) + radius,
            if self.dimensions == Dimensions::D3 {
                origin.coord(2) + radius
            } else {
                0.0
            },
        ])?;
        validate_cell_span(self.dimensions, min_cell, max_cell)?;
        let radius_sq = radius * radius;
        for x in min_cell[0]..=max_cell[0] {
            for y in min_cell[1]..=max_cell[1] {
                if self.dimensions == Dimensions::D2 {
                    if let Some(bucket) = self.buckets.get(&[x, y, 0]) {
                        for record in bucket {
                            let distance_sq =
                                distance_squared_unchecked(origin, &record.point, self.dimensions);
                            if distance_sq <= radius_sq {
                                visit(record, distance_sq)?;
                            }
                        }
                    }
                } else {
                    for z in min_cell[2]..=max_cell[2] {
                        if let Some(bucket) = self.buckets.get(&[x, y, z]) {
                            for record in bucket {
                                let distance_sq = distance_squared_unchecked(
                                    origin,
                                    &record.point,
                                    self.dimensions,
                                );
                                if distance_sq <= radius_sq {
                                    visit(record, distance_sq)?;
                                }
                            }
                        }
                    }
                }
            }
        }
        Ok(())
    }

    pub fn query_radius_unordered(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        if self.has_multicell_records {
            return self.query_radius_ordered(origin, radius, out);
        }
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
        let radius_sq = radius * radius;
        for x in min_cell[0]..=max_cell[0] {
            for y in min_cell[1]..=max_cell[1] {
                if self.dimensions == Dimensions::D2 {
                    if let Some(bucket) = self.buckets.get(&[x, y, 0]) {
                        for record in bucket {
                            if origin.distance_squared(&record.point)? <= radius_sq {
                                out.push(record.clone());
                            }
                        }
                    }
                } else {
                    for z in min_cell[2]..=max_cell[2] {
                        if let Some(bucket) = self.buckets.get(&[x, y, z]) {
                            for record in bucket {
                                if origin.distance_squared(&record.point)? <= radius_sq {
                                    out.push(record.clone());
                                }
                            }
                        }
                    }
                }
            }
        }
        Ok(())
    }

    pub(super) fn query_radius_ordered(
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
        let radius_sq = radius * radius;
        if !self.has_multicell_records {
            for x in min_cell[0]..=max_cell[0] {
                for y in min_cell[1]..=max_cell[1] {
                    if self.dimensions == Dimensions::D2 {
                        if let Some(bucket) = self.buckets.get(&[x, y, 0]) {
                            for record in bucket {
                                if origin.distance_squared(&record.point)? <= radius_sq {
                                    out.push(record.clone());
                                }
                            }
                        }
                    } else {
                        for z in min_cell[2]..=max_cell[2] {
                            if let Some(bucket) = self.buckets.get(&[x, y, z]) {
                                for record in bucket {
                                    if origin.distance_squared(&record.point)? <= radius_sq {
                                        out.push(record.clone());
                                    }
                                }
                            }
                        }
                    }
                }
            }
            out.sort_by_key(|record| record.entity.raw());
            return Ok(());
        }

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
            if origin.distance_squared(&record.point)? <= radius_sq {
                out.push(record);
            }
        }
        Ok(())
    }

    pub(super) fn query_aabb_ordered(
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
        validate_cell_span(self.dimensions, min_cell, max_cell)?;
        if !self.has_multicell_records {
            for cell in iter_cells(self.dimensions, min_cell, max_cell) {
                if let Some(bucket) = self.buckets.get(&cell) {
                    for record in bucket {
                        match &record.bounds {
                            Some(record_bounds) if bounds.overlaps(record_bounds)? => {
                                out.push(record.clone())
                            }
                            None => {
                                let point_bounds =
                                    SpatialAabb::new(record.point.clone(), record.point.clone())?;
                                if bounds.overlaps(&point_bounds)? {
                                    out.push(record.clone());
                                }
                            }
                            _ => {}
                        }
                    }
                }
            }
            out.sort_by_key(|record| record.entity.raw());
            return Ok(());
        }

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
