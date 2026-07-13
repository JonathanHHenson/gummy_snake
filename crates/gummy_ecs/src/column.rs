use std::collections::HashMap;
use std::mem::size_of;

use crate::error::{EcsError, Result};
use crate::schema::{ListElementType, StorageType};

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

fn type_mismatch(expected: &'static str, value: EcsValue) -> EcsError {
    EcsError::ColumnTypeMismatch {
        expected,
        got: value.kind_name(),
    }
}

fn integer_value(value: EcsValue, expected: &'static str) -> Result<i128> {
    match value {
        EcsValue::I64(value) => Ok(i128::from(value)),
        EcsValue::U64(value) => Ok(i128::from(value)),
        EcsValue::F64(value) if value.is_finite() && value.fract() == 0.0 => {
            let integer = value as i128;
            if integer as f64 == value {
                Ok(integer)
            } else {
                Err(EcsError::ValueOutOfRange {
                    storage_type: expected,
                    value: value.to_string(),
                })
            }
        }
        other => Err(type_mismatch(expected, other)),
    }
}

fn checked_signed(
    value: EcsValue,
    storage_type: StorageType,
    min: i128,
    max: i128,
) -> Result<EcsValue> {
    let value = integer_value(value, storage_type.name())?;
    if !(min..=max).contains(&value) {
        return Err(EcsError::ValueOutOfRange {
            storage_type: storage_type.name(),
            value: value.to_string(),
        });
    }
    Ok(EcsValue::I64(value as i64))
}

fn checked_unsigned(value: EcsValue, storage_type: StorageType, max: i128) -> Result<EcsValue> {
    let value = integer_value(value, storage_type.name())?;
    if !(0..=max).contains(&value) {
        return Err(EcsError::ValueOutOfRange {
            storage_type: storage_type.name(),
            value: value.to_string(),
        });
    }
    Ok(EcsValue::U64(value as u64))
}

fn float_value(value: EcsValue, storage_type: StorageType) -> Result<f64> {
    let value = match value {
        EcsValue::F64(value) => value,
        EcsValue::I64(value) => value as f64,
        EcsValue::U64(value) => value as f64,
        other => return Err(type_mismatch(storage_type.name(), other)),
    };
    if !value.is_finite() {
        return Err(EcsError::NonFiniteFloat {
            storage_type: storage_type.name(),
        });
    }
    Ok(value)
}

fn checked_f32(value: f64, storage_type: StorageType) -> Result<f32> {
    if !value.is_finite() {
        return Err(EcsError::NonFiniteFloat {
            storage_type: storage_type.name(),
        });
    }
    let narrowed = value as f32;
    if !narrowed.is_finite() {
        return Err(EcsError::ValueOutOfRange {
            storage_type: storage_type.name(),
            value: value.to_string(),
        });
    }
    Ok(narrowed)
}

fn finite_f64_vector<const N: usize>(
    values: [f64; N],
    storage_type: StorageType,
) -> Result<[f64; N]> {
    if values.iter().any(|value| !value.is_finite()) {
        return Err(EcsError::NonFiniteFloat {
            storage_type: storage_type.name(),
        });
    }
    Ok(values)
}

fn f32_vector<const N: usize>(values: [f64; N], storage_type: StorageType) -> Result<[f32; N]> {
    let mut narrowed = [0.0_f32; N];
    for (index, value) in values.into_iter().enumerate() {
        narrowed[index] = checked_f32(value, storage_type)?;
    }
    Ok(narrowed)
}

/// Apply the canonical ECS write policy for a declared storage type.
///
/// Integer conversions are exact and checked; overflow is an error. Float32 values
/// are rounded once with Rust/IEEE-754 narrowing and then widened only for the public
/// `EcsValue` transport. Non-finite floats are rejected. Lists recursively apply the
/// same policy to every declared element.
pub fn coerce_value_for_storage(storage_type: StorageType, value: EcsValue) -> Result<EcsValue> {
    match storage_type {
        StorageType::Bool => match value {
            EcsValue::Bool(value) => Ok(EcsValue::Bool(value)),
            other => Err(type_mismatch("Bool", other)),
        },
        StorageType::Int8 => checked_signed(value, storage_type, i8::MIN.into(), i8::MAX.into()),
        StorageType::Int16 => checked_signed(value, storage_type, i16::MIN.into(), i16::MAX.into()),
        StorageType::Int32 => checked_signed(value, storage_type, i32::MIN.into(), i32::MAX.into()),
        StorageType::Int64 => checked_signed(value, storage_type, i64::MIN.into(), i64::MAX.into()),
        StorageType::UInt8 => checked_unsigned(value, storage_type, u8::MAX.into()),
        StorageType::UInt16 => checked_unsigned(value, storage_type, u16::MAX.into()),
        StorageType::UInt32 => checked_unsigned(value, storage_type, u32::MAX.into()),
        StorageType::UInt64 => checked_unsigned(value, storage_type, u64::MAX.into()),
        StorageType::Float32 => {
            let value = float_value(value, storage_type)?;
            Ok(EcsValue::F64(f64::from(checked_f32(value, storage_type)?)))
        }
        StorageType::Float64 => Ok(EcsValue::F64(float_value(value, storage_type)?)),
        StorageType::String | StorageType::CategoricalString => match value {
            EcsValue::String(value) => Ok(EcsValue::String(value)),
            other => Err(type_mismatch(storage_type.name(), other)),
        },
        StorageType::Vec2F32 => {
            let values = match value {
                EcsValue::Vec2F32(values) => {
                    if values.iter().any(|value| !value.is_finite()) {
                        return Err(EcsError::NonFiniteFloat {
                            storage_type: storage_type.name(),
                        });
                    }
                    return Ok(EcsValue::Vec2F32(values));
                }
                EcsValue::Vec2F64(values) => values,
                other => return Err(type_mismatch("Vec2F32", other)),
            };
            Ok(EcsValue::Vec2F32(f32_vector(values, storage_type)?))
        }
        StorageType::Vec2F64 => {
            let values = match value {
                EcsValue::Vec2F32(values) => values.map(f64::from),
                EcsValue::Vec2F64(values) => values,
                other => return Err(type_mismatch("Vec2F64", other)),
            };
            Ok(EcsValue::Vec2F64(finite_f64_vector(values, storage_type)?))
        }
        StorageType::Vec3F32 => {
            let values = match value {
                EcsValue::Vec3F32(values) => {
                    if values.iter().any(|value| !value.is_finite()) {
                        return Err(EcsError::NonFiniteFloat {
                            storage_type: storage_type.name(),
                        });
                    }
                    return Ok(EcsValue::Vec3F32(values));
                }
                EcsValue::Vec3F64(values) => values,
                other => return Err(type_mismatch("Vec3F32", other)),
            };
            Ok(EcsValue::Vec3F32(f32_vector(values, storage_type)?))
        }
        StorageType::Vec3F64 => {
            let values = match value {
                EcsValue::Vec3F32(values) => values.map(f64::from),
                EcsValue::Vec3F64(values) => values,
                other => return Err(type_mismatch("Vec3F64", other)),
            };
            Ok(EcsValue::Vec3F64(finite_f64_vector(values, storage_type)?))
        }
        StorageType::List(element_type) => match value {
            EcsValue::List(values) => values
                .into_iter()
                .map(|value| coerce_value_for_storage(element_type.storage_type(), value))
                .collect::<Result<Vec<_>>>()
                .map(EcsValue::List),
            other => Err(type_mismatch(storage_type.name(), other)),
        },
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct PackedList<T> {
    offsets: Vec<usize>,
    values: Vec<T>,
}

impl<T> Default for PackedList<T> {
    fn default() -> Self {
        Self {
            offsets: vec![0],
            values: Vec::new(),
        }
    }
}

impl<T: Clone> PackedList<T> {
    fn len(&self) -> usize {
        self.offsets.len() - 1
    }

    fn row_capacity(&self) -> usize {
        self.offsets.capacity().saturating_sub(1)
    }

    fn reserve_rows(&mut self, additional: usize) {
        self.offsets.reserve(additional);
    }

    fn push(&mut self, values: Vec<T>) {
        self.values.extend(values);
        self.offsets.push(self.values.len());
    }

    fn get(&self, row: usize) -> Result<&[T]> {
        let start = *self.offsets.get(row).ok_or(EcsError::RowOutOfBounds)?;
        let end = *self.offsets.get(row + 1).ok_or(EcsError::RowOutOfBounds)?;
        Ok(&self.values[start..end])
    }

    fn set(&mut self, row: usize, values: Vec<T>) -> Result<()> {
        let start = *self.offsets.get(row).ok_or(EcsError::RowOutOfBounds)?;
        let end = *self.offsets.get(row + 1).ok_or(EcsError::RowOutOfBounds)?;
        let old_len = end - start;
        let new_len = values.len();
        self.values.splice(start..end, values);
        if new_len >= old_len {
            let delta = new_len - old_len;
            for offset in &mut self.offsets[row + 1..] {
                *offset += delta;
            }
        } else {
            let delta = old_len - new_len;
            for offset in &mut self.offsets[row + 1..] {
                *offset -= delta;
            }
        }
        Ok(())
    }

    fn swap_remove(&mut self, row: usize) -> Result<Vec<T>> {
        let len = self.len();
        if row >= len {
            return Err(EcsError::RowOutOfBounds);
        }
        let removed = self.get(row)?.to_vec();
        if row + 1 == len {
            let start = self.offsets[row];
            self.values.truncate(start);
            self.offsets.pop();
            return Ok(removed);
        }
        let last = self.get(len - 1)?.to_vec();
        self.set(row, last)?;
        let last_start = self.offsets[len - 1];
        self.values.truncate(last_start);
        self.offsets.pop();
        Ok(removed)
    }

    fn allocated_bytes(&self) -> usize {
        self.offsets.capacity() * size_of::<usize>() + self.values.capacity() * size_of::<T>()
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
struct CategoryInterner {
    ids: HashMap<String, u32>,
    values: Vec<Option<String>>,
    references: Vec<usize>,
    free_ids: Vec<u32>,
}

impl CategoryInterner {
    fn intern(&mut self, value: String) -> Result<u32> {
        if let Some(id) = self.ids.get(&value).copied() {
            self.references[id as usize] += 1;
            return Ok(id);
        }
        let id = if let Some(id) = self.free_ids.pop() {
            self.values[id as usize] = Some(value.clone());
            self.references[id as usize] = 1;
            id
        } else {
            let id = u32::try_from(self.values.len()).map_err(|_| EcsError::ValueOutOfRange {
                storage_type: "CategoricalString dictionary",
                value: self.values.len().to_string(),
            })?;
            self.values.push(Some(value.clone()));
            self.references.push(1);
            id
        };
        self.ids.insert(value, id);
        Ok(id)
    }

    fn resolve(&self, id: u32) -> &str {
        self.values[id as usize]
            .as_deref()
            .expect("live categorical code must resolve")
    }

    fn release(&mut self, id: u32) {
        let references = &mut self.references[id as usize];
        *references -= 1;
        if *references == 0 {
            if let Some(value) = self.values[id as usize].take() {
                self.ids.remove(&value);
            }
            self.free_ids.push(id);
        }
    }

    fn allocated_bytes(&self) -> usize {
        let strings = self
            .values
            .iter()
            .filter_map(Option::as_ref)
            .map(|value| value.capacity())
            .sum::<usize>();
        self.values.capacity() * size_of::<Option<String>>()
            + self.references.capacity() * size_of::<usize>()
            + self.free_ids.capacity() * size_of::<u32>()
            + strings
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct CategoricalColumn {
    codes: Vec<u32>,
    interner: CategoryInterner,
}

impl CategoricalColumn {
    fn push(&mut self, value: String) -> Result<()> {
        let code = self.interner.intern(value)?;
        self.codes.push(code);
        Ok(())
    }

    fn get(&self, row: usize) -> Result<String> {
        let code = *self.codes.get(row).ok_or(EcsError::RowOutOfBounds)?;
        Ok(self.interner.resolve(code).to_string())
    }

    fn set(&mut self, row: usize, value: String) -> Result<()> {
        let old = *self.codes.get(row).ok_or(EcsError::RowOutOfBounds)?;
        let new = self.interner.intern(value)?;
        self.codes[row] = new;
        self.interner.release(old);
        Ok(())
    }

    fn swap_remove(&mut self, row: usize) -> Result<String> {
        if row >= self.codes.len() {
            return Err(EcsError::RowOutOfBounds);
        }
        let code = self.codes.swap_remove(row);
        let value = self.interner.resolve(code).to_string();
        self.interner.release(code);
        Ok(value)
    }

    fn allocated_bytes(&self) -> usize {
        self.codes.capacity() * size_of::<u32>() + self.interner.allocated_bytes()
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct CategoricalListColumn {
    rows: PackedList<u32>,
    interner: CategoryInterner,
}

impl CategoricalListColumn {
    fn intern_values(&mut self, values: Vec<String>) -> Result<Vec<u32>> {
        let mut codes = Vec::with_capacity(values.len());
        for value in values {
            match self.interner.intern(value) {
                Ok(code) => codes.push(code),
                Err(error) => {
                    for code in codes {
                        self.interner.release(code);
                    }
                    return Err(error);
                }
            }
        }
        Ok(codes)
    }

    fn push(&mut self, values: Vec<String>) -> Result<()> {
        let codes = self.intern_values(values)?;
        self.rows.push(codes);
        Ok(())
    }

    fn get(&self, row: usize) -> Result<Vec<String>> {
        Ok(self
            .rows
            .get(row)?
            .iter()
            .map(|code| self.interner.resolve(*code).to_string())
            .collect())
    }

    fn set(&mut self, row: usize, values: Vec<String>) -> Result<()> {
        let old = self.rows.get(row)?.to_vec();
        let codes = self.intern_values(values)?;
        self.rows.set(row, codes)?;
        for code in old {
            self.interner.release(code);
        }
        Ok(())
    }

    fn swap_remove(&mut self, row: usize) -> Result<Vec<String>> {
        let removed = self.rows.swap_remove(row)?;
        let values = removed
            .iter()
            .map(|code| self.interner.resolve(*code).to_string())
            .collect();
        for code in removed {
            self.interner.release(code);
        }
        Ok(values)
    }

    fn allocated_bytes(&self) -> usize {
        self.rows.allocated_bytes() + self.interner.allocated_bytes()
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum TypedListColumn {
    Bool(PackedList<bool>),
    Int8(PackedList<i8>),
    UInt8(PackedList<u8>),
    Int16(PackedList<i16>),
    UInt16(PackedList<u16>),
    Int32(PackedList<i32>),
    UInt32(PackedList<u32>),
    Int64(PackedList<i64>),
    UInt64(PackedList<u64>),
    Float32(PackedList<f32>),
    Float64(PackedList<f64>),
    String(PackedList<String>),
    CategoricalString(CategoricalListColumn),
    Vec2F32(PackedList<[f32; 2]>),
    Vec2F64(PackedList<[f64; 2]>),
    Vec3F32(PackedList<[f32; 3]>),
    Vec3F64(PackedList<[f64; 3]>),
}

macro_rules! list_match {
    ($self:expr, $method:ident $(, $arg:expr)*) => {
        match $self {
            TypedListColumn::Bool(values) => values.$method($($arg),*),
            TypedListColumn::Int8(values) => values.$method($($arg),*),
            TypedListColumn::UInt8(values) => values.$method($($arg),*),
            TypedListColumn::Int16(values) => values.$method($($arg),*),
            TypedListColumn::UInt16(values) => values.$method($($arg),*),
            TypedListColumn::Int32(values) => values.$method($($arg),*),
            TypedListColumn::UInt32(values) => values.$method($($arg),*),
            TypedListColumn::Int64(values) => values.$method($($arg),*),
            TypedListColumn::UInt64(values) => values.$method($($arg),*),
            TypedListColumn::Float32(values) => values.$method($($arg),*),
            TypedListColumn::Float64(values) => values.$method($($arg),*),
            TypedListColumn::String(values) => values.$method($($arg),*),
            TypedListColumn::CategoricalString(values) => values.rows.$method($($arg),*),
            TypedListColumn::Vec2F32(values) => values.$method($($arg),*),
            TypedListColumn::Vec2F64(values) => values.$method($($arg),*),
            TypedListColumn::Vec3F32(values) => values.$method($($arg),*),
            TypedListColumn::Vec3F64(values) => values.$method($($arg),*),
        }
    };
}

impl TypedListColumn {
    fn new(element_type: ListElementType) -> Self {
        match element_type {
            ListElementType::Bool => Self::Bool(PackedList::default()),
            ListElementType::Int8 => Self::Int8(PackedList::default()),
            ListElementType::UInt8 => Self::UInt8(PackedList::default()),
            ListElementType::Int16 => Self::Int16(PackedList::default()),
            ListElementType::UInt16 => Self::UInt16(PackedList::default()),
            ListElementType::Int32 => Self::Int32(PackedList::default()),
            ListElementType::UInt32 => Self::UInt32(PackedList::default()),
            ListElementType::Int64 => Self::Int64(PackedList::default()),
            ListElementType::UInt64 => Self::UInt64(PackedList::default()),
            ListElementType::Float32 => Self::Float32(PackedList::default()),
            ListElementType::Float64 => Self::Float64(PackedList::default()),
            ListElementType::String => Self::String(PackedList::default()),
            ListElementType::CategoricalString => Self::CategoricalString(Default::default()),
            ListElementType::Vec2F32 => Self::Vec2F32(PackedList::default()),
            ListElementType::Vec2F64 => Self::Vec2F64(PackedList::default()),
            ListElementType::Vec3F32 => Self::Vec3F32(PackedList::default()),
            ListElementType::Vec3F64 => Self::Vec3F64(PackedList::default()),
        }
    }

    fn element_type(&self) -> ListElementType {
        match self {
            Self::Bool(_) => ListElementType::Bool,
            Self::Int8(_) => ListElementType::Int8,
            Self::UInt8(_) => ListElementType::UInt8,
            Self::Int16(_) => ListElementType::Int16,
            Self::UInt16(_) => ListElementType::UInt16,
            Self::Int32(_) => ListElementType::Int32,
            Self::UInt32(_) => ListElementType::UInt32,
            Self::Int64(_) => ListElementType::Int64,
            Self::UInt64(_) => ListElementType::UInt64,
            Self::Float32(_) => ListElementType::Float32,
            Self::Float64(_) => ListElementType::Float64,
            Self::String(_) => ListElementType::String,
            Self::CategoricalString(_) => ListElementType::CategoricalString,
            Self::Vec2F32(_) => ListElementType::Vec2F32,
            Self::Vec2F64(_) => ListElementType::Vec2F64,
            Self::Vec3F32(_) => ListElementType::Vec3F32,
            Self::Vec3F64(_) => ListElementType::Vec3F64,
        }
    }

    fn len(&self) -> usize {
        list_match!(self, len)
    }

    fn capacity(&self) -> usize {
        list_match!(self, row_capacity)
    }

    fn reserve(&mut self, additional: usize) {
        list_match!(self, reserve_rows, additional)
    }

    fn push(&mut self, values: Vec<EcsValue>) -> Result<()> {
        macro_rules! push_values {
            ($rows:expr, $variant:ident, $ty:ty, $expected:literal) => {{
                let values = values
                    .into_iter()
                    .map(|value| match value {
                        EcsValue::$variant(value) => Ok(value as $ty),
                        other => Err(type_mismatch($expected, other)),
                    })
                    .collect::<Result<Vec<$ty>>>()?;
                $rows.push(values);
                Ok(())
            }};
        }
        match self {
            Self::Bool(rows) => {
                let values = values
                    .into_iter()
                    .map(|value| match value {
                        EcsValue::Bool(value) => Ok(value),
                        other => Err(type_mismatch("Bool", other)),
                    })
                    .collect::<Result<Vec<_>>>()?;
                rows.push(values);
                Ok(())
            }
            Self::Int8(rows) => push_values!(rows, I64, i8, "Int8"),
            Self::UInt8(rows) => push_values!(rows, U64, u8, "UInt8"),
            Self::Int16(rows) => push_values!(rows, I64, i16, "Int16"),
            Self::UInt16(rows) => push_values!(rows, U64, u16, "UInt16"),
            Self::Int32(rows) => push_values!(rows, I64, i32, "Int32"),
            Self::UInt32(rows) => push_values!(rows, U64, u32, "UInt32"),
            Self::Int64(rows) => push_values!(rows, I64, i64, "Int64"),
            Self::UInt64(rows) => push_values!(rows, U64, u64, "UInt64"),
            Self::Float32(rows) => push_values!(rows, F64, f32, "Float32"),
            Self::Float64(rows) => push_values!(rows, F64, f64, "Float64"),
            Self::String(rows) => {
                let values = values
                    .into_iter()
                    .map(|value| match value {
                        EcsValue::String(value) => Ok(value),
                        other => Err(type_mismatch("String", other)),
                    })
                    .collect::<Result<Vec<_>>>()?;
                rows.push(values);
                Ok(())
            }
            Self::CategoricalString(rows) => {
                let values = values
                    .into_iter()
                    .map(|value| match value {
                        EcsValue::String(value) => Ok(value),
                        other => Err(type_mismatch("CategoricalString", other)),
                    })
                    .collect::<Result<Vec<_>>>()?;
                rows.push(values)
            }
            Self::Vec2F32(rows) => push_values!(rows, Vec2F32, [f32; 2], "Vec2F32"),
            Self::Vec2F64(rows) => push_values!(rows, Vec2F64, [f64; 2], "Vec2F64"),
            Self::Vec3F32(rows) => push_values!(rows, Vec3F32, [f32; 3], "Vec3F32"),
            Self::Vec3F64(rows) => push_values!(rows, Vec3F64, [f64; 3], "Vec3F64"),
        }
    }

    fn get(&self, row: usize) -> Result<Vec<EcsValue>> {
        macro_rules! get_values {
            ($rows:expr, $variant:ident, $convert:expr) => {
                Ok($rows
                    .get(row)?
                    .iter()
                    .cloned()
                    .map(|value| EcsValue::$variant($convert(value)))
                    .collect())
            };
        }
        match self {
            Self::Bool(rows) => get_values!(rows, Bool, |value| value),
            Self::Int8(rows) => get_values!(rows, I64, i64::from),
            Self::UInt8(rows) => get_values!(rows, U64, u64::from),
            Self::Int16(rows) => get_values!(rows, I64, i64::from),
            Self::UInt16(rows) => get_values!(rows, U64, u64::from),
            Self::Int32(rows) => get_values!(rows, I64, i64::from),
            Self::UInt32(rows) => get_values!(rows, U64, u64::from),
            Self::Int64(rows) => get_values!(rows, I64, |value| value),
            Self::UInt64(rows) => get_values!(rows, U64, |value| value),
            Self::Float32(rows) => get_values!(rows, F64, f64::from),
            Self::Float64(rows) => get_values!(rows, F64, |value| value),
            Self::String(rows) => get_values!(rows, String, |value| value),
            Self::CategoricalString(rows) => {
                Ok(rows.get(row)?.into_iter().map(EcsValue::String).collect())
            }
            Self::Vec2F32(rows) => get_values!(rows, Vec2F32, |value| value),
            Self::Vec2F64(rows) => get_values!(rows, Vec2F64, |value| value),
            Self::Vec3F32(rows) => get_values!(rows, Vec3F32, |value| value),
            Self::Vec3F64(rows) => get_values!(rows, Vec3F64, |value| value),
        }
    }

    fn set(&mut self, row: usize, values: Vec<EcsValue>) -> Result<()> {
        if row >= self.len() {
            return Err(EcsError::RowOutOfBounds);
        }
        let mut replacement = Self::new(self.element_type());
        replacement.push(values)?;
        macro_rules! replace {
            ($target:expr, $source:expr) => {
                $target.set(row, $source.get(0)?.to_vec())
            };
        }
        match (self, replacement) {
            (Self::Bool(target), Self::Bool(source)) => replace!(target, source),
            (Self::Int8(target), Self::Int8(source)) => replace!(target, source),
            (Self::UInt8(target), Self::UInt8(source)) => replace!(target, source),
            (Self::Int16(target), Self::Int16(source)) => replace!(target, source),
            (Self::UInt16(target), Self::UInt16(source)) => replace!(target, source),
            (Self::Int32(target), Self::Int32(source)) => replace!(target, source),
            (Self::UInt32(target), Self::UInt32(source)) => replace!(target, source),
            (Self::Int64(target), Self::Int64(source)) => replace!(target, source),
            (Self::UInt64(target), Self::UInt64(source)) => replace!(target, source),
            (Self::Float32(target), Self::Float32(source)) => replace!(target, source),
            (Self::Float64(target), Self::Float64(source)) => replace!(target, source),
            (Self::String(target), Self::String(source)) => replace!(target, source),
            (Self::CategoricalString(target), Self::CategoricalString(source)) => {
                target.set(row, source.get(0)?)
            }
            (Self::Vec2F32(target), Self::Vec2F32(source)) => replace!(target, source),
            (Self::Vec2F64(target), Self::Vec2F64(source)) => replace!(target, source),
            (Self::Vec3F32(target), Self::Vec3F32(source)) => replace!(target, source),
            (Self::Vec3F64(target), Self::Vec3F64(source)) => replace!(target, source),
            _ => unreachable!("replacement list has the same element type"),
        }
    }

    fn swap_remove(&mut self, row: usize) -> Result<Vec<EcsValue>> {
        let value = self.get(row)?;
        match self {
            Self::Bool(rows) => drop(rows.swap_remove(row)?),
            Self::Int8(rows) => drop(rows.swap_remove(row)?),
            Self::UInt8(rows) => drop(rows.swap_remove(row)?),
            Self::Int16(rows) => drop(rows.swap_remove(row)?),
            Self::UInt16(rows) => drop(rows.swap_remove(row)?),
            Self::Int32(rows) => drop(rows.swap_remove(row)?),
            Self::UInt32(rows) => drop(rows.swap_remove(row)?),
            Self::Int64(rows) => drop(rows.swap_remove(row)?),
            Self::UInt64(rows) => drop(rows.swap_remove(row)?),
            Self::Float32(rows) => drop(rows.swap_remove(row)?),
            Self::Float64(rows) => drop(rows.swap_remove(row)?),
            Self::String(rows) => drop(rows.swap_remove(row)?),
            Self::CategoricalString(rows) => drop(rows.swap_remove(row)?),
            Self::Vec2F32(rows) => drop(rows.swap_remove(row)?),
            Self::Vec2F64(rows) => drop(rows.swap_remove(row)?),
            Self::Vec3F32(rows) => drop(rows.swap_remove(row)?),
            Self::Vec3F64(rows) => drop(rows.swap_remove(row)?),
        }
        Ok(value)
    }

    fn allocated_bytes(&self) -> usize {
        match self {
            Self::Bool(values) => values.allocated_bytes(),
            Self::Int8(values) => values.allocated_bytes(),
            Self::UInt8(values) => values.allocated_bytes(),
            Self::Int16(values) => values.allocated_bytes(),
            Self::UInt16(values) => values.allocated_bytes(),
            Self::Int32(values) => values.allocated_bytes(),
            Self::UInt32(values) => values.allocated_bytes(),
            Self::Int64(values) => values.allocated_bytes(),
            Self::UInt64(values) => values.allocated_bytes(),
            Self::Float32(values) => values.allocated_bytes(),
            Self::Float64(values) => values.allocated_bytes(),
            Self::String(values) => values.allocated_bytes(),
            Self::CategoricalString(values) => values.allocated_bytes(),
            Self::Vec2F32(values) => values.allocated_bytes(),
            Self::Vec2F64(values) => values.allocated_bytes(),
            Self::Vec3F32(values) => values.allocated_bytes(),
            Self::Vec3F64(values) => values.allocated_bytes(),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum Column {
    Bool(Vec<bool>),
    Int8(Vec<i8>),
    UInt8(Vec<u8>),
    Int16(Vec<i16>),
    UInt16(Vec<u16>),
    Int32(Vec<i32>),
    UInt32(Vec<u32>),
    Int64(Vec<i64>),
    UInt64(Vec<u64>),
    Float32(Vec<f32>),
    Float64(Vec<f64>),
    String(Vec<String>),
    CategoricalString(CategoricalColumn),
    Vec2F32(Vec<[f32; 2]>),
    Vec2F64(Vec<[f64; 2]>),
    Vec3F32(Vec<[f32; 3]>),
    Vec3F64(Vec<[f64; 3]>),
    List(TypedListColumn),
}

macro_rules! column_values_match {
    ($self:expr, $method:ident $(, $arg:expr)*) => {
        match $self {
            Column::Bool(values) => values.$method($($arg),*),
            Column::Int8(values) => values.$method($($arg),*),
            Column::UInt8(values) => values.$method($($arg),*),
            Column::Int16(values) => values.$method($($arg),*),
            Column::UInt16(values) => values.$method($($arg),*),
            Column::Int32(values) => values.$method($($arg),*),
            Column::UInt32(values) => values.$method($($arg),*),
            Column::Int64(values) => values.$method($($arg),*),
            Column::UInt64(values) => values.$method($($arg),*),
            Column::Float32(values) => values.$method($($arg),*),
            Column::Float64(values) => values.$method($($arg),*),
            Column::String(values) => values.$method($($arg),*),
            Column::CategoricalString(values) => values.codes.$method($($arg),*),
            Column::Vec2F32(values) => values.$method($($arg),*),
            Column::Vec2F64(values) => values.$method($($arg),*),
            Column::Vec3F32(values) => values.$method($($arg),*),
            Column::Vec3F64(values) => values.$method($($arg),*),
            Column::List(values) => values.$method($($arg),*),
        }
    };
}

impl Column {
    pub fn empty(storage_type: StorageType) -> Self {
        match storage_type {
            StorageType::Bool => Self::Bool(Vec::new()),
            StorageType::Int8 => Self::Int8(Vec::new()),
            StorageType::UInt8 => Self::UInt8(Vec::new()),
            StorageType::Int16 => Self::Int16(Vec::new()),
            StorageType::UInt16 => Self::UInt16(Vec::new()),
            StorageType::Int32 => Self::Int32(Vec::new()),
            StorageType::UInt32 => Self::UInt32(Vec::new()),
            StorageType::Int64 => Self::Int64(Vec::new()),
            StorageType::UInt64 => Self::UInt64(Vec::new()),
            StorageType::Float32 => Self::Float32(Vec::new()),
            StorageType::Float64 => Self::Float64(Vec::new()),
            StorageType::String => Self::String(Vec::new()),
            StorageType::CategoricalString => Self::CategoricalString(Default::default()),
            StorageType::Vec2F32 => Self::Vec2F32(Vec::new()),
            StorageType::Vec2F64 => Self::Vec2F64(Vec::new()),
            StorageType::Vec3F32 => Self::Vec3F32(Vec::new()),
            StorageType::Vec3F64 => Self::Vec3F64(Vec::new()),
            StorageType::List(element_type) => Self::List(TypedListColumn::new(element_type)),
        }
    }

    pub fn storage_type(&self) -> StorageType {
        match self {
            Self::Bool(_) => StorageType::Bool,
            Self::Int8(_) => StorageType::Int8,
            Self::UInt8(_) => StorageType::UInt8,
            Self::Int16(_) => StorageType::Int16,
            Self::UInt16(_) => StorageType::UInt16,
            Self::Int32(_) => StorageType::Int32,
            Self::UInt32(_) => StorageType::UInt32,
            Self::Int64(_) => StorageType::Int64,
            Self::UInt64(_) => StorageType::UInt64,
            Self::Float32(_) => StorageType::Float32,
            Self::Float64(_) => StorageType::Float64,
            Self::String(_) => StorageType::String,
            Self::CategoricalString(_) => StorageType::CategoricalString,
            Self::Vec2F32(_) => StorageType::Vec2F32,
            Self::Vec2F64(_) => StorageType::Vec2F64,
            Self::Vec3F32(_) => StorageType::Vec3F32,
            Self::Vec3F64(_) => StorageType::Vec3F64,
            Self::List(values) => StorageType::List(values.element_type()),
        }
    }

    pub fn family_name(&self) -> &'static str {
        self.storage_type().name()
    }

    pub fn len(&self) -> usize {
        column_values_match!(self, len)
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn capacity(&self) -> usize {
        column_values_match!(self, capacity)
    }

    pub fn reserve(&mut self, additional: usize) {
        column_values_match!(self, reserve, additional)
    }

    pub fn allocated_bytes(&self) -> usize {
        match self {
            Self::Bool(values) => values.capacity().div_ceil(8),
            Self::Int8(values) => values.capacity() * size_of::<i8>(),
            Self::UInt8(values) => values.capacity() * size_of::<u8>(),
            Self::Int16(values) => values.capacity() * size_of::<i16>(),
            Self::UInt16(values) => values.capacity() * size_of::<u16>(),
            Self::Int32(values) => values.capacity() * size_of::<i32>(),
            Self::UInt32(values) => values.capacity() * size_of::<u32>(),
            Self::Int64(values) => values.capacity() * size_of::<i64>(),
            Self::UInt64(values) => values.capacity() * size_of::<u64>(),
            Self::Float32(values) => values.capacity() * size_of::<f32>(),
            Self::Float64(values) => values.capacity() * size_of::<f64>(),
            Self::String(values) => {
                values.capacity() * size_of::<String>()
                    + values.iter().map(|value| value.capacity()).sum::<usize>()
            }
            Self::CategoricalString(values) => values.allocated_bytes(),
            Self::Vec2F32(values) => values.capacity() * size_of::<[f32; 2]>(),
            Self::Vec2F64(values) => values.capacity() * size_of::<[f64; 2]>(),
            Self::Vec3F32(values) => values.capacity() * size_of::<[f32; 3]>(),
            Self::Vec3F64(values) => values.capacity() * size_of::<[f64; 3]>(),
            Self::List(values) => values.allocated_bytes(),
        }
    }

    pub fn push_default(&mut self) {
        self.push_value(self.default_value())
            .expect("column default must match its physical type");
    }

    pub fn default_value(&self) -> EcsValue {
        match self {
            Self::Bool(_) => EcsValue::Bool(false),
            Self::Int8(_) | Self::Int16(_) | Self::Int32(_) | Self::Int64(_) => EcsValue::I64(0),
            Self::UInt8(_) | Self::UInt16(_) | Self::UInt32(_) | Self::UInt64(_) => {
                EcsValue::U64(0)
            }
            Self::Float32(_) | Self::Float64(_) => EcsValue::F64(0.0),
            Self::String(_) | Self::CategoricalString(_) => EcsValue::String(String::new()),
            Self::Vec2F32(_) => EcsValue::Vec2F32([0.0, 0.0]),
            Self::Vec2F64(_) => EcsValue::Vec2F64([0.0, 0.0]),
            Self::Vec3F32(_) => EcsValue::Vec3F32([0.0, 0.0, 0.0]),
            Self::Vec3F64(_) => EcsValue::Vec3F64([0.0, 0.0, 0.0]),
            Self::List(_) => EcsValue::List(Vec::new()),
        }
    }

    pub fn push_value(&mut self, value: EcsValue) -> Result<()> {
        let value = coerce_value_for_storage(self.storage_type(), value)?;
        match (self, value) {
            (Self::Bool(values), EcsValue::Bool(value)) => values.push(value),
            (Self::Int8(values), EcsValue::I64(value)) => values.push(value as i8),
            (Self::UInt8(values), EcsValue::U64(value)) => values.push(value as u8),
            (Self::Int16(values), EcsValue::I64(value)) => values.push(value as i16),
            (Self::UInt16(values), EcsValue::U64(value)) => values.push(value as u16),
            (Self::Int32(values), EcsValue::I64(value)) => values.push(value as i32),
            (Self::UInt32(values), EcsValue::U64(value)) => values.push(value as u32),
            (Self::Int64(values), EcsValue::I64(value)) => values.push(value),
            (Self::UInt64(values), EcsValue::U64(value)) => values.push(value),
            (Self::Float32(values), EcsValue::F64(value)) => values.push(value as f32),
            (Self::Float64(values), EcsValue::F64(value)) => values.push(value),
            (Self::String(values), EcsValue::String(value)) => values.push(value),
            (Self::CategoricalString(values), EcsValue::String(value)) => values.push(value)?,
            (Self::Vec2F32(values), EcsValue::Vec2F32(value)) => values.push(value),
            (Self::Vec2F64(values), EcsValue::Vec2F64(value)) => values.push(value),
            (Self::Vec3F32(values), EcsValue::Vec3F32(value)) => values.push(value),
            (Self::Vec3F64(values), EcsValue::Vec3F64(value)) => values.push(value),
            (Self::List(values), EcsValue::List(value)) => values.push(value)?,
            (column, value) => return Err(type_mismatch(column.family_name(), value)),
        }
        Ok(())
    }

    pub fn get_f64(&self, row: usize) -> Result<f64> {
        if row >= self.len() {
            return Err(EcsError::RowOutOfBounds);
        }
        match self {
            Self::Bool(values) => Ok(if values[row] { 1.0 } else { 0.0 }),
            Self::Int8(values) => Ok(f64::from(values[row])),
            Self::UInt8(values) => Ok(f64::from(values[row])),
            Self::Int16(values) => Ok(f64::from(values[row])),
            Self::UInt16(values) => Ok(f64::from(values[row])),
            Self::Int32(values) => Ok(f64::from(values[row])),
            Self::UInt32(values) => Ok(f64::from(values[row])),
            Self::Int64(values) => Ok(values[row] as f64),
            Self::UInt64(values) => Ok(values[row] as f64),
            Self::Float32(values) => Ok(f64::from(values[row])),
            Self::Float64(values) => Ok(values[row]),
            column => Err(EcsError::ColumnTypeMismatch {
                expected: "numeric",
                got: column.family_name(),
            }),
        }
    }

    pub fn f64_slice(&self) -> Option<&[f64]> {
        match self {
            Self::Float64(values) => Some(values.as_slice()),
            _ => None,
        }
    }

    pub fn f64_slice_mut(&mut self) -> Option<&mut [f64]> {
        match self {
            Self::Float64(values) => Some(values.as_mut_slice()),
            _ => None,
        }
    }

    pub fn set_f64(&mut self, row: usize, value: f64) -> Result<()> {
        self.set(row, EcsValue::F64(value))
    }

    pub fn set_f64_rows(&mut self, rows: &[(usize, f64)]) -> Result<usize> {
        let mut converted = Vec::with_capacity(rows.len());
        for (row, value) in rows {
            if *row >= self.len() {
                return Err(EcsError::RowOutOfBounds);
            }
            let EcsValue::F64(value) =
                coerce_value_for_storage(self.storage_type(), EcsValue::F64(*value))?
            else {
                return Err(EcsError::ColumnTypeMismatch {
                    expected: "Float32 or Float64",
                    got: self.family_name(),
                });
            };
            converted.push((*row, value));
        }
        let mut written = 0;
        for (row, value) in converted {
            if self.get_f64(row)? != value {
                self.set_f64(row, value)?;
                written += 1;
            }
        }
        Ok(written)
    }

    pub fn get(&self, row: usize) -> Result<EcsValue> {
        let value = match self {
            Self::Bool(values) => EcsValue::Bool(*values.get(row).ok_or(EcsError::RowOutOfBounds)?),
            Self::Int8(values) => {
                EcsValue::I64(i64::from(*values.get(row).ok_or(EcsError::RowOutOfBounds)?))
            }
            Self::UInt8(values) => {
                EcsValue::U64(u64::from(*values.get(row).ok_or(EcsError::RowOutOfBounds)?))
            }
            Self::Int16(values) => {
                EcsValue::I64(i64::from(*values.get(row).ok_or(EcsError::RowOutOfBounds)?))
            }
            Self::UInt16(values) => {
                EcsValue::U64(u64::from(*values.get(row).ok_or(EcsError::RowOutOfBounds)?))
            }
            Self::Int32(values) => {
                EcsValue::I64(i64::from(*values.get(row).ok_or(EcsError::RowOutOfBounds)?))
            }
            Self::UInt32(values) => {
                EcsValue::U64(u64::from(*values.get(row).ok_or(EcsError::RowOutOfBounds)?))
            }
            Self::Int64(values) => EcsValue::I64(*values.get(row).ok_or(EcsError::RowOutOfBounds)?),
            Self::UInt64(values) => {
                EcsValue::U64(*values.get(row).ok_or(EcsError::RowOutOfBounds)?)
            }
            Self::Float32(values) => {
                EcsValue::F64(f64::from(*values.get(row).ok_or(EcsError::RowOutOfBounds)?))
            }
            Self::Float64(values) => {
                EcsValue::F64(*values.get(row).ok_or(EcsError::RowOutOfBounds)?)
            }
            Self::String(values) => {
                EcsValue::String(values.get(row).ok_or(EcsError::RowOutOfBounds)?.clone())
            }
            Self::CategoricalString(values) => EcsValue::String(values.get(row)?),
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
            Self::List(values) => EcsValue::List(values.get(row)?),
        };
        Ok(value)
    }

    pub fn set(&mut self, row: usize, value: EcsValue) -> Result<()> {
        if row >= self.len() {
            return Err(EcsError::RowOutOfBounds);
        }
        let value = coerce_value_for_storage(self.storage_type(), value)?;
        match (self, value) {
            (Self::Bool(values), EcsValue::Bool(value)) => values[row] = value,
            (Self::Int8(values), EcsValue::I64(value)) => values[row] = value as i8,
            (Self::UInt8(values), EcsValue::U64(value)) => values[row] = value as u8,
            (Self::Int16(values), EcsValue::I64(value)) => values[row] = value as i16,
            (Self::UInt16(values), EcsValue::U64(value)) => values[row] = value as u16,
            (Self::Int32(values), EcsValue::I64(value)) => values[row] = value as i32,
            (Self::UInt32(values), EcsValue::U64(value)) => values[row] = value as u32,
            (Self::Int64(values), EcsValue::I64(value)) => values[row] = value,
            (Self::UInt64(values), EcsValue::U64(value)) => values[row] = value,
            (Self::Float32(values), EcsValue::F64(value)) => values[row] = value as f32,
            (Self::Float64(values), EcsValue::F64(value)) => values[row] = value,
            (Self::String(values), EcsValue::String(value)) => values[row] = value,
            (Self::CategoricalString(values), EcsValue::String(value)) => values.set(row, value)?,
            (Self::Vec2F32(values), EcsValue::Vec2F32(value)) => values[row] = value,
            (Self::Vec2F64(values), EcsValue::Vec2F64(value)) => values[row] = value,
            (Self::Vec3F32(values), EcsValue::Vec3F32(value)) => values[row] = value,
            (Self::Vec3F64(values), EcsValue::Vec3F64(value)) => values[row] = value,
            (Self::List(values), EcsValue::List(value)) => values.set(row, value)?,
            (column, value) => return Err(type_mismatch(column.family_name(), value)),
        }
        Ok(())
    }

    pub fn swap_remove(&mut self, row: usize) -> Result<EcsValue> {
        if row >= self.len() {
            return Err(EcsError::RowOutOfBounds);
        }
        let value = match self {
            Self::Bool(values) => EcsValue::Bool(values.swap_remove(row)),
            Self::Int8(values) => EcsValue::I64(i64::from(values.swap_remove(row))),
            Self::UInt8(values) => EcsValue::U64(u64::from(values.swap_remove(row))),
            Self::Int16(values) => EcsValue::I64(i64::from(values.swap_remove(row))),
            Self::UInt16(values) => EcsValue::U64(u64::from(values.swap_remove(row))),
            Self::Int32(values) => EcsValue::I64(i64::from(values.swap_remove(row))),
            Self::UInt32(values) => EcsValue::U64(u64::from(values.swap_remove(row))),
            Self::Int64(values) => EcsValue::I64(values.swap_remove(row)),
            Self::UInt64(values) => EcsValue::U64(values.swap_remove(row)),
            Self::Float32(values) => EcsValue::F64(f64::from(values.swap_remove(row))),
            Self::Float64(values) => EcsValue::F64(values.swap_remove(row)),
            Self::String(values) => EcsValue::String(values.swap_remove(row)),
            Self::CategoricalString(values) => EcsValue::String(values.swap_remove(row)?),
            Self::Vec2F32(values) => EcsValue::Vec2F32(values.swap_remove(row)),
            Self::Vec2F64(values) => EcsValue::Vec2F64(values.swap_remove(row)),
            Self::Vec3F32(values) => EcsValue::Vec3F32(values.swap_remove(row)),
            Self::Vec3F64(values) => EcsValue::Vec3F64(values.swap_remove(row)),
            Self::List(values) => EcsValue::List(values.swap_remove(row)?),
        };
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scalar_widths_control_physical_layout_and_checked_range() {
        let mut narrow = Column::empty(StorageType::UInt16);
        let mut wide = Column::empty(StorageType::UInt64);
        narrow.reserve(1024);
        wide.reserve(1024);
        assert!(matches!(narrow, Column::UInt16(_)));
        assert!(narrow.allocated_bytes() * 3 < wide.allocated_bytes());
        narrow.push_value(EcsValue::I64(65_535)).unwrap();
        assert_eq!(narrow.get(0).unwrap(), EcsValue::U64(65_535));
        assert!(matches!(
            narrow.push_value(EcsValue::I64(65_536)),
            Err(EcsError::ValueOutOfRange { .. })
        ));
    }

    #[test]
    fn float32_rounds_at_every_write_boundary() {
        let mut column = Column::empty(StorageType::Float32);
        column.push_value(EcsValue::F64(1.0 / 3.0)).unwrap();
        assert_eq!(
            column.get(0).unwrap(),
            EcsValue::F64(f64::from((1.0_f64 / 3.0) as f32))
        );
        assert!(matches!(
            column.set(0, EcsValue::F64(f64::INFINITY)),
            Err(EcsError::NonFiniteFloat { .. })
        ));
    }

    #[test]
    fn categorical_columns_intern_and_reclaim_codes() {
        let mut column = Column::empty(StorageType::CategoricalString);
        column
            .push_value(EcsValue::String("red".to_string()))
            .unwrap();
        column
            .push_value(EcsValue::String("red".to_string()))
            .unwrap();
        column.set(0, EcsValue::String("blue".to_string())).unwrap();
        assert_eq!(column.get(0).unwrap(), EcsValue::String("blue".to_string()));
        assert_eq!(
            column.swap_remove(1).unwrap(),
            EcsValue::String("red".to_string())
        );
        assert_eq!(column.len(), 1);
    }

    #[test]
    fn typed_lists_use_packed_narrow_values_and_preserve_swap_remove() {
        let mut list = Column::empty(StorageType::List(ListElementType::Int8));
        list.push_value(EcsValue::List(vec![EcsValue::I64(1), EcsValue::I64(2)]))
            .unwrap();
        list.push_value(EcsValue::List(vec![EcsValue::I64(3)]))
            .unwrap();
        assert!(matches!(
            list.push_value(EcsValue::List(vec![EcsValue::I64(128)])),
            Err(EcsError::ValueOutOfRange { .. })
        ));
        assert_eq!(
            list.swap_remove(0).unwrap(),
            EcsValue::List(vec![EcsValue::I64(1), EcsValue::I64(2)])
        );
        assert_eq!(list.get(0).unwrap(), EcsValue::List(vec![EcsValue::I64(3)]));
    }
}
