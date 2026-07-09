use std::collections::HashMap;

use crate::archetype::ComponentRow;
use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::schema::SchemaRegistry;

#[derive(Debug, Default, Clone, PartialEq)]
pub struct ResourceStore {
    values: HashMap<String, ComponentRow>,
    revisions: HashMap<String, u64>,
}

impl ResourceStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn insert(
        &mut self,
        registry: &SchemaRegistry,
        name: impl Into<String>,
        value: ComponentRow,
    ) -> Result<()> {
        let name = name.into();
        let schema = registry
            .get(&name)
            .ok_or_else(|| EcsError::UnknownSchema(name.clone()))?;
        for field in &schema.fields {
            if !value.contains_key(&field.name) {
                return Err(EcsError::UnknownField {
                    component: name.clone(),
                    field: field.name.clone(),
                });
            }
        }
        self.values.insert(schema.name.clone(), value);
        *self.revisions.entry(schema.name.clone()).or_insert(0) += 1;
        Ok(())
    }

    pub fn get(&self, name: &str) -> Result<&ComponentRow> {
        self.values
            .get(name)
            .ok_or_else(|| EcsError::MissingResource(name.to_string()))
    }

    pub fn remove(&mut self, name: &str) -> Result<ComponentRow> {
        let removed = self
            .values
            .remove(name)
            .ok_or_else(|| EcsError::MissingResource(name.to_string()))?;
        *self.revisions.entry(name.to_string()).or_insert(0) += 1;
        Ok(removed)
    }

    pub fn set_field(&mut self, name: &str, field: &str, value: EcsValue) -> Result<()> {
        let row = self
            .values
            .get_mut(name)
            .ok_or_else(|| EcsError::MissingResource(name.to_string()))?;
        if !row.contains_key(field) {
            return Err(EcsError::UnknownField {
                component: name.to_string(),
                field: field.to_string(),
            });
        }
        row.insert(field.to_string(), value);
        *self.revisions.entry(name.to_string()).or_insert(0) += 1;
        Ok(())
    }

    pub fn get_field(&self, name: &str, field: &str) -> Result<EcsValue> {
        self.get(name)?
            .get(field)
            .cloned()
            .ok_or_else(|| EcsError::UnknownField {
                component: name.to_string(),
                field: field.to_string(),
            })
    }

    pub fn contains(&self, name: &str) -> bool {
        self.values.contains_key(name)
    }

    pub fn len(&self) -> usize {
        self.values.len()
    }

    pub fn is_empty(&self) -> bool {
        self.values.is_empty()
    }

    pub fn revision(&self, name: &str) -> u64 {
        self.revisions.get(name).copied().unwrap_or(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{ComponentSchema, FieldSchema, StorageType};

    #[test]
    fn resources_store_dataclass_shaped_rows() {
        let mut registry = SchemaRegistry::new();
        registry
            .register(ComponentSchema::new(
                "Gravity",
                vec![FieldSchema::new("y", StorageType::Float64)],
            ))
            .unwrap();
        let mut resources = ResourceStore::new();
        let mut row = ComponentRow::new();
        row.insert("y".to_string(), EcsValue::F64(0.5));
        resources.insert(&registry, "Gravity", row).unwrap();
        assert_eq!(
            resources.get_field("Gravity", "y").unwrap(),
            EcsValue::F64(0.5)
        );
        resources
            .set_field("Gravity", "y", EcsValue::F64(0.25))
            .unwrap();
        assert_eq!(resources.revision("Gravity"), 2);
    }
}
