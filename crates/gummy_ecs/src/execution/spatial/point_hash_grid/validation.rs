use crate::error::{EcsError, Result};
use crate::spatial::Dimensions;

const DIRECT_POINT_HASH_GRID_MAX_QUERY_CELLS: u64 = 1_000_000;

pub(super) fn validate_direct_point_cell_span(
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
        if total > DIRECT_POINT_HASH_GRID_MAX_QUERY_CELLS {
            return Err(EcsError::InvalidSpatialInput(format!(
                "hash grid query spans {total} cells; maximum is {DIRECT_POINT_HASH_GRID_MAX_QUERY_CELLS}"
            )));
        }
    }
    Ok(())
}
