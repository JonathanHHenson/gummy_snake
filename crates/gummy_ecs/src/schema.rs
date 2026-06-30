use std::collections::HashMap;
use std::hash::{Hash, Hasher};

use crate::error::{EcsError, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum StorageType {
    Bool,
    Int8,
    UInt8,
    Int16,
    UInt16,
    Int32,
    UInt32,
    Int64,
    UInt64,
    Float32,
    Float64,
    String,
    CategoricalString,
    Vec2F32,
    Vec2F64,
    Vec3F32,
    Vec3F64,
    List,
}

impl StorageType {
    pub fn parse(name: &str) -> Result<Self> {
        match name {
            "Bool" => Ok(Self::Bool),
            "Int8" => Ok(Self::Int8),
            "UInt8" => Ok(Self::UInt8),
            "Int16" => Ok(Self::Int16),
            "UInt16" => Ok(Self::UInt16),
            "Int32" => Ok(Self::Int32),
            "UInt32" => Ok(Self::UInt32),
            "Int64" => Ok(Self::Int64),
            "UInt64" => Ok(Self::UInt64),
            "Float32" => Ok(Self::Float32),
            "Float64" => Ok(Self::Float64),
            "String" => Ok(Self::String),
            "CategoricalString" => Ok(Self::CategoricalString),
            "Vec2F32" => Ok(Self::Vec2F32),
            "Vec2F64" => Ok(Self::Vec2F64),
            "Vec3F32" => Ok(Self::Vec3F32),
            "Vec3F64" => Ok(Self::Vec3F64),
            name if name.starts_with("List[") && name.ends_with(']') => Ok(Self::List),
            other => Err(EcsError::UnknownStorageType(other.to_string())),
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Bool => "Bool",
            Self::Int8 => "Int8",
            Self::UInt8 => "UInt8",
            Self::Int16 => "Int16",
            Self::UInt16 => "UInt16",
            Self::Int32 => "Int32",
            Self::UInt32 => "UInt32",
            Self::Int64 => "Int64",
            Self::UInt64 => "UInt64",
            Self::Float32 => "Float32",
            Self::Float64 => "Float64",
            Self::String => "String",
            Self::CategoricalString => "CategoricalString",
            Self::Vec2F32 => "Vec2F32",
            Self::Vec2F64 => "Vec2F64",
            Self::Vec3F32 => "Vec3F32",
            Self::Vec3F64 => "Vec3F64",
            Self::List => "List",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FieldSchema {
    pub name: String,
    pub storage_type: StorageType,
}

impl FieldSchema {
    pub fn new(name: impl Into<String>, storage_type: StorageType) -> Self {
        Self {
            name: name.into(),
            storage_type,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ComponentSchema {
    pub name: String,
    pub fields: Vec<FieldSchema>,
}

impl ComponentSchema {
    pub fn new(name: impl Into<String>, fields: Vec<FieldSchema>) -> Self {
        Self {
            name: name.into(),
            fields,
        }
    }

    pub fn validate(&self) -> Result<()> {
        if self.name.is_empty() {
            return Err(EcsError::EmptySchemaName);
        }
        for field in &self.fields {
            if field.name.is_empty() {
                return Err(EcsError::EmptyFieldName);
            }
        }
        Ok(())
    }
}

#[derive(Debug, Default, Clone)]
pub struct SchemaRegistry {
    schemas: HashMap<String, ComponentSchema>,
    component_ids: HashMap<String, u32>,
    next_component_id: u32,
}

impl SchemaRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&mut self, schema: ComponentSchema) -> Result<()> {
        schema.validate()?;
        if let Some(existing) = self.schemas.get(&schema.name) {
            if existing == &schema {
                return Ok(());
            }
            return Err(EcsError::DuplicateSchema(schema.name));
        }
        let name = schema.name.clone();
        self.schemas.insert(name.clone(), schema);
        self.component_ids.insert(name, self.next_component_id);
        self.next_component_id = self.next_component_id.wrapping_add(1);
        Ok(())
    }

    pub fn get(&self, name: &str) -> Option<&ComponentSchema> {
        self.schemas.get(name)
    }

    pub fn contains(&self, name: &str) -> bool {
        self.schemas.contains_key(name)
    }

    pub fn component_id(&self, name: &str) -> Option<u32> {
        self.component_ids.get(name).copied()
    }

    pub fn all(&self) -> &HashMap<String, ComponentSchema> {
        &self.schemas
    }

    pub fn len(&self) -> usize {
        self.schemas.len()
    }

    pub fn is_empty(&self) -> bool {
        self.schemas.is_empty()
    }

    pub fn fingerprint(&self) -> u64 {
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        let mut names = self.schemas.keys().collect::<Vec<_>>();
        names.sort();
        for name in names {
            name.hash(&mut hasher);
            if let Some(schema) = self.schemas.get(name) {
                for field in &schema.fields {
                    field.name.hash(&mut hasher);
                    field.storage_type.hash(&mut hasher);
                }
            }
        }
        hasher.finish()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identical_schema_registration_reuses_existing_component_id() {
        let mut registry = SchemaRegistry::new();
        let schema =
            ComponentSchema::new("Health", vec![FieldSchema::new("hp", StorageType::Int32)]);
        registry.register(schema.clone()).unwrap();
        let first_id = registry.component_id("Health").unwrap();
        registry.register(schema).unwrap();
        assert_eq!(registry.component_id("Health"), Some(first_id));
        assert_eq!(registry.len(), 1);
    }

    #[test]
    fn conflicting_schema_name_is_rejected() {
        let mut registry = SchemaRegistry::new();
        registry
            .register(ComponentSchema::new(
                "Health",
                vec![FieldSchema::new("hp", StorageType::Int32)],
            ))
            .unwrap();
        assert!(matches!(
            registry.register(ComponentSchema::new(
                "Health",
                vec![FieldSchema::new("value", StorageType::Int32)],
            )),
            Err(EcsError::DuplicateSchema(_))
        ));
    }
}
