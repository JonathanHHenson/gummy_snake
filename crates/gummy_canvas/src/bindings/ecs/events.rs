use gummy_ecs::World;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use super::values::ecs_value_to_py;

pub(super) fn read_events_to_list<'py>(
    py: Python<'py>,
    world: &World,
    event_type: &str,
) -> PyResult<Bound<'py, PyList>> {
    let events = world
        .read_events(event_type)
        .map_err(|err| pyo3::exceptions::PyValueError::new_err(err.to_string()))?;
    let out = PyList::empty_bound(py);
    for event in events {
        let item = PyDict::new_bound(py);
        item.set_item("frame", event.frame)?;
        item.set_item("sequence", event.sequence)?;
        item.set_item("payload", ecs_value_to_py(py, &event.payload)?)?;
        out.append(item)?;
    }
    Ok(out)
}
