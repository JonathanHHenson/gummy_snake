use std::collections::HashMap;

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};

use super::World;

fn contiguous_location_range(locations: &[(usize, usize)]) -> Option<(usize, usize, usize)> {
    let (first_archetype, first_row) = locations.first().copied()?;
    for (offset, (archetype, row)) in locations.iter().copied().enumerate() {
        if archetype != first_archetype || row != first_row + offset {
            return None;
        }
    }
    Some((first_archetype, first_row, first_row + locations.len()))
}

impl World {
    pub fn set_field(
        &mut self,
        entity: Entity,
        component: &str,
        field: &str,
        value: EcsValue,
    ) -> Result<()> {
        let value = self.coerce_value_for_component_field(component, field, value)?;
        let location = self.location(entity)?;
        self.archetypes[location.archetype].set_field(location.row, component, field, value)?;
        self.note_field_revision(component, field);
        Ok(())
    }

    pub(crate) fn set_field_f64_many(
        &mut self,
        component: &str,
        field: &str,
        writes: &[(Entity, f64)],
    ) -> Result<usize> {
        if writes.is_empty() {
            return Ok(0);
        }
        let locations = self.locations_for_entities(writes.iter().map(|(entity, _)| *entity))?;
        let values = writes.iter().map(|(_, value)| *value).collect::<Vec<_>>();
        self.set_field_f64_resolved_strided(component, field, &locations, &values, 0, 1)
    }

    pub(crate) fn locations_for_entities(
        &self,
        entities: impl IntoIterator<Item = Entity>,
    ) -> Result<Vec<(usize, usize)>> {
        let mut locations = Vec::new();
        for entity in entities {
            let location = self.location(entity)?;
            locations.push((location.archetype, location.row));
        }
        Ok(locations)
    }

    pub(crate) fn field_f64_cache_for_resolved_entities(
        &self,
        component: &str,
        field: &str,
        entities: &[Entity],
        locations: &[(usize, usize)],
    ) -> Result<Vec<Option<(u32, f64)>>> {
        if entities.len() != locations.len() {
            return Err(EcsError::InvalidPlan(
                "resolved f64 cache requires one location per entity".to_string(),
            ));
        }
        let max_index = entities
            .iter()
            .map(|entity| entity.index as usize)
            .max()
            .unwrap_or(0);
        let mut values = vec![None; max_index + 1];
        let Some((first_archetype, _)) = locations.first().copied() else {
            return Ok(values);
        };
        if locations
            .iter()
            .all(|(archetype, _)| *archetype == first_archetype)
        {
            if let Some(column) =
                self.archetypes[first_archetype].get_field_f64_slice(component, field)?
            {
                for (entity, (_, row)) in entities.iter().zip(locations.iter()) {
                    let Some(value) = column.get(*row) else {
                        return Err(EcsError::RowOutOfBounds);
                    };
                    values[entity.index as usize] = Some((entity.generation, *value));
                }
                return Ok(values);
            }
        }
        for (entity, (archetype, row)) in entities.iter().zip(locations.iter()) {
            values[entity.index as usize] = Some((
                entity.generation,
                self.archetypes[*archetype].get_field_f64(*row, component, field)?,
            ));
        }
        Ok(values)
    }

    pub(crate) fn field_f64_rows_for_resolved_entities(
        &self,
        component: &str,
        field: &str,
        locations: &[(usize, usize)],
    ) -> Result<Vec<f64>> {
        let mut values = Vec::with_capacity(locations.len());
        let Some((first_archetype, _)) = locations.first().copied() else {
            return Ok(values);
        };
        if locations
            .iter()
            .all(|(archetype, _)| *archetype == first_archetype)
        {
            if let Some(column) =
                self.archetypes[first_archetype].get_field_f64_slice(component, field)?
            {
                if let Some((_, start, end)) = contiguous_location_range(locations) {
                    let Some(slice) = column.get(start..end) else {
                        return Err(EcsError::RowOutOfBounds);
                    };
                    values.extend_from_slice(slice);
                    return Ok(values);
                }
                for (_, row) in locations {
                    let Some(value) = column.get(*row) else {
                        return Err(EcsError::RowOutOfBounds);
                    };
                    values.push(*value);
                }
                return Ok(values);
            }
        }
        for (archetype, row) in locations {
            values.push(self.archetypes[*archetype].get_field_f64(*row, component, field)?);
        }
        Ok(values)
    }

    pub(crate) fn set_field_f64_resolved_strided(
        &mut self,
        component: &str,
        field: &str,
        locations: &[(usize, usize)],
        values: &[f64],
        value_offset: usize,
        value_stride: usize,
    ) -> Result<usize> {
        if locations.is_empty() {
            return Ok(0);
        }
        if value_stride == 0 {
            return Err(EcsError::InvalidPlan(
                "strided f64 writes require a non-zero stride".to_string(),
            ));
        }
        let required_value_index = (locations.len() - 1)
            .checked_mul(value_stride)
            .and_then(|index| index.checked_add(value_offset))
            .ok_or_else(|| EcsError::InvalidPlan("strided f64 write index overflow".to_string()))?;
        if required_value_index >= values.len() {
            return Err(EcsError::InvalidPlan(
                "strided f64 writes do not have enough values".to_string(),
            ));
        }

        let first_archetype = locations[0].0;
        let mut written = 0usize;
        if locations
            .iter()
            .all(|(archetype, _)| *archetype == first_archetype)
        {
            if let Some(column) =
                self.archetypes[first_archetype].get_field_f64_slice_mut(component, field)?
            {
                if let Some((_, start, end)) = contiguous_location_range(locations) {
                    let Some(slice) = column.get_mut(start..end) else {
                        return Err(EcsError::RowOutOfBounds);
                    };
                    for (index, slot) in slice.iter_mut().enumerate() {
                        let value = values[index * value_stride + value_offset];
                        if *slot != value {
                            *slot = value;
                            written += 1;
                        }
                    }
                } else {
                    let len = column.len();
                    for (_, row) in locations {
                        if *row >= len {
                            return Err(EcsError::RowOutOfBounds);
                        }
                    }
                    for (index, (_, row)) in locations.iter().enumerate() {
                        let value = values[index * value_stride + value_offset];
                        if column[*row] != value {
                            column[*row] = value;
                            written += 1;
                        }
                    }
                }
            } else {
                let mut rows = Vec::with_capacity(locations.len());
                for (index, (_, row)) in locations.iter().enumerate() {
                    rows.push((*row, values[index * value_stride + value_offset]));
                }
                written =
                    self.archetypes[first_archetype].set_field_f64_rows(component, field, &rows)?;
            }
        } else {
            let mut by_archetype: HashMap<usize, Vec<(usize, f64)>> = HashMap::new();
            for (index, (archetype, row)) in locations.iter().enumerate() {
                by_archetype
                    .entry(*archetype)
                    .or_default()
                    .push((*row, values[index * value_stride + value_offset]));
            }
            for (archetype, rows) in by_archetype {
                written +=
                    self.archetypes[archetype].set_field_f64_rows(component, field, &rows)?;
            }
        }
        self.note_field_revision_by(component, field, written as u64);
        Ok(written)
    }

    pub fn get_field(&self, entity: Entity, component: &str, field: &str) -> Result<EcsValue> {
        let location = self.location(entity)?;
        self.archetypes[location.archetype].get_field(location.row, component, field)
    }

    pub fn get_field_f64(&self, entity: Entity, component: &str, field: &str) -> Result<f64> {
        let location = self.location(entity)?;
        self.archetypes[location.archetype].get_field_f64(location.row, component, field)
    }
}
