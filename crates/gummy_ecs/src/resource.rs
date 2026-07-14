use crate::archetype::ComponentRow;
use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::schema::{ComponentId, FieldId, SchemaRegistry};

#[derive(Debug, Clone, PartialEq)]
struct ResourceRow {
    component: ComponentId,
    values: Vec<EcsValue>,
}

#[derive(Debug, Default, Clone, PartialEq)]
pub struct ResourceStore {
    rows: Vec<Option<ResourceRow>>,
    revisions: Vec<u64>,
    len: usize,
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
        let component = registry
            .component_id(&name)
            .ok_or_else(|| EcsError::UnknownSchema(name.clone()))?;
        let schema = registry
            .get_by_id(component)
            .expect("registered component ID must resolve");
        let mut values = Vec::with_capacity(schema.fields.len());
        for field in &schema.fields {
            values.push(
                value
                    .get(&field.name)
                    .cloned()
                    .ok_or_else(|| EcsError::UnknownField {
                        component: name.clone(),
                        field: field.name.clone(),
                    })?,
            );
        }
        for field in value.keys() {
            if !schema
                .fields
                .iter()
                .any(|candidate| &candidate.name == field)
            {
                return Err(EcsError::UnknownField {
                    component: name.clone(),
                    field: field.clone(),
                });
            }
        }
        self.ensure_component_slot(component);
        if self.rows[component.index()].is_none() {
            self.len += 1;
        }
        self.rows[component.index()] = Some(ResourceRow { component, values });
        self.revisions[component.index()] = self.revisions[component.index()].saturating_add(1);
        Ok(())
    }

    pub fn remove(&mut self, registry: &SchemaRegistry, name: &str) -> Result<ComponentRow> {
        let component = self.component_id(registry, name)?;
        let row = self
            .rows
            .get_mut(component.index())
            .and_then(Option::take)
            .ok_or_else(|| EcsError::MissingResource(name.to_string()))?;
        self.len = self.len.saturating_sub(1);
        self.revisions[component.index()] = self.revisions[component.index()].saturating_add(1);
        let schema = registry
            .get_by_id(component)
            .expect("registered component ID must resolve");
        Ok(schema
            .fields
            .iter()
            .zip(row.values)
            .map(|(field, value)| (field.name.clone(), value))
            .collect())
    }

    pub fn set_field(
        &mut self,
        registry: &SchemaRegistry,
        name: &str,
        field: &str,
        value: EcsValue,
    ) -> Result<()> {
        let field_id = self.field_id(registry, name, field)?;
        let row = self.row_mut(name, field_id.component())?;
        row.values[field_id.index()] = value;
        self.revisions[field_id.component().index()] =
            self.revisions[field_id.component().index()].saturating_add(1);
        Ok(())
    }

    pub fn get_field(
        &self,
        registry: &SchemaRegistry,
        name: &str,
        field: &str,
    ) -> Result<EcsValue> {
        let field_id = self.field_id(registry, name, field)?;
        self.row(name, field_id.component())?
            .values
            .get(field_id.index())
            .cloned()
            .ok_or_else(|| EcsError::UnknownField {
                component: name.to_string(),
                field: field.to_string(),
            })
    }

    pub fn contains(&self, registry: &SchemaRegistry, name: &str) -> bool {
        registry
            .component_id(name)
            .and_then(|component| self.rows.get(component.index()))
            .is_some_and(Option::is_some)
    }

    pub fn len(&self) -> usize {
        self.len
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    pub fn revision(&self, registry: &SchemaRegistry, name: &str) -> u64 {
        registry
            .component_id(name)
            .and_then(|component| self.revisions.get(component.index()))
            .copied()
            .unwrap_or(0)
    }

    pub fn estimated_bytes(&self) -> usize {
        self.rows.capacity() * std::mem::size_of::<Option<ResourceRow>>()
            + self.revisions.capacity() * std::mem::size_of::<u64>()
            + self
                .rows
                .iter()
                .flatten()
                .map(|row| row.values.capacity() * std::mem::size_of::<EcsValue>())
                .sum::<usize>()
    }

    fn ensure_component_slot(&mut self, component: ComponentId) {
        if self.rows.len() <= component.index() {
            self.rows.resize_with(component.index() + 1, || None);
            self.revisions.resize(component.index() + 1, 0);
        }
    }

    fn component_id(&self, registry: &SchemaRegistry, name: &str) -> Result<ComponentId> {
        registry
            .component_id(name)
            .ok_or_else(|| EcsError::UnknownSchema(name.to_string()))
    }

    fn field_id(&self, registry: &SchemaRegistry, name: &str, field: &str) -> Result<FieldId> {
        registry
            .field_id(name, field)
            .ok_or_else(|| EcsError::UnknownField {
                component: name.to_string(),
                field: field.to_string(),
            })
    }

    fn row(&self, name: &str, component: ComponentId) -> Result<&ResourceRow> {
        self.rows
            .get(component.index())
            .and_then(Option::as_ref)
            .ok_or_else(|| EcsError::MissingResource(name.to_string()))
    }

    fn row_mut(&mut self, name: &str, component: ComponentId) -> Result<&mut ResourceRow> {
        self.rows
            .get_mut(component.index())
            .and_then(Option::as_mut)
            .ok_or_else(|| EcsError::MissingResource(name.to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{ComponentSchema, FieldSchema, StorageType};

    #[test]
    fn resources_store_typed_singleton_rows_by_stable_ids() {
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
            resources.get_field(&registry, "Gravity", "y").unwrap(),
            EcsValue::F64(0.5)
        );
        resources
            .set_field(&registry, "Gravity", "y", EcsValue::F64(0.25))
            .unwrap();
        assert_eq!(resources.revision(&registry, "Gravity"), 2);
        assert!(resources.estimated_bytes() > 0);
    }
}
