use crate::spatial::Dimensions;

use super::{
    DIRECT_POINT_HASH_GRID_DENSE_CELL_PADDING, DIRECT_POINT_HASH_GRID_DENSE_MAX_CELLS,
    DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER,
};

#[derive(Debug, Clone)]
pub(super) struct DirectPointDenseBuckets {
    min_cell: [i64; 3],
    spans: [usize; 3],
    buckets: Vec<Vec<usize>>,
}

impl DirectPointDenseBuckets {
    pub(super) fn new(dimensions: Dimensions, cells: &[[i64; 3]]) -> Option<Self> {
        if cells.is_empty() {
            return None;
        }
        let axis_count = dimensions.len();
        let mut min_cell = [i64::MAX; 3];
        let mut max_cell = [i64::MIN; 3];
        for cell in cells {
            for axis in 0..axis_count {
                min_cell[axis] = min_cell[axis].min(cell[axis]);
                max_cell[axis] = max_cell[axis].max(cell[axis]);
            }
        }
        for axis in 0..axis_count {
            min_cell[axis] =
                min_cell[axis].saturating_sub(DIRECT_POINT_HASH_GRID_DENSE_CELL_PADDING);
            max_cell[axis] =
                max_cell[axis].saturating_add(DIRECT_POINT_HASH_GRID_DENSE_CELL_PADDING);
        }
        for axis in axis_count..3 {
            min_cell[axis] = 0;
            max_cell[axis] = 0;
        }
        let mut spans = [1_usize; 3];
        let mut total = 1_usize;
        for axis in 0..axis_count {
            let span = max_cell[axis]
                .checked_sub(min_cell[axis])
                .and_then(|value| value.checked_add(1))?;
            let span = usize::try_from(span).ok()?;
            spans[axis] = span;
            total = total.checked_mul(span)?;
        }
        let dense_budget = cells
            .len()
            .saturating_mul(DIRECT_POINT_HASH_GRID_DENSE_RECORD_MULTIPLIER)
            .max(4096);
        if total > DIRECT_POINT_HASH_GRID_DENSE_MAX_CELLS || total > dense_budget {
            return None;
        }
        Some(Self {
            min_cell,
            spans,
            buckets: vec![Vec::new(); total],
        })
    }

    pub(super) fn try_push(&mut self, cell: [i64; 3], record_index: usize) -> bool {
        let Some(index) = self.bucket_index(cell) else {
            return false;
        };
        self.buckets[index].push(record_index);
        true
    }

    pub(super) fn remove(&mut self, cell: [i64; 3], record_index: usize) -> bool {
        let Some(index) = self.bucket_index(cell) else {
            return false;
        };
        let Some(bucket) = self.buckets.get_mut(index) else {
            return false;
        };
        let Some(position) = bucket
            .iter()
            .position(|candidate| *candidate == record_index)
        else {
            return false;
        };
        bucket.swap_remove(position);
        true
    }

    pub(super) fn bucket(&self, cell: [i64; 3]) -> Option<&[usize]> {
        self.bucket_index(cell)
            .and_then(|index| self.buckets.get(index).map(Vec::as_slice))
    }

    fn bucket_index(&self, cell: [i64; 3]) -> Option<usize> {
        let mut index = 0_usize;
        let mut stride = 1_usize;
        for (axis, coord) in cell.iter().enumerate() {
            let relative = coord.checked_sub(self.min_cell[axis])?;
            let relative = usize::try_from(relative).ok()?;
            if relative >= self.spans[axis] {
                return None;
            }
            index = index.checked_add(relative.checked_mul(stride)?)?;
            stride = stride.checked_mul(self.spans[axis])?;
        }
        Some(index)
    }
}
