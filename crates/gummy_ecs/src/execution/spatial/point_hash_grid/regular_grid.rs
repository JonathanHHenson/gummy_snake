use crate::error::Result;
use crate::spatial::Dimensions;

use super::{
    DirectPointRecord, DIRECT_POINT_HASH_GRID_DENSE_MAX_CELLS,
    DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER,
};

#[derive(Debug, Clone)]
pub(super) struct DirectPointRegularGrid {
    x0: f64,
    y0: f64,
    dx: f64,
    dy: f64,
    width: usize,
    height: usize,
    cells: Vec<Option<usize>>,
}

impl DirectPointRegularGrid {
    pub(super) fn new(records: &[DirectPointRecord]) -> Option<Self> {
        if records.len() < 8 {
            return None;
        }
        if records
            .iter()
            .any(|record| record.point.dimensions() != Dimensions::D2)
        {
            return None;
        }
        if records.len() >= 256 {
            let sample_len = records.len().min(512);
            let sample = &records[..sample_len];
            let sample_xs = sorted_unique_axis(sample, 0);
            let sample_ys = sorted_unique_axis(sample, 1);
            if sample_xs.len().saturating_mul(sample_ys.len())
                > sample_len.saturating_mul(DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER)
            {
                return None;
            }
        }
        let xs = sorted_unique_axis(records, 0);
        let ys = sorted_unique_axis(records, 1);
        let dx = regular_axis_spacing(&xs)?;
        let dy = regular_axis_spacing(&ys)?;
        let width = xs.len();
        let height = ys.len();
        let total = width.checked_mul(height)?;
        let dense_budget = records
            .len()
            .saturating_mul(DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER)
            .max(4096);
        if total > DIRECT_POINT_HASH_GRID_DENSE_MAX_CELLS || total > dense_budget {
            return None;
        }
        let x0 = xs[0];
        let y0 = ys[0];
        let x_tolerance = regular_grid_tolerance(dx);
        let y_tolerance = regular_grid_tolerance(dy);
        let mut cells = vec![None; total];
        for (record_index, record) in records.iter().enumerate() {
            let ix = regular_grid_axis_index(record.point.coord(0), x0, dx, width, x_tolerance)?;
            let iy = regular_grid_axis_index(record.point.coord(1), y0, dy, height, y_tolerance)?;
            let cell_index = iy.checked_mul(width)?.checked_add(ix)?;
            if cells[cell_index].replace(record_index).is_some() {
                return None;
            }
        }
        Some(Self {
            x0,
            y0,
            dx,
            dy,
            width,
            height,
            cells,
        })
    }

    pub(super) fn visit_radius<F>(
        &self,
        records: &[DirectPointRecord],
        origin_x: f64,
        origin_y: f64,
        radius: f64,
        radius_sq: f64,
        visit: &mut F,
    ) -> Result<()>
    where
        F: FnMut(usize, &DirectPointRecord, f64) -> Result<()>,
    {
        let min_x = regular_grid_query_min(origin_x - radius, self.x0, self.dx);
        let max_x = regular_grid_query_max(origin_x + radius, self.x0, self.dx);
        let min_y = regular_grid_query_min(origin_y - radius, self.y0, self.dy);
        let max_y = regular_grid_query_max(origin_y + radius, self.y0, self.dy);
        let min_x = min_x.clamp(0, self.width.saturating_sub(1) as i64) as usize;
        let max_x = max_x.clamp(0, self.width.saturating_sub(1) as i64) as usize;
        let min_y = min_y.clamp(0, self.height.saturating_sub(1) as i64) as usize;
        let max_y = max_y.clamp(0, self.height.saturating_sub(1) as i64) as usize;
        if min_x > max_x || min_y > max_y {
            return Ok(());
        }
        for iy in min_y..=max_y {
            let row = iy * self.width;
            for ix in min_x..=max_x {
                let Some(record_index) = self.cells[row + ix] else {
                    continue;
                };
                let record = &records[record_index];
                let dx = record.point.coord(0) - origin_x;
                let dy = record.point.coord(1) - origin_y;
                let distance_sq = dx * dx + dy * dy;
                if distance_sq <= radius_sq {
                    visit(record_index, record, distance_sq)?;
                }
            }
        }
        Ok(())
    }
}

fn sorted_unique_axis(records: &[DirectPointRecord], axis: usize) -> Vec<f64> {
    let mut values = records
        .iter()
        .map(|record| record.point.coord(axis))
        .collect::<Vec<_>>();
    values.sort_by(f64::total_cmp);
    values.dedup_by(|left, right| *left == *right);
    values
}

fn regular_axis_spacing(values: &[f64]) -> Option<f64> {
    match values {
        [] => None,
        [_] => Some(1.0),
        [first, second, rest @ ..] => {
            let spacing = second - first;
            if !spacing.is_finite() || spacing <= 0.0 {
                return None;
            }
            let tolerance = regular_grid_tolerance(spacing);
            let mut previous = *second;
            for value in rest {
                let delta = *value - previous;
                if (delta - spacing).abs() > tolerance {
                    return None;
                }
                previous = *value;
            }
            Some(spacing)
        }
    }
}

fn regular_grid_tolerance(spacing: f64) -> f64 {
    spacing.abs().max(1.0) * 1.0e-9
}

fn regular_grid_axis_index(
    value: f64,
    origin: f64,
    spacing: f64,
    len: usize,
    tolerance: f64,
) -> Option<usize> {
    let index = ((value - origin) / spacing).round();
    if index < 0.0 || index > len.saturating_sub(1) as f64 {
        return None;
    }
    let expected = origin + index * spacing;
    if (expected - value).abs() > tolerance {
        return None;
    }
    Some(index as usize)
}

fn regular_grid_query_min(value: f64, origin: f64, spacing: f64) -> i64 {
    ((value - origin) / spacing - 1.0e-9).ceil() as i64
}

fn regular_grid_query_max(value: f64, origin: f64, spacing: f64) -> i64 {
    ((value - origin) / spacing + 1.0e-9).floor() as i64
}
