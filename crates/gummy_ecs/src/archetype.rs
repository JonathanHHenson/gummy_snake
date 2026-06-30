use std::collections::{BTreeSet, HashMap};

use crate::column::{Column, EcsValue};
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::schema::ComponentSchema;

pub type ComponentRow = HashMap<String, EcsValue>;
pub type EntityRowData = HashMap<String, ComponentRow>;

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ComponentSetKey(Vec<String>);

impl ComponentSetKey {
    pub const TAG_PREFIX: &'static str = "#tag:";

    pub fn new(components: impl IntoIterator<Item = impl Into<String>>) -> Self {
        let names: BTreeSet<String> = components.into_iter().map(Into::into).collect();
        Self(names.into_iter().collect())
    }

    pub fn empty() -> Self {
        Self(Vec::new())
    }

    pub fn tag_key(tag: &str) -> String {
        if tag.starts_with(Self::TAG_PREFIX) {
            tag.to_string()
        } else {
            format!("{}{tag}", Self::TAG_PREFIX)
        }
    }

    pub fn is_tag_name(name: &str) -> bool {
        name.starts_with(Self::TAG_PREFIX)
    }

    pub fn contains(&self, component: &str) -> bool {
        self.0
            .binary_search_by(|name| name.as_str().cmp(component))
            .is_ok()
    }

    pub fn contains_component(&self, component: &str) -> bool {
        !Self::is_tag_name(component) && self.contains(component)
    }

    pub fn contains_tag(&self, tag: &str) -> bool {
        self.contains(&Self::tag_key(tag))
    }

    pub fn is_superset_of(&self, required: &ComponentSetKey) -> bool {
        required.0.iter().all(|component| self.contains(component))
    }

    pub fn with(&self, component: impl Into<String>) -> Self {
        let mut names = self.0.clone();
        names.push(component.into());
        Self::new(names)
    }

    pub fn with_tag(&self, tag: &str) -> Self {
        self.with(Self::tag_key(tag))
    }

    pub fn without(&self, component: &str) -> Self {
        Self::new(
            self.0
                .iter()
                .filter(|name| name.as_str() != component)
                .cloned(),
        )
    }

    pub fn without_tag(&self, tag: &str) -> Self {
        let key = Self::tag_key(tag);
        self.without(&key)
    }

    pub fn components(&self) -> &[String] {
        &self.0
    }

    pub fn component_names(&self) -> impl Iterator<Item = &String> {
        self.0.iter().filter(|name| !Self::is_tag_name(name))
    }

    pub fn tag_names(&self) -> impl Iterator<Item = &str> {
        self.0
            .iter()
            .filter_map(|name| name.strip_prefix(Self::TAG_PREFIX))
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

    pub fn extract_row_swap_remove(&mut self, row: usize) -> Result<ComponentRow> {
        let mut values = ComponentRow::new();
        for (field_name, column) in &mut self.columns {
            values.insert(field_name.clone(), column.swap_remove(row)?);
        }
        Ok(values)
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
}

#[derive(Debug, Clone)]
pub struct RemovedRow {
    pub entity: Entity,
    pub data: EntityRowData,
    pub swapped_entity: Option<Entity>,
}

#[derive(Debug, Clone)]
pub struct Archetype {
    key: ComponentSetKey,
    entities: Vec<Entity>,
    components: HashMap<String, ComponentTable>,
}

impl Archetype {
    pub fn new(key: ComponentSetKey, schemas: &HashMap<String, ComponentSchema>) -> Result<Self> {
        let mut components = HashMap::new();
        for component_name in key.component_names() {
            let schema = schemas
                .get(component_name)
                .ok_or_else(|| EcsError::UnknownSchema(component_name.clone()))?;
            components.insert(component_name.clone(), ComponentTable::from_schema(schema));
        }
        Ok(Self {
            key,
            entities: Vec::new(),
            components,
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

    pub fn push_row(&mut self, entity: Entity, data: Option<&EntityRowData>) -> Result<usize> {
        let row = self.entities.len();
        self.entities.push(entity);
        for component_name in self.key.component_names() {
            let table = self
                .components
                .get_mut(component_name)
                .ok_or_else(|| EcsError::MissingComponent(component_name.clone()))?;
            table.push_row(data.and_then(|row_data| row_data.get(component_name)))?;
        }
        Ok(row)
    }

    pub fn push_default_row(&mut self, entity: Entity) -> Result<usize> {
        self.push_row(entity, None)
    }

    pub fn remove_row_swap_remove(&mut self, row: usize) -> Result<RemovedRow> {
        if row >= self.entities.len() {
            return Err(EcsError::RowOutOfBounds);
        }
        let entity = self.entities.swap_remove(row);
        let swapped_entity = if row < self.entities.len() {
            Some(self.entities[row])
        } else {
            None
        };
        let mut data = EntityRowData::new();
        for component_name in self.key.component_names() {
            let table = self
                .components
                .get_mut(component_name)
                .ok_or_else(|| EcsError::MissingComponent(component_name.clone()))?;
            data.insert(component_name.clone(), table.extract_row_swap_remove(row)?);
        }
        Ok(RemovedRow {
            entity,
            data,
            swapped_entity,
        })
    }

    pub fn set_field(
        &mut self,
        row: usize,
        component_name: &str,
        field_name: &str,
        value: EcsValue,
    ) -> Result<()> {
        let table = self
            .components
            .get_mut(component_name)
            .ok_or_else(|| EcsError::MissingComponent(component_name.to_string()))?;
        table.set_field(row, field_name, value)
    }

    pub fn get_field(
        &self,
        row: usize,
        component_name: &str,
        field_name: &str,
    ) -> Result<EcsValue> {
        let table = self
            .components
            .get(component_name)
            .ok_or_else(|| EcsError::MissingComponent(component_name.to_string()))?;
        table.get_field(row, field_name)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{FieldSchema, StorageType};

    #[test]
    fn component_set_key_is_sorted_and_deduped() {
        let key = ComponentSetKey::new(["Velocity", "Position", "Position"]);
        assert_eq!(
            key.components(),
            &["Position".to_string(), "Velocity".to_string()]
        );
        assert!(key.is_superset_of(&ComponentSetKey::new(["Position"])));
    }

    #[test]
    fn archetype_moves_rows_with_swap_remove() {
        let mut schemas = HashMap::new();
        schemas.insert(
            "Position".to_string(),
            ComponentSchema::new(
                "Position",
                vec![FieldSchema::new("x", StorageType::Float64)],
            ),
        );
        let mut archetype = Archetype::new(ComponentSetKey::new(["Position"]), &schemas).unwrap();
        let first = Entity {
            index: 0,
            generation: 0,
        };
        let second = Entity {
            index: 1,
            generation: 0,
        };
        archetype.push_default_row(first).unwrap();
        archetype.push_default_row(second).unwrap();
        archetype
            .set_field(0, "Position", "x", EcsValue::F64(42.0))
            .unwrap();
        let removed = archetype.remove_row_swap_remove(0).unwrap();
        assert_eq!(removed.entity, first);
        assert_eq!(removed.swapped_entity, Some(second));
        assert_eq!(removed.data["Position"]["x"], EcsValue::F64(42.0));
    }
}
