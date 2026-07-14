use std::collections::HashMap;

use crate::column::{Column, EcsValue};
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::schema::{ComponentId, ComponentSchema, SchemaRegistry};

pub type ComponentRow = HashMap<String, EcsValue>;
pub type EntityRowData = HashMap<String, ComponentRow>;

#[derive(Debug, Clone, Default, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ComponentSetKey(Vec<ComponentId>);

impl ComponentSetKey {
    pub fn new(components: impl IntoIterator<Item = ComponentId>) -> Self {
        let mut ids = components.into_iter().collect::<Vec<_>>();
        ids.sort_unstable();
        ids.dedup();
        Self(ids)
    }

    pub fn empty() -> Self {
        Self::default()
    }

    pub fn contains(&self, component: ComponentId) -> bool {
        self.0.binary_search(&component).is_ok()
    }

    pub fn is_superset_of(&self, required: &Self) -> bool {
        required.0.iter().all(|component| self.contains(*component))
    }

    pub fn is_disjoint_from(&self, excluded: &Self) -> bool {
        excluded
            .0
            .iter()
            .all(|component| !self.contains(*component))
    }

    pub fn with(&self, component: ComponentId) -> Self {
        let mut ids = self.0.clone();
        match ids.binary_search(&component) {
            Ok(_) => Self(ids),
            Err(index) => {
                ids.insert(index, component);
                Self(ids)
            }
        }
    }

    pub fn without(&self, component: ComponentId) -> Self {
        let mut ids = self.0.clone();
        if let Ok(index) = ids.binary_search(&component) {
            ids.remove(index);
        }
        Self(ids)
    }

    pub fn components(&self) -> &[ComponentId] {
        &self.0
    }
}

#[derive(Debug, Clone)]
pub struct ComponentTable {
    schema_name: String,
    columns: HashMap<String, Column>,
}

impl ComponentTable {
    pub fn from_schema(schema: &ComponentSchema) -> Self {
        let columns = schema
            .fields
            .iter()
            .map(|field| (field.name.clone(), Column::empty(field.storage_type)))
            .collect();
        Self {
            schema_name: schema.name.clone(),
            columns,
        }
    }

    pub fn push_default_row(&mut self) {
        for column in self.columns.values_mut() {
            column.push_default();
        }
    }

    pub fn push_row(&mut self, values: Option<&ComponentRow>) -> Result<()> {
        for (field_name, column) in &mut self.columns {
            let value = values
                .and_then(|row| row.get(field_name).cloned())
                .unwrap_or_else(|| column.default_value());
            column.push_value(value)?;
        }
        Ok(())
    }

    fn validate_move_to(&self, target: &Self) -> Result<()> {
        if self.columns.len() != target.columns.len() {
            return Err(EcsError::MissingComponent(self.schema_name.clone()));
        }
        for (field, source) in &self.columns {
            let target = target
                .columns
                .get(field)
                .ok_or_else(|| EcsError::UnknownField {
                    component: self.schema_name.clone(),
                    field: field.clone(),
                })?;
            if source.storage_type() != target.storage_type() {
                return Err(EcsError::ColumnTypeMismatch {
                    expected: target.family_name(),
                    got: source.family_name(),
                });
            }
        }
        Ok(())
    }

    fn move_row_to(&mut self, target: &mut Self, row: usize) -> Result<()> {
        self.validate_move_to(target)?;
        for (field, source) in &mut self.columns {
            let target = target
                .columns
                .get_mut(field)
                .expect("component table move was prevalidated");
            source.move_swap_removed_to(target, row)?;
        }
        Ok(())
    }

    pub fn set_field(&mut self, row: usize, field_name: &str, value: EcsValue) -> Result<()> {
        let column = self
            .columns
            .get_mut(field_name)
            .ok_or_else(|| EcsError::UnknownField {
                component: self.schema_name.clone(),
                field: field_name.to_string(),
            })?;
        column.set(row, value)
    }

    pub fn set_field_f64(&mut self, row: usize, field_name: &str, value: f64) -> Result<()> {
        let column = self
            .columns
            .get_mut(field_name)
            .ok_or_else(|| EcsError::UnknownField {
                component: self.schema_name.clone(),
                field: field_name.to_string(),
            })?;
        column.set_f64(row, value)
    }

    pub fn set_field_f64_rows(&mut self, field_name: &str, rows: &[(usize, f64)]) -> Result<usize> {
        let column = self
            .columns
            .get_mut(field_name)
            .ok_or_else(|| EcsError::UnknownField {
                component: self.schema_name.clone(),
                field: field_name.to_string(),
            })?;
        column.set_f64_rows(rows)
    }

    pub fn get_field(&self, row: usize, field_name: &str) -> Result<EcsValue> {
        let column = self
            .columns
            .get(field_name)
            .ok_or_else(|| EcsError::UnknownField {
                component: self.schema_name.clone(),
                field: field_name.to_string(),
            })?;
        column.get(row)
    }

    pub fn get_field_f64(&self, row: usize, field_name: &str) -> Result<f64> {
        let column = self
            .columns
            .get(field_name)
            .ok_or_else(|| EcsError::UnknownField {
                component: self.schema_name.clone(),
                field: field_name.to_string(),
            })?;
        column.get_f64(row)
    }

    pub fn get_field_f64_slice(&self, field_name: &str) -> Result<Option<&[f64]>> {
        let column = self
            .columns
            .get(field_name)
            .ok_or_else(|| EcsError::UnknownField {
                component: self.schema_name.clone(),
                field: field_name.to_string(),
            })?;
        Ok(column.f64_slice())
    }

    pub fn get_field_f64_slice_mut(&mut self, field_name: &str) -> Result<Option<&mut [f64]>> {
        let column = self
            .columns
            .get_mut(field_name)
            .ok_or_else(|| EcsError::UnknownField {
                component: self.schema_name.clone(),
                field: field_name.to_string(),
            })?;
        Ok(column.f64_slice_mut())
    }

    pub fn remove_row(&mut self, row: usize) -> Result<()> {
        for column in self.columns.values_mut() {
            column.swap_remove(row)?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RemovedRow {
    pub entity: Entity,
    pub swapped_entity: Option<Entity>,
}

#[derive(Debug, Clone)]
pub struct Archetype {
    key: ComponentSetKey,
    entities: Vec<Entity>,
    components: HashMap<ComponentId, ComponentTable>,
    component_names: HashMap<String, ComponentId>,
    add_edges: HashMap<ComponentId, usize>,
    remove_edges: HashMap<ComponentId, usize>,
}

impl Archetype {
    pub fn new(key: ComponentSetKey, schemas: &SchemaRegistry) -> Result<Self> {
        let mut components = HashMap::new();
        let mut component_names = HashMap::new();
        for component_id in key.components() {
            let schema = schemas.get_by_id(*component_id).ok_or_else(|| {
                EcsError::UnknownSchema(format!("component id {}", component_id.raw()))
            })?;
            components.insert(*component_id, ComponentTable::from_schema(schema));
            component_names.insert(schema.name.clone(), *component_id);
        }
        Ok(Self {
            key,
            entities: Vec::new(),
            components,
            component_names,
            add_edges: HashMap::new(),
            remove_edges: HashMap::new(),
        })
    }

    pub fn key(&self) -> &ComponentSetKey {
        &self.key
    }

    pub fn len(&self) -> usize {
        self.entities.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entities.is_empty()
    }

    pub fn entities(&self) -> &[Entity] {
        &self.entities
    }

    pub fn transition_add(&self, component: ComponentId) -> Option<usize> {
        self.add_edges.get(&component).copied()
    }

    pub fn transition_remove(&self, component: ComponentId) -> Option<usize> {
        self.remove_edges.get(&component).copied()
    }

    pub fn cache_add_transition(&mut self, component: ComponentId, target: usize) {
        self.add_edges.insert(component, target);
    }

    pub fn cache_remove_transition(&mut self, component: ComponentId, target: usize) {
        self.remove_edges.insert(component, target);
    }

    pub fn push_row(&mut self, entity: Entity, data: Option<&EntityRowData>) -> Result<usize> {
        let row = self.entities.len();
        for (component_id, table) in &mut self.components {
            let component_name = self
                .component_names
                .iter()
                .find_map(|(name, id)| (id == component_id).then_some(name.as_str()))
                .expect("archetype component id has a name");
            table.push_row(data.and_then(|row_data| row_data.get(component_name)))?;
        }
        self.entities.push(entity);
        Ok(row)
    }

    pub fn push_default_row(&mut self, entity: Entity) -> Result<usize> {
        let row = self.entities.len();
        for table in self.components.values_mut() {
            table.push_default_row();
        }
        self.entities.push(entity);
        Ok(row)
    }

    pub fn remove_row_swap_remove(&mut self, row: usize) -> Result<RemovedRow> {
        if row >= self.entities.len() {
            return Err(EcsError::RowOutOfBounds);
        }
        for table in self.components.values_mut() {
            table.remove_row(row)?;
        }
        let entity = self.entities.swap_remove(row);
        let swapped_entity = self.entities.get(row).copied();
        Ok(RemovedRow {
            entity,
            swapped_entity,
        })
    }

    pub fn move_row_to(
        &mut self,
        row: usize,
        target: &mut Self,
        entity: Entity,
    ) -> Result<RemovedRow> {
        if self.entities.get(row).copied() != Some(entity) {
            return Err(EcsError::RowOutOfBounds);
        }
        for component_id in target.key.components() {
            if let Some(source) = self.components.get(component_id) {
                let target_table = target
                    .components
                    .get(component_id)
                    .expect("target archetype key and tables agree");
                source.validate_move_to(target_table)?;
            }
        }

        for component_id in target.key.components() {
            let target_table = target
                .components
                .get_mut(component_id)
                .expect("target archetype key and tables agree");
            if let Some(source) = self.components.get_mut(component_id) {
                source.move_row_to(target_table, row)?;
            } else {
                target_table.push_default_row();
            }
        }
        for component_id in self.key.components() {
            if !target.key.contains(*component_id) {
                self.components
                    .get_mut(component_id)
                    .expect("source archetype key and tables agree")
                    .remove_row(row)?;
            }
        }

        let removed_entity = self.entities.swap_remove(row);
        debug_assert_eq!(removed_entity, entity);
        let swapped_entity = self.entities.get(row).copied();
        target.entities.push(entity);
        Ok(RemovedRow {
            entity,
            swapped_entity,
        })
    }

    fn component_id(&self, component_name: &str) -> Result<ComponentId> {
        self.component_names
            .get(component_name)
            .copied()
            .ok_or_else(|| EcsError::MissingComponent(component_name.to_string()))
    }

    pub fn set_field(
        &mut self,
        row: usize,
        component_name: &str,
        field_name: &str,
        value: EcsValue,
    ) -> Result<()> {
        let component_id = self.component_id(component_name)?;
        self.components
            .get_mut(&component_id)
            .expect("component name map and tables agree")
            .set_field(row, field_name, value)
    }

    pub fn set_field_f64(
        &mut self,
        row: usize,
        component_name: &str,
        field_name: &str,
        value: f64,
    ) -> Result<()> {
        let component_id = self.component_id(component_name)?;
        self.components
            .get_mut(&component_id)
            .expect("component name map and tables agree")
            .set_field_f64(row, field_name, value)
    }

    pub fn set_field_f64_rows(
        &mut self,
        component_name: &str,
        field_name: &str,
        rows: &[(usize, f64)],
    ) -> Result<usize> {
        let component_id = self.component_id(component_name)?;
        self.components
            .get_mut(&component_id)
            .expect("component name map and tables agree")
            .set_field_f64_rows(field_name, rows)
    }

    pub fn get_field(
        &self,
        row: usize,
        component_name: &str,
        field_name: &str,
    ) -> Result<EcsValue> {
        let component_id = self.component_id(component_name)?;
        self.components
            .get(&component_id)
            .expect("component name map and tables agree")
            .get_field(row, field_name)
    }

    pub fn get_field_f64(&self, row: usize, component_name: &str, field_name: &str) -> Result<f64> {
        let component_id = self.component_id(component_name)?;
        self.components
            .get(&component_id)
            .expect("component name map and tables agree")
            .get_field_f64(row, field_name)
    }

    pub fn get_field_f64_slice(
        &self,
        component_name: &str,
        field_name: &str,
    ) -> Result<Option<&[f64]>> {
        let component_id = self.component_id(component_name)?;
        self.components
            .get(&component_id)
            .expect("component name map and tables agree")
            .get_field_f64_slice(field_name)
    }

    pub fn get_field_f64_slice_mut(
        &mut self,
        component_name: &str,
        field_name: &str,
    ) -> Result<Option<&mut [f64]>> {
        let component_id = self.component_id(component_name)?;
        self.components
            .get_mut(&component_id)
            .expect("component name map and tables agree")
            .get_field_f64_slice_mut(field_name)
    }

    pub fn has_component(&self, component_id: ComponentId) -> bool {
        self.key.contains(component_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{FieldSchema, StorageType};

    fn registry() -> SchemaRegistry {
        let mut schemas = SchemaRegistry::new();
        schemas
            .register(ComponentSchema::new(
                "Position",
                vec![FieldSchema::new("x", StorageType::Int64)],
            ))
            .unwrap();
        schemas
            .register(ComponentSchema::new(
                "Velocity",
                vec![FieldSchema::new("dx", StorageType::Int64)],
            ))
            .unwrap();
        schemas
    }

    #[test]
    fn component_set_key_is_sorted_and_deduped() {
        let schemas = registry();
        let position = schemas.component_id("Position").unwrap();
        let velocity = schemas.component_id("Velocity").unwrap();
        let key = ComponentSetKey::new([velocity, position, position]);
        assert_eq!(key.components(), &[position, velocity]);
        assert!(key.is_superset_of(&ComponentSetKey::new([position])));
    }

    #[test]
    fn archetype_moves_typed_rows_directly_with_swap_remove() {
        let schemas = registry();
        let position = schemas.component_id("Position").unwrap();
        let velocity = schemas.component_id("Velocity").unwrap();
        let mut source = Archetype::new(ComponentSetKey::new([position]), &schemas).unwrap();
        let mut target =
            Archetype::new(ComponentSetKey::new([position, velocity]), &schemas).unwrap();
        let first = Entity {
            index: 0,
            generation: 0,
        };
        let second = Entity {
            index: 1,
            generation: 0,
        };
        source.push_default_row(first).unwrap();
        source.push_default_row(second).unwrap();
        source
            .set_field(0, "Position", "x", EcsValue::I64(9_007_199_254_740_993))
            .unwrap();

        let removed = source.move_row_to(0, &mut target, first).unwrap();
        assert_eq!(removed.swapped_entity, Some(second));
        assert_eq!(
            target.get_field(0, "Position", "x").unwrap(),
            EcsValue::I64(9_007_199_254_740_993)
        );
        assert_eq!(
            target.get_field(0, "Velocity", "dx").unwrap(),
            EcsValue::I64(0)
        );
    }
}
