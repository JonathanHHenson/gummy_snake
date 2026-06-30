use std::collections::HashMap;

use crate::error::{EcsError, Result};
use crate::schema::StorageType;

#[derive(Debug, Clone, PartialEq)]
pub enum EcsValue {
    Bool(bool),
    I64(i64),
    U64(u64),
    F64(f64),
    String(String),
    Vec2F32([f32; 2]),
    Vec2F64([f64; 2]),
    Vec3F32([f32; 3]),
    Vec3F64([f64; 3]),
    List(Vec<EcsValue>),
    Struct(HashMap<String, EcsValue>),
}

impl EcsValue {
    pub fn kind_name(&self) -> &'static str {
        match self {
            Self::Bool(_) => "Bool",
            Self::I64(_) => "I64",
            Self::U64(_) => "U64",
            Self::F64(_) => "F64",
            Self::String(_) => "String",
            Self::Vec2F32(_) => "Vec2F32",
            Self::Vec2F64(_) => "Vec2F64",
            Self::Vec3F32(_) => "Vec3F32",
            Self::Vec3F64(_) => "Vec3F64",
            Self::List(_) => "List",
            Self::Struct(_) => "Struct",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum Column {
    Bool(Vec<bool>),
    I64(Vec<i64>),
    U64(Vec<u64>),
    F64(Vec<f64>),
    String(Vec<String>),
    Vec2F32(Vec<[f32; 2]>),
    Vec2F64(Vec<[f64; 2]>),
    Vec3F32(Vec<[f32; 3]>),
    Vec3F64(Vec<[f64; 3]>),
    List(Vec<Vec<EcsValue>>),
}

impl Column {
    pub fn empty(storage_type: StorageType) -> Self {
        match storage_type {
            StorageType::Bool => Self::Bool(Vec::new()),
            StorageType::Int8 | StorageType::Int16 | StorageType::Int32 | StorageType::Int64 => {
                Self::I64(Vec::new())
            }
            StorageType::UInt8
            | StorageType::UInt16
            | StorageType::UInt32
            | StorageType::UInt64 => Self::U64(Vec::new()),
            StorageType::Float32 | StorageType::Float64 => Self::F64(Vec::new()),
            StorageType::String | StorageType::CategoricalString => Self::String(Vec::new()),
            StorageType::Vec2F32 => Self::Vec2F32(Vec::new()),
            StorageType::Vec2F64 => Self::Vec2F64(Vec::new()),
            StorageType::Vec3F32 => Self::Vec3F32(Vec::new()),
            StorageType::Vec3F64 => Self::Vec3F64(Vec::new()),
            StorageType::List => Self::List(Vec::new()),
        }
    }

    pub fn family_name(&self) -> &'static str {
        match self {
            Self::Bool(_) => "Bool",
            Self::I64(_) => "I64",
            Self::U64(_) => "U64",
            Self::F64(_) => "F64",
            Self::String(_) => "String",
            Self::Vec2F32(_) => "Vec2F32",
            Self::Vec2F64(_) => "Vec2F64",
            Self::Vec3F32(_) => "Vec3F32",
            Self::Vec3F64(_) => "Vec3F64",
            Self::List(_) => "List",
        }
    }

    pub fn len(&self) -> usize {
        match self {
            Self::Bool(values) => values.len(),
            Self::I64(values) => values.len(),
            Self::U64(values) => values.len(),
            Self::F64(values) => values.len(),
            Self::String(values) => values.len(),
            Self::Vec2F32(values) => values.len(),
            Self::Vec2F64(values) => values.len(),
            Self::Vec3F32(values) => values.len(),
            Self::Vec3F64(values) => values.len(),
            Self::List(values) => values.len(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn capacity(&self) -> usize {
        match self {
            Self::Bool(values) => values.capacity(),
            Self::I64(values) => values.capacity(),
            Self::U64(values) => values.capacity(),
            Self::F64(values) => values.capacity(),
            Self::String(values) => values.capacity(),
            Self::Vec2F32(values) => values.capacity(),
            Self::Vec2F64(values) => values.capacity(),
            Self::Vec3F32(values) => values.capacity(),
            Self::Vec3F64(values) => values.capacity(),
            Self::List(values) => values.capacity(),
        }
    }

    pub fn reserve(&mut self, additional: usize) {
        match self {
            Self::Bool(values) => values.reserve(additional),
            Self::I64(values) => values.reserve(additional),
            Self::U64(values) => values.reserve(additional),
            Self::F64(values) => values.reserve(additional),
            Self::String(values) => values.reserve(additional),
            Self::Vec2F32(values) => values.reserve(additional),
            Self::Vec2F64(values) => values.reserve(additional),
            Self::Vec3F32(values) => values.reserve(additional),
            Self::Vec3F64(values) => values.reserve(additional),
            Self::List(values) => values.reserve(additional),
        }
    }

    pub fn push_default(&mut self) {
        match self {
            Self::Bool(values) => values.push(false),
            Self::I64(values) => values.push(0),
            Self::U64(values) => values.push(0),
            Self::F64(values) => values.push(0.0),
            Self::String(values) => values.push(String::new()),
            Self::Vec2F32(values) => values.push([0.0, 0.0]),
            Self::Vec2F64(values) => values.push([0.0, 0.0]),
            Self::Vec3F32(values) => values.push([0.0, 0.0, 0.0]),
            Self::Vec3F64(values) => values.push([0.0, 0.0, 0.0]),
            Self::List(values) => values.push(Vec::new()),
        }
    }

    pub fn default_value(&self) -> EcsValue {
        match self {
            Self::Bool(_) => EcsValue::Bool(false),
            Self::I64(_) => EcsValue::I64(0),
            Self::U64(_) => EcsValue::U64(0),
            Self::F64(_) => EcsValue::F64(0.0),
            Self::String(_) => EcsValue::String(String::new()),
            Self::Vec2F32(_) => EcsValue::Vec2F32([0.0, 0.0]),
            Self::Vec2F64(_) => EcsValue::Vec2F64([0.0, 0.0]),
            Self::Vec3F32(_) => EcsValue::Vec3F32([0.0, 0.0, 0.0]),
            Self::Vec3F64(_) => EcsValue::Vec3F64([0.0, 0.0, 0.0]),
            Self::List(_) => EcsValue::List(Vec::new()),
        }
    }

    pub fn push_value(&mut self, value: EcsValue) -> Result<()> {
        match (self, value) {
            (Self::Bool(values), EcsValue::Bool(value)) => values.push(value),
            (Self::I64(values), EcsValue::I64(value)) => values.push(value),
            (Self::U64(values), EcsValue::U64(value)) => values.push(value),
            (Self::F64(values), EcsValue::F64(value)) => values.push(value),
            (Self::String(values), EcsValue::String(value)) => values.push(value),
            (Self::Vec2F32(values), EcsValue::Vec2F32(value)) => values.push(value),
            (Self::Vec2F64(values), EcsValue::Vec2F64(value)) => values.push(value),
            (Self::Vec3F32(values), EcsValue::Vec3F32(value)) => values.push(value),
            (Self::Vec3F64(values), EcsValue::Vec3F64(value)) => values.push(value),
            (Self::List(values), EcsValue::List(value)) => values.push(value),
            (column, value) => {
                return Err(EcsError::ColumnTypeMismatch {
                    expected: column.family_name(),
                    got: value.kind_name(),
                })
            }
        }
        Ok(())
    }

    pub fn get(&self, row: usize) -> Result<EcsValue> {
        let value = match self {
            Self::Bool(values) => EcsValue::Bool(*values.get(row).ok_or(EcsError::RowOutOfBounds)?),
            Self::I64(values) => EcsValue::I64(*values.get(row).ok_or(EcsError::RowOutOfBounds)?),
            Self::U64(values) => EcsValue::U64(*values.get(row).ok_or(EcsError::RowOutOfBounds)?),
            Self::F64(values) => EcsValue::F64(*values.get(row).ok_or(EcsError::RowOutOfBounds)?),
            Self::String(values) => {
                EcsValue::String(values.get(row).ok_or(EcsError::RowOutOfBounds)?.clone())
            }
            Self::Vec2F32(values) => {
                EcsValue::Vec2F32(*values.get(row).ok_or(EcsError::RowOutOfBounds)?)
            }
            Self::Vec2F64(values) => {
                EcsValue::Vec2F64(*values.get(row).ok_or(EcsError::RowOutOfBounds)?)
            }
            Self::Vec3F32(values) => {
                EcsValue::Vec3F32(*values.get(row).ok_or(EcsError::RowOutOfBounds)?)
            }
            Self::Vec3F64(values) => {
                EcsValue::Vec3F64(*values.get(row).ok_or(EcsError::RowOutOfBounds)?)
            }
            Self::List(values) => {
                EcsValue::List(values.get(row).ok_or(EcsError::RowOutOfBounds)?.clone())
            }
        };
        Ok(value)
    }

    pub fn set(&mut self, row: usize, value: EcsValue) -> Result<()> {
        if row >= self.len() {
            return Err(EcsError::RowOutOfBounds);
        }
        match (self, value) {
            (Self::Bool(values), EcsValue::Bool(value)) => values[row] = value,
            (Self::I64(values), EcsValue::I64(value)) => values[row] = value,
            (Self::U64(values), EcsValue::U64(value)) => values[row] = value,
            (Self::F64(values), EcsValue::F64(value)) => values[row] = value,
            (Self::String(values), EcsValue::String(value)) => values[row] = value,
            (Self::Vec2F32(values), EcsValue::Vec2F32(value)) => values[row] = value,
            (Self::Vec2F64(values), EcsValue::Vec2F64(value)) => values[row] = value,
            (Self::Vec3F32(values), EcsValue::Vec3F32(value)) => values[row] = value,
            (Self::Vec3F64(values), EcsValue::Vec3F64(value)) => values[row] = value,
            (Self::List(values), EcsValue::List(value)) => values[row] = value,
            (column, value) => {
                return Err(EcsError::ColumnTypeMismatch {
                    expected: column.family_name(),
                    got: value.kind_name(),
                })
            }
        }
        Ok(())
    }

    pub fn swap_remove(&mut self, row: usize) -> Result<EcsValue> {
        if row >= self.len() {
            return Err(EcsError::RowOutOfBounds);
        }
        let value = match self {
            Self::Bool(values) => EcsValue::Bool(values.swap_remove(row)),
            Self::I64(values) => EcsValue::I64(values.swap_remove(row)),
            Self::U64(values) => EcsValue::U64(values.swap_remove(row)),
            Self::F64(values) => EcsValue::F64(values.swap_remove(row)),
            Self::String(values) => EcsValue::String(values.swap_remove(row)),
            Self::Vec2F32(values) => EcsValue::Vec2F32(values.swap_remove(row)),
            Self::Vec2F64(values) => EcsValue::Vec2F64(values.swap_remove(row)),
            Self::Vec3F32(values) => EcsValue::Vec3F32(values.swap_remove(row)),
            Self::Vec3F64(values) => EcsValue::Vec3F64(values.swap_remove(row)),
            Self::List(values) => EcsValue::List(values.swap_remove(row)),
        };
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn columns_group_scalar_storage_families() {
        let mut column = Column::empty(StorageType::UInt16);
        column.reserve(8);
        assert!(column.capacity() >= 8);
        column.push_default();
        assert_eq!(column.len(), 1);
        assert!(matches!(column, Column::U64(_)));
    }

    #[test]
    fn vector_and_list_columns_store_typed_values() {
        let mut vector = Column::empty(StorageType::Vec3F32);
        vector
            .push_value(EcsValue::Vec3F32([1.0, 2.0, 3.0]))
            .unwrap();
        assert_eq!(vector.get(0).unwrap(), EcsValue::Vec3F32([1.0, 2.0, 3.0]));

        let mut list = Column::empty(StorageType::List);
        list.push_value(EcsValue::List(vec![EcsValue::F64(1.0), EcsValue::F64(2.0)]))
            .unwrap();
        assert_eq!(list.len(), 1);
    }
}
