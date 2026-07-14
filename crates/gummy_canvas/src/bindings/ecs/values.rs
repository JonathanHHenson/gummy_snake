use std::collections::HashMap;

use gummy_ecs::{ComponentRow, EcsValue, EntityRowData, SpawnEntity};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyTuple};

pub(super) fn py_to_ecs_value(value: &Bound<'_, PyAny>) -> PyResult<EcsValue> {
    if let Ok(value) = value.extract::<bool>() {
        return Ok(EcsValue::Bool(value));
    }
    if let Ok(value) = value.extract::<i64>() {
        return Ok(EcsValue::I64(value));
    }
    if let Ok(value) = value.extract::<u64>() {
        return Ok(EcsValue::U64(value));
    }
    if let Ok(value) = value.extract::<f64>() {
        return Ok(EcsValue::F64(value));
    }
    if let Ok(value) = value.extract::<String>() {
        return Ok(EcsValue::String(value));
    }
    if let Ok(tuple) = value.downcast::<PyTuple>() {
        return match tuple.len() {
            2 => Ok(EcsValue::Vec2F64([
                tuple.get_item(0)?.extract::<f64>()?,
                tuple.get_item(1)?.extract::<f64>()?,
            ])),
            3 => Ok(EcsValue::Vec3F64([
                tuple.get_item(0)?.extract::<f64>()?,
                tuple.get_item(1)?.extract::<f64>()?,
                tuple.get_item(2)?.extract::<f64>()?,
            ])),
            _ => Err(PyValueError::new_err(
                "ECS tuple values must have length 2 or 3",
            )),
        };
    }
    if let Ok(list) = value.downcast::<PyList>() {
        let mut values = Vec::with_capacity(list.len());
        for item in list.iter() {
            values.push(py_to_ecs_value(&item)?);
        }
        return Ok(EcsValue::List(values));
    }
    if let Ok(dict) = value.downcast::<PyDict>() {
        let mut fields = HashMap::new();
        for (key, value) in dict.iter() {
            fields.insert(key.extract::<String>()?, py_to_ecs_value(&value)?);
        }
        return Ok(EcsValue::Struct(fields));
    }
    Err(PyValueError::new_err(
        "unsupported ECS value; expected bool, int, float, str, tuple[float, ...], list, or dict",
    ))
}

pub(super) fn ecs_value_to_py(py: Python<'_>, value: &EcsValue) -> PyResult<PyObject> {
    match value {
        EcsValue::Bool(value) => Ok(value.into_py(py)),
        EcsValue::I64(value) => Ok(value.into_py(py)),
        EcsValue::U64(value) => Ok(value.into_py(py)),
        EcsValue::F64(value) => Ok(value.into_py(py)),
        EcsValue::String(value) => Ok(value.into_py(py)),
        EcsValue::Vec2F32(value) => Ok((value[0], value[1]).into_py(py)),
        EcsValue::Vec2F64(value) => Ok((value[0], value[1]).into_py(py)),
        EcsValue::Vec3F32(value) => Ok((value[0], value[1], value[2]).into_py(py)),
        EcsValue::Vec3F64(value) => Ok((value[0], value[1], value[2]).into_py(py)),
        EcsValue::List(values) => {
            let items = values
                .iter()
                .map(|value| ecs_value_to_py(py, value))
                .collect::<PyResult<Vec<_>>>()?;
            Ok(PyList::new_bound(py, items).into_py(py))
        }
        EcsValue::Struct(fields) => {
            let dict = PyDict::new_bound(py);
            for (key, value) in fields {
                dict.set_item(key, ecs_value_to_py(py, value)?)?;
            }
            Ok(dict.into_py(py))
        }
    }
}

pub(super) fn component_row_from_dict(fields: &Bound<'_, PyDict>) -> PyResult<ComponentRow> {
    let mut row = ComponentRow::new();
    for (key, value) in fields.iter() {
        row.insert(key.extract::<String>()?, py_to_ecs_value(&value)?);
    }
    Ok(row)
}

pub(super) fn spawn_entities_from_list(rows: &Bound<'_, PyList>) -> PyResult<Vec<SpawnEntity>> {
    let mut entities = Vec::with_capacity(rows.len());
    for (row_index, value) in rows.iter().enumerate() {
        let row = value.downcast::<PyTuple>().map_err(|_| {
            PyValueError::new_err(format!(
                "ECS bulk spawn row {row_index} must be a (components, tags) tuple"
            ))
        })?;
        if row.len() != 2 {
            return Err(PyValueError::new_err(format!(
                "ECS bulk spawn row {row_index} must contain components and tags"
            )));
        }
        let component_value = row.get_item(0)?;
        let component_dict = component_value.downcast::<PyDict>().map_err(|_| {
            PyValueError::new_err(format!(
                "ECS bulk spawn row {row_index} components must be a dict"
            ))
        })?;
        let mut components = EntityRowData::with_capacity(component_dict.len());
        for (name, fields) in component_dict.iter() {
            let component_name = name.extract::<String>()?;
            let fields = fields.downcast::<PyDict>().map_err(|_| {
                PyValueError::new_err(format!(
                    "ECS bulk spawn component {component_name:?} fields must be a dict"
                ))
            })?;
            components.insert(component_name, component_row_from_dict(fields)?);
        }
        let tags = row.get_item(1)?.extract::<Vec<String>>().map_err(|_| {
            PyValueError::new_err(format!(
                "ECS bulk spawn row {row_index} tags must be a list of strings"
            ))
        })?;
        entities.push(SpawnEntity::new(components, tags));
    }
    Ok(entities)
}

pub(super) fn component_row_to_dict<'py>(
    py: Python<'py>,
    row: ComponentRow,
) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new_bound(py);
    for (key, value) in row {
        dict.set_item(key, ecs_value_to_py(py, &value)?)?;
    }
    Ok(dict)
}
