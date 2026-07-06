use rayon::prelude::*;

use crate::error::{EcsError, Result};
use crate::plan::SpatialRelationNode;
use crate::spatial::SpatialRecord;

use super::super::direct_point_hash_grid::{DirectPointHashGrid, DirectPointRecord};
use super::super::spatial_helpers::{dimensions_from_u8, point_from_row_arrays};
use super::super::spatial_support::BuiltSpatialIndex;
use super::super::PlanExecutor;

impl<'a> PlanExecutor<'a> {
    pub(in crate::execution) fn build_direct_spatial_index_for_relation(
        &mut self,
        relation: &SpatialRelationNode,
    ) -> Result<Option<(String, BuiltSpatialIndex)>> {
        if relation.target_bounds.is_some() {
            return Ok(None);
        }
        let Some(target_coords) =
            self.match_direct_spatial_coords(&relation.target_position, &relation.item_query)
        else {
            return Ok(None);
        };
        let index_key = self.spatial_index_cache_key(relation);
        if let Some(index) = self.take_fresh_spatial_index(relation) {
            self.report_algorithm_use(&index);
            return Ok(Some((index_key, index)));
        }
        let item_rows = self
            .query_rows
            .get(&relation.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    relation.item_query
                ))
            })?;
        let item_locations = self.query_locations(&relation.item_query)?;
        let mut target_coord_arrays = Vec::with_capacity(target_coords.len());
        for coord in &target_coords {
            target_coord_arrays.push(self.world.field_f64_rows_for_resolved_entities(
                &coord.component,
                &coord.field,
                &item_locations,
            )?);
        }
        let worker_count = rayon::current_num_threads().max(1);
        self.report.spatial_parallel_workers =
            self.report.spatial_parallel_workers.max(worker_count);
        if item_rows.len() >= worker_count * 32 {
            self.report.spatial_parallel_chunks += worker_count;
        }
        if relation.algorithm.kind == "hash_grid" {
            let records = item_rows
                .par_iter()
                .enumerate()
                .map(|(row_index, entity)| {
                    Ok(DirectPointRecord {
                        entity: *entity,
                        point: point_from_row_arrays(&target_coord_arrays, row_index)?,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            let signature = self.spatial_index_signature(relation);
            let structural_revision = self.world.structural_revision();
            let field_revision = self.spatial_dependency_revision(relation);
            if let Some(mut cached) = self.world.take_spatial_index_cache(&index_key) {
                if cached.signature == signature
                    && cached.structural_revision == structural_revision
                {
                    if let BuiltSpatialIndex::DirectPointHashGrid(direct_index) = &mut cached.index
                    {
                        if direct_index.update_sorted_points(&records)? {
                            self.report.spatial_index_incremental_updates += 1;
                        } else {
                            self.report.spatial_indexes_built += 1;
                            self.report.spatial_index_full_rebuilds += 1;
                        }
                        self.spatial_index_metadata.insert(
                            index_key.clone(),
                            (signature, structural_revision, field_revision),
                        );
                        self.report_algorithm_use(&cached.index);
                        return Ok(Some((index_key, cached.index)));
                    }
                }
            }
            let mut direct_index = DirectPointHashGrid::new(
                dimensions_from_u8(relation.algorithm.dimensions)?,
                relation.algorithm.cell_size.unwrap_or(1.0),
            )?;
            direct_index.build_sorted_points(records)?;
            self.report.spatial_indexes_built += 1;
            self.report.spatial_index_full_rebuilds += 1;
            let index = BuiltSpatialIndex::DirectPointHashGrid(direct_index);
            self.spatial_index_metadata.insert(
                index_key.clone(),
                (signature, structural_revision, field_revision),
            );
            self.report_algorithm_use(&index);
            return Ok(Some((index_key, index)));
        }
        let records = item_rows
            .par_iter()
            .enumerate()
            .map(|(row_index, entity)| {
                Ok(SpatialRecord {
                    entity: *entity,
                    point: point_from_row_arrays(&target_coord_arrays, row_index)?,
                    bounds: None,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let index = self.build_or_update_spatial_index(relation, records)?;
        self.report_algorithm_use(&index);
        Ok(Some((index_key, index)))
    }
}
