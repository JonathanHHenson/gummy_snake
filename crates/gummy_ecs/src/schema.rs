use std::collections::HashMap;
use std::hash::{Hash, Hasher};

use crate::error::{EcsError, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ListElementType {
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
}

impl ListElementType {
    fn parse(name: &str) -> Result<Self> {
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
            other => Err(EcsError::UnknownStorageType(format!("List[{other}]"))),
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
        }
    }

    pub fn storage_type(self) -> StorageType {
        match self {
            Self::Bool => StorageType::Bool,
            Self::Int8 => StorageType::Int8,
            Self::UInt8 => StorageType::UInt8,
            Self::Int16 => StorageType::Int16,
            Self::UInt16 => StorageType::UInt16,
            Self::Int32 => StorageType::Int32,
            Self::UInt32 => StorageType::UInt32,
            Self::Int64 => StorageType::Int64,
            Self::UInt64 => StorageType::UInt64,
            Self::Float32 => StorageType::Float32,
            Self::Float64 => StorageType::Float64,
            Self::String => StorageType::String,
            Self::CategoricalString => StorageType::CategoricalString,
            Self::Vec2F32 => StorageType::Vec2F32,
            Self::Vec2F64 => StorageType::Vec2F64,
            Self::Vec3F32 => StorageType::Vec3F32,
            Self::Vec3F64 => StorageType::Vec3F64,
        }
    }
}

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
    List(ListElementType),
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
            name if name.starts_with("List[") && name.ends_with(']') => {
                let element = &name[5..name.len() - 1];
                Ok(Self::List(ListElementType::parse(element)?))
            }
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
            Self::List(ListElementType::Bool) => "List[Bool]",
            Self::List(ListElementType::Int8) => "List[Int8]",
            Self::List(ListElementType::UInt8) => "List[UInt8]",
            Self::List(ListElementType::Int16) => "List[Int16]",
            Self::List(ListElementType::UInt16) => "List[UInt16]",
            Self::List(ListElementType::Int32) => "List[Int32]",
            Self::List(ListElementType::UInt32) => "List[UInt32]",
            Self::List(ListElementType::Int64) => "List[Int64]",
            Self::List(ListElementType::UInt64) => "List[UInt64]",
            Self::List(ListElementType::Float32) => "List[Float32]",
            Self::List(ListElementType::Float64) => "List[Float64]",
            Self::List(ListElementType::String) => "List[String]",
            Self::List(ListElementType::CategoricalString) => "List[CategoricalString]",
            Self::List(ListElementType::Vec2F32) => "List[Vec2F32]",
            Self::List(ListElementType::Vec2F64) => "List[Vec2F64]",
            Self::List(ListElementType::Vec3F32) => "List[Vec3F32]",
            Self::List(ListElementType::Vec3F64) => "List[Vec3F64]",
        }
    }

    pub fn list_element(self) -> Option<ListElementType> {
        match self {
            Self::List(element) => Some(element),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ComponentId(u32);

impl ComponentId {
    pub const fn new(raw: u32) -> Self {
        Self(raw)
    }

    pub const fn index(self) -> usize {
        self.0 as usize
    }

    pub const fn raw(self) -> u32 {
        self.0
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct FieldId {
    component: ComponentId,
    field: u16,
}

impl FieldId {
    pub const fn new(component: ComponentId, field: u16) -> Self {
        Self { component, field }
    }

    pub const fn component(self) -> ComponentId {
        self.component
    }

    pub const fn index(self) -> usize {
        self.field as usize
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
    component_ids: HashMap<String, ComponentId>,
    schemas_by_id: Vec<ComponentSchema>,
    version: u64,
    fingerprint: u64,
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
        let id = ComponentId::new(self.schemas_by_id.len() as u32);
        let schema_hash = hash_schema(&schema);
        self.schemas.insert(name.clone(), schema.clone());
        self.component_ids.insert(name, id);
        self.schemas_by_id.push(schema);
        self.version = self.version.saturating_add(1);
        self.fingerprint ^= schema_hash.rotate_left((schema_hash & 63) as u32);
        Ok(())
    }

    pub fn get(&self, name: &str) -> Option<&ComponentSchema> {
        self.schemas.get(name)
    }

    pub fn contains(&self, name: &str) -> bool {
        self.schemas.contains_key(name)
    }

    pub fn component_id(&self, name: &str) -> Option<ComponentId> {
        self.component_ids.get(name).copied()
    }

    pub fn get_by_id(&self, id: ComponentId) -> Option<&ComponentSchema> {
        self.schemas_by_id.get(id.index())
    }

    pub fn field_id(&self, component: &str, field: &str) -> Option<FieldId> {
        let component_id = self.component_id(component)?;
        let schema = self.get_by_id(component_id)?;
        let field_index = schema
            .fields
            .iter()
            .position(|candidate| candidate.name == field)?;
        u16::try_from(field_index)
            .ok()
            .map(|field| FieldId::new(component_id, field))
    }

    pub fn field_schema(&self, id: FieldId) -> Option<&FieldSchema> {
        self.get_by_id(id.component())?.fields.get(id.index())
    }

    pub fn component_name(&self, id: ComponentId) -> Option<&str> {
        self.get_by_id(id).map(|schema| schema.name.as_str())
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

    pub const fn version(&self) -> u64 {
        self.version
    }

    pub const fn fingerprint(&self) -> u64 {
        self.fingerprint
    }
}

fn hash_schema(schema: &ComponentSchema) -> u64 {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    schema.name.hash(&mut hasher);
    for field in &schema.fields {
        field.name.hash(&mut hasher);
        field.storage_type.hash(&mut hasher);
    }
    hasher.finish()
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
        let first_field = registry.field_id("Health", "hp").unwrap();
        let first_version = registry.version();
        let first_fingerprint = registry.fingerprint();
        registry.register(schema).unwrap();
        assert_eq!(registry.component_id("Health"), Some(first_id));
        assert_eq!(registry.field_id("Health", "hp"), Some(first_field));
        assert_eq!(registry.version(), first_version);
        assert_eq!(registry.fingerprint(), first_fingerprint);
        assert_eq!(registry.len(), 1);
    }

    #[test]
    fn schema_fingerprint_is_incremental_and_registration_order_independent() {
        let health =
            ComponentSchema::new("Health", vec![FieldSchema::new("hp", StorageType::Int32)]);
        let position = ComponentSchema::new(
            "Position",
            vec![FieldSchema::new("x", StorageType::Float64)],
        );
        let mut first = SchemaRegistry::new();
        first.register(health.clone()).unwrap();
        first.register(position.clone()).unwrap();
        let mut second = SchemaRegistry::new();
        second.register(position).unwrap();
        second.register(health).unwrap();
        assert_eq!(first.version(), 2);
        assert_eq!(first.fingerprint(), second.fingerprint());
        assert_eq!(
            first.field_schema(first.field_id("Position", "x").unwrap()),
            Some(&FieldSchema::new("x", StorageType::Float64))
        );
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

    #[test]
    fn list_schema_preserves_declared_element_type() {
        let storage = StorageType::parse("List[UInt16]").unwrap();
        assert_eq!(storage, StorageType::List(ListElementType::UInt16));
        assert_eq!(storage.name(), "List[UInt16]");
        assert!(StorageType::parse("List[List[Int8]]").is_err());
    }
}
