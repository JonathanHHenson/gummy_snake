use crate::error::{EcsError, Result};
use crate::spatial::{Dimensions, SpatialAabb, SpatialPoint, SpatialRecord};

pub(super) fn record_overlaps(record: &SpatialRecord, bounds: &SpatialAabb) -> Result<bool> {
    match &record.bounds {
        Some(record_bounds) => bounds.overlaps(record_bounds),
        None => point_in_aabb(&record.point, bounds),
    }
}

pub(super) fn point_in_aabb(point: &SpatialPoint, bounds: &SpatialAabb) -> Result<bool> {
    if point.dimensions() != bounds.dimensions() {
        return Err(EcsError::InvalidSpatialInput(
            "point dimensions do not match bounds dimensions".to_string(),
        ));
    }
    Ok((0..point.dimensions().len()).all(|axis| {
        bounds.minimum().coord(axis) <= point.coord(axis)
            && point.coord(axis) <= bounds.maximum().coord(axis)
    }))
}

pub(super) fn radius_bounds(
    origin: &SpatialPoint,
    radius: f64,
    dimensions: Dimensions,
) -> Result<SpatialAabb> {
    match dimensions {
        Dimensions::D2 => SpatialAabb::point2(
            origin.coord(0) - radius,
            origin.coord(1) - radius,
            origin.coord(0) + radius,
            origin.coord(1) + radius,
        ),
        Dimensions::D3 => SpatialAabb::point3(
            origin.coord(0) - radius,
            origin.coord(1) - radius,
            origin.coord(2) - radius,
            origin.coord(0) + radius,
            origin.coord(1) + radius,
            origin.coord(2) + radius,
        ),
    }
}

pub(super) fn subdivide_bounds(
    bounds: &SpatialAabb,
    dimensions: Dimensions,
) -> Result<Vec<SpatialAabb>> {
    let mid_x = midpoint(bounds, 0);
    let mid_y = midpoint(bounds, 1);
    if dimensions == Dimensions::D2 {
        return Ok(vec![
            SpatialAabb::point2(
                bounds.minimum().coord(0),
                bounds.minimum().coord(1),
                mid_x,
                mid_y,
            )?,
            SpatialAabb::point2(
                mid_x,
                bounds.minimum().coord(1),
                bounds.maximum().coord(0),
                mid_y,
            )?,
            SpatialAabb::point2(
                bounds.minimum().coord(0),
                mid_y,
                mid_x,
                bounds.maximum().coord(1),
            )?,
            SpatialAabb::point2(
                mid_x,
                mid_y,
                bounds.maximum().coord(0),
                bounds.maximum().coord(1),
            )?,
        ]);
    }
    let mid_z = midpoint(bounds, 2);
    let mut children = Vec::new();
    for min_x in [bounds.minimum().coord(0), mid_x] {
        let max_x = if min_x == bounds.minimum().coord(0) {
            mid_x
        } else {
            bounds.maximum().coord(0)
        };
        for min_y in [bounds.minimum().coord(1), mid_y] {
            let max_y = if min_y == bounds.minimum().coord(1) {
                mid_y
            } else {
                bounds.maximum().coord(1)
            };
            for min_z in [bounds.minimum().coord(2), mid_z] {
                let max_z = if min_z == bounds.minimum().coord(2) {
                    mid_z
                } else {
                    bounds.maximum().coord(2)
                };
                children.push(SpatialAabb::point3(
                    min_x, min_y, min_z, max_x, max_y, max_z,
                )?);
            }
        }
    }
    Ok(children)
}

pub(super) fn midpoint(bounds: &SpatialAabb, axis: usize) -> f64 {
    (bounds.minimum().coord(axis) + bounds.maximum().coord(axis)) * 0.5
}
