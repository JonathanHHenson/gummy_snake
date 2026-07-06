mod parse;
mod spatial_registry;
mod summaries;
mod values;
mod world;

use gummy_ecs::{health_check as ecs_core_health_check, ECS_ABI_VERSION};
use pyo3::prelude::*;

pub(crate) use spatial_registry::PyEcsSpatialIndexRegistry;
pub(crate) use world::PyEcsWorld;

#[pyfunction]
pub(crate) fn ecs_abi_version() -> u32 {
    ECS_ABI_VERSION
}

#[pyfunction]
pub(crate) fn ecs_health_check() -> &'static str {
    ecs_core_health_check()
}
